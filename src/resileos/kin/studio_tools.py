"""Studio legions: Forge video, graphify ingest, and the plan/test/debug loop.

Hephaestus is the Studio patron and is not a Kin. Forge video and the
plan/test/debug loop register on Hermes, which is paths and dispatch.
Graphify registers on Eat. Hades keeps lessons and checkpoints and does
not host these tools.

A Demi-god reaches a legion only by mounting that parent's name into the
temporary swarm. The swarm does not copy the legion onto another Kin.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import uuid
from typing import Any, Callable

from resileos.harness.tools import budget_and_stuck_guard, verify_on_stop
from resileos.kin.eat import eat_filter
from resileos.kin.legions import invoke_legion, kin_catalogue, register_legion

_MUTATING = frozenset({"write_file", "apply_diff", "git_commit"})
_STUDIO = ("forge_video", "graphify", "plan_test_debug")


def _proof(packet: dict[str, Any] | None, apollo_result: dict[str, Any] | None) -> dict[str, Any]:
    return verify_on_stop(dict(packet or {}), apollo_result)


def _verified_step(goal: str, verdict: str, verified: bool) -> dict[str, Any]:
    """Higher step. Built only from the goal and a verdict word."""
    word = verdict if verdict in {"pass", "fail", "unverified"} else "unverified"
    return {"verified": bool(verified), "artefact": {"goal": str(goal), "verdict": word}}


def _default_test(goal: str) -> dict[str, Any]:
    if not str(goal).strip():
        return {"ok": False, "stdout": "", "signature": "empty-goal"}
    return {"ok": True, "stdout": "", "signature": "goal-present"}


def _critique(test_ok: bool | None) -> dict[str, Any]:
    """Momus's part of the loop. Critique is not proof and does not approve a missing test."""
    if test_ok is None:
        return {"outcome": "need_more", "approved": False, "reason": "missing test"}
    if test_ok:
        return {
            "outcome": "noted",
            "approved": False,
            "reason": "test passed; critique is not proof",
        }
    return {"outcome": "fail", "approved": False, "reason": "test failed"}


def _candidates(source: Any) -> list[Any]:
    """Turn a graph or text into claim candidates. Missing fields stay missing."""
    if isinstance(source, dict) and isinstance(source.get("edges"), list):
        claims: list[Any] = []
        for edge in source["edges"][:64]:
            if not isinstance(edge, dict):
                claims.append(edge)
                continue
            claims.append(
                {
                    "subject": edge.get("from", edge.get("subject", "")),
                    "relation": edge.get("relation", edge.get("rel", "")),
                    "obj": edge.get("to", edge.get("obj", edge.get("object", ""))),
                }
            )
        return claims
    if isinstance(source, dict) and isinstance(source.get("triples"), list):
        return list(source["triples"][:64])
    if isinstance(source, list):
        return list(source[:64])
    if isinstance(source, str):
        lines = [line.strip() for line in source.splitlines() if line.strip()]
        return (lines or [source.strip()])[:64]
    return [source]


def _unavailable(prompt: str, stage: str, detail: str) -> dict[str, Any]:
    return {
        "status": "UNAVAILABLE",
        "detail": detail,
        "draft": False,
        "prompt": prompt,
        "url": None,
        "stage": stage,
        "patron": "hephaestus",
    }


def _asset_url(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    url = payload.get("url") or payload.get("video_url")
    if not isinstance(url, str):
        return None
    text = url.strip()
    return text or None


def _run_executable(path: str, prompt: str) -> dict[str, Any]:
    """Run a configured provider executable. No shell. No invented URL."""
    proc = subprocess.Popen(
        [path, prompt],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )
    try:
        out, _err = proc.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.wait(timeout=3)
        return _unavailable(prompt, "draft", "Video provider timed out.")
    if proc.returncode != 0:
        return _unavailable(prompt, "draft", "Video provider failed.")
    try:
        payload = json.loads((out or "")[:4000] or "{}")
    except json.JSONDecodeError:
        return _unavailable(prompt, "draft", "Video provider returned no asset.")
    url = _asset_url(payload)
    if url is None:
        return _unavailable(prompt, "draft", "Video provider returned no asset.")
    return {
        "status": "submitted",
        "detail": "",
        "draft": True,
        "prompt": prompt,
        "url": url,
        "stage": "draft",
        "patron": "hephaestus",
        "result": payload if isinstance(payload, dict) else {},
    }


def forge_video(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Forge video under Hephaestus. Draft through a configured provider, or UNAVAILABLE."""
    del seen
    prompt = str(kwargs.get("prompt") or "")[:2000]
    stage = str(kwargs.get("stage") or "draft")
    packet = {
        "verified": bool(kwargs.get("verified")),
        "scars": list(kwargs.get("scars") or []),
        "evidence": list(kwargs.get("evidence") or []),
    }
    apollo = kwargs.get("apollo_result")
    if not isinstance(apollo, dict) and kwargs.get("apollo_success"):
        apollo = {"success": True}
    proof = _proof(packet, apollo if isinstance(apollo, dict) else None)
    if stage not in {"draft", "verify", "upscale"}:
        refused = _unavailable(prompt, stage, "Unknown forge stage.")
        refused["status"] = "refused"
        return refused
    if stage == "verify":
        return {
            "status": "verified" if proof.get("verified") else "unverified",
            "detail": "",
            "draft": not bool(proof.get("verified")),
            "prompt": prompt,
            "url": None,
            "stage": "verify",
            "patron": "hephaestus",
            "verified": bool(proof.get("verified")),
        }
    if stage == "upscale" and not proof.get("verified"):
        return {
            "status": "refused",
            "detail": "Upscale waits until the draft is verified.",
            "draft": False,
            "prompt": prompt,
            "url": None,
            "stage": "upscale",
            "patron": "hephaestus",
            "verified": False,
        }
    provider_fn = kwargs.get("provider_fn")
    if callable(provider_fn):
        try:
            payload = provider_fn(prompt)
        except Exception:
            return _unavailable(prompt, stage, "Video provider failed.")
        url = _asset_url(payload)
        if url is None:
            return _unavailable(prompt, stage, "Video provider returned no asset.")
        result = {
            "status": "submitted",
            "detail": "",
            "draft": stage != "upscale",
            "prompt": prompt,
            "url": url,
            "stage": stage,
            "patron": "hephaestus",
            "verified": bool(proof.get("verified")),
        }
        if isinstance(payload, dict):
            if payload.get("pgid") is not None:
                result["pgid"] = payload.get("pgid")
            if payload.get("process_alive"):
                result["process_alive"] = True
        return result
    provider = os.getenv("RESILEOS_VIDEO_PROVIDER", "").strip()
    if provider and os.path.isfile(provider) and os.access(provider, os.X_OK):
        produced = _run_executable(provider, prompt)
        produced["stage"] = stage
        produced["verified"] = bool(proof.get("verified"))
        if stage == "upscale" and produced.get("status") == "submitted":
            produced["draft"] = False
        return produced
    from resileos.ui.fluid_gen import generate_video_hook

    hooked = generate_video_hook(prompt)
    hooked["stage"] = stage
    hooked["patron"] = "hephaestus"
    hooked["verified"] = bool(proof.get("verified"))
    if hooked.get("url") in ("", None):
        hooked["url"] = None
        hooked["status"] = "UNAVAILABLE"
        hooked["draft"] = False
    return hooked


def graphify(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Ingest a graph through Eat. Learn only the accepted claims when commit is set."""
    del seen
    source = kwargs.get("source")
    commit = bool(kwargs.get("commit"))
    if isinstance(source, str) and len(source) > 8000:
        return {
            "decisions": [],
            "claims": [],
            "learned": 0,
            "error": "source too long",
        }
    decisions: list[dict[str, Any]] = []
    claims: list[list[str]] = []
    for candidate in _candidates(source):
        decision = eat_filter(candidate)
        action = str(getattr(decision, "action", "") or "")
        row = {
            "action": action,
            "subject": str(getattr(decision, "subject", "") or ""),
            "relation": str(getattr(decision, "relation", "") or ""),
            "obj": str(getattr(decision, "obj", "") or ""),
            "reason": str(getattr(decision, "reason", "") or ""),
        }
        decisions.append(row)
        if commit and action == "accept" and row["subject"] and row["relation"] and row["obj"]:
            claims.append([row["subject"], row["relation"], row["obj"]])
    return {"decisions": decisions, "claims": claims, "learned": len(claims)}


def run_plan_test_debug(
    goal: str,
    *,
    steps: list[dict[str, Any]] | None = None,
    test_fn: Callable[..., Any] | None = None,
    tools: dict[str, Callable[..., Any]] | None = None,
    packet: dict[str, Any] | None = None,
    apollo_result: dict[str, Any] | None = None,
    allow_mutate: bool = False,
    spec: Any = None,
    residual_hash: str | None = None,
    max_rounds: int = 3,
) -> dict[str, Any]:
    """Plan, test, and debug without spinning and without promoting lower-tier output.

    Hermes dispatches the steps. Momus critiques. Athena judges a clean
    perception. Themis keeps mutating steps refused until Apollo's
    ``verify_on_stop`` passes. Hades is not asked to checkpoint here.
    """
    goal = str(goal or "")
    if isinstance(steps, list):
        plan = [step for step in steps if isinstance(step, dict)][:12]
    else:
        plan = [
            {"tool": "plan", "args": {"goal": goal}},
            {"tool": "test", "args": {"goal": goal}},
            {"tool": "debug", "args": {}},
        ]
    rounds_cap = int(max_rounds or 3)
    if rounds_cap < 1:
        rounds_cap = 1
    if rounds_cap > 6:
        rounds_cap = 6
    tool_table = dict(tools or {})
    view = {
        "verified": bool((packet or {}).get("verified")),
        "scars": list((packet or {}).get("scars") or []),
        "evidence": list((packet or {}).get("evidence") or []),
        "budget_remaining": dict(
            (packet or {}).get("budget_remaining") or {"steps": 8, "cost": 1.0}
        ),
    }
    trace: list[dict[str, Any]] = []
    lower: list[dict[str, Any]] = []
    rounds = 0
    index = 0
    advanced = 0
    stuck = False
    last_sig: str | None = None
    test_ok: bool | None = None
    refused_mutate = False
    critique = _critique(None)

    while index < len(plan) and rounds < rounds_cap:
        rounds += 1
        guard = budget_and_stuck_guard(
            {
                "budget_remaining": dict(view["budget_remaining"]),
                "history": [],
            }
        )
        if not guard["ok"]:
            stuck = True
            trace.append(
                {"tool": "guard", "ok": False, "ran": False, "reason": guard.get("reason")}
            )
            advanced += 1
            break
        step = plan[index]
        tool = str(step.get("tool") or "")
        args = step.get("args") if isinstance(step.get("args"), dict) else {}
        if tool in _MUTATING:
            proof_now = _proof(view, apollo_result)
            if not allow_mutate or not proof_now.get("verified"):
                refused_mutate = True
                trace.append(
                    {
                        "tool": tool,
                        "ok": False,
                        "ran": False,
                        "refused": True,
                        "reason": "refused until verified",
                    }
                )
                index += 1
                advanced += 1
                continue
            fn = tool_table.get(tool)
            if not callable(fn):
                refused_mutate = True
                trace.append(
                    {
                        "tool": tool,
                        "ok": False,
                        "ran": False,
                        "refused": True,
                        "reason": "refused until verified",
                    }
                )
                index += 1
                advanced += 1
                continue
            try:
                produced = fn(**args)
            except Exception as exc:
                produced = {"ok": False, "error": type(exc).__name__}
            ok = bool(produced.get("ok", True)) if isinstance(produced, dict) else True
            trace.append({"tool": tool, "ok": ok, "ran": True, "refused": False})
            index += 1
            advanced += 1
            continue
        if tool == "test":
            if callable(test_fn):
                produced = test_fn(goal, rounds)
            else:
                produced = _default_test(goal)
            if not isinstance(produced, dict):
                produced = {"ok": False, "stdout": "", "signature": "bad-result"}
            stdout = str(produced.get("stdout") or "")
            signature = str(
                produced.get("signature")
                or ("fail" if not produced.get("ok") else "pass")
            )
            lower.append(
                {
                    "tool": "test",
                    "stdout": stdout,
                    "process_alive": bool(produced.get("process_alive")),
                    "waited": False,
                }
            )
            ok = bool(produced.get("ok"))
            trace.append({"tool": "test", "ok": ok, "ran": True, "tier": "lower"})
            if not ok:
                if signature == last_sig:
                    stuck = True
                    advanced += 1
                    break
                last_sig = signature
                test_ok = False
                advanced += 1
                continue
            test_ok = True
            index += 1
            advanced += 1
            continue
        if tool == "debug":
            critique = _critique(test_ok)
            if spec is not None and residual_hash:
                from resileos.kin.demigods import checks as demigod_checks

                review = demigod_checks.momus_review(
                    {"goal": goal, "test_ok": bool(test_ok)},
                    spec,
                    residual_hash,
                )
                critique = {
                    "outcome": review.outcome,
                    "approved": bool(review.verified),
                    "reason": review.reason,
                }
            lower.append({"tool": "debug", "critique": critique["reason"], "stdout": ""})
            trace.append(
                {
                    "tool": "debug",
                    "ok": True,
                    "ran": True,
                    "tier": "critique",
                    "outcome": critique["outcome"],
                }
            )
            index += 1
            advanced += 1
            continue
        if tool == "plan":
            trace.append({"tool": "plan", "ok": True, "ran": True, "steps": len(plan)})
            index += 1
            advanced += 1
            continue
        trace.append({"tool": tool or "unknown", "ok": False, "ran": False, "reason": "unknown tool"})
        index += 1
        advanced += 1

    proof = _proof(view, apollo_result)
    passed = test_ok is not False and not stuck and not refused_mutate
    if test_ok is False:
        passed = False
    verdict = "pass" if passed and proof.get("verified") else "unverified"
    verified_step = _verified_step(goal, verdict, bool(proof.get("verified") and passed))
    from resileos.kin.athena import judge

    judgment = judge(
        [{"subject": "loop", "address": {"residual_bin": "pass" if passed else "fail"}}]
    )
    law_holds = True
    for row in trace:
        if row.get("tool") in _MUTATING and row.get("ran") and not proof.get("verified"):
            law_holds = False
    return {
        "goal": goal,
        "ok": bool(passed),
        "progress": advanced > 0 and rounds <= rounds_cap,
        "stuck": stuck,
        "rounds": rounds,
        "trace": trace,
        "lower_tier": lower,
        "verified_step": verified_step,
        "checkpoint": None,
        "waited": False,
        "roles": {
            "hermes": "paths",
            "momus": critique,
            "athena": "judgment",
            "themis": "law",
            "apollo": proof,
            "hades": "lessons",
        },
        "judgment_ok": bool(judgment.get("ok")),
        "law_holds": law_holds,
    }


def plan_test_debug(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Plan, test, and debug on the Hermes path. Mutating steps stay refused until verified."""
    packet = {
        "verified": bool(kwargs.get("verified")),
        "scars": list(kwargs.get("scars") or []),
        "evidence": list(kwargs.get("evidence") or []),
        "budget_remaining": dict(seen.get("budget_remaining") or {"steps": 8, "cost": 1.0}),
    }
    steps = kwargs.get("steps")
    return run_plan_test_debug(
        str(kwargs.get("goal") or ""),
        steps=steps if isinstance(steps, list) else None,
        test_fn=kwargs.get("test_fn") if callable(kwargs.get("test_fn")) else None,
        tools=kwargs.get("tools") if isinstance(kwargs.get("tools"), dict) else None,
        packet=packet,
        apollo_result=kwargs.get("apollo_result")
        if isinstance(kwargs.get("apollo_result"), dict)
        else None,
        allow_mutate=bool(kwargs.get("allow_mutate")),
        spec=kwargs.get("spec"),
        residual_hash=kwargs.get("residual_hash")
        if isinstance(kwargs.get("residual_hash"), str)
        else None,
        max_rounds=int(kwargs.get("max_rounds") or 3),
    )


def _studio_ready() -> bool:
    hermes = {row["name"] for row in kin_catalogue("hermes")}
    eat = {row["name"] for row in kin_catalogue("eat")}
    return "forge_video" in hermes and "plan_test_debug" in hermes and "graphify" in eat


def register_studio_legions() -> list[str]:
    """Register the three Studio legions once. Idempotent."""
    if _studio_ready():
        return list(_STUDIO)
    register_legion(
        "hermes",
        forge_video,
        name="forge_video",
        constraints={
            "action": "draft video",
            "writes_residual": False,
            "executes": True,
            "spawns_processes": True,
        },
    )
    register_legion(
        "eat",
        graphify,
        name="graphify",
        constraints={
            "action": "ingest graph",
            "writes_residual": True,
            "executes": True,
        },
    )
    register_legion(
        "hermes",
        plan_test_debug,
        name="plan_test_debug",
        constraints={
            "action": "inspect cycle",
            "writes_residual": False,
            "executes": True,
        },
    )
    return list(_STUDIO)


def _packet(kind: str) -> dict[str, Any]:
    return {
        "id": f"{kind}-{uuid.uuid4().hex[:8]}",
        "budget_remaining": {"steps": 8, "cost": 1.0, "tokens": 1000},
        "evidence": [],
        "history": [],
        "scars": [],
        "verified": False,
    }


def run_forge_video(
    prompt: str,
    *,
    provider_fn: Callable[..., Any] | None = None,
    stage: str = "draft",
    verified: bool = False,
    scars: list[str] | None = None,
    apollo_result: dict[str, Any] | None = None,
    packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Invoke the Forge legion and register any worker on the packet owner."""
    from resileos.kin.demigods.swarm import swarm_meta
    from resileos.kin.moirai import note_worker

    register_studio_legions()
    host = packet or _packet("forge")
    result = invoke_legion(
        "hermes",
        "forge_video",
        host,
        prompt=prompt,
        provider_fn=provider_fn,
        stage=stage,
        verified=verified,
        scars=list(scars or []),
        apollo_result=apollo_result,
    )
    meta = swarm_meta(host)
    owner = str(meta["attempt_id"]) if meta else str(host.get("id") or "forge")
    if meta is None:
        note_worker(owner, "forge_video", result)
    result["clotho_owner"] = owner
    return result


def run_graphify(
    source: Any,
    *,
    commit: bool = False,
    learn_fn: Callable[[str, str, str], Any] | None = None,
    packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Invoke graphify. ``learn_fn`` is passed only when the caller sets commit."""
    register_studio_legions()
    host = packet or _packet("graphify")
    kwargs: dict[str, Any] = {"source": source, "commit": bool(commit)}
    if commit and learn_fn is not None:
        kwargs["learn_fn"] = learn_fn
    return invoke_legion("eat", "graphify", host, **kwargs)


def run_plan_loop(
    goal: str,
    *,
    steps: list[dict[str, Any]] | None = None,
    packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """HTTP and Studio entry. Mutating tools are not executed on this surface."""
    register_studio_legions()
    host = packet or _packet("plan")
    return invoke_legion(
        "hermes",
        "plan_test_debug",
        host,
        goal=goal,
        steps=steps,
        allow_mutate=False,
    )
