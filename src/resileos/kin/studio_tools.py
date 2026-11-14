"""Studio legions: Forge video, graphify ingest, the plan/test/debug loop, and Muse.

Muse is the native generative leaf, a legion under Apollo (not a Kin).
ControlPacket plus a brief go in; evidence, confidence, and cost come
out. Its output is evidence, never a fact: it never verifies, never
calls learn, never touches scars, and never writes Titanos (Eat stays
the only writer). Hades keeps at most a one-line lesson from it. The
budget guard counts its time and memory. It is not on the confidence
cascade: Studio calls it, or a caller names it explicitly. Engines run
on the leveled core (``studio.level_core``): phase-based keyframe clips
checked with ``clip_metrics``, and leveled WFC environments with the
overlay scene graph and the game rule checks. No outside model.

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
_STUDIO = ("forge_video", "graphify", "plan_test_debug", "muse")
MUSE_KINDS = ("clip", "environment", "text_video")
MUSE_BUDGET = {"steps": 8, "cost": 1.0, "tokens": 1000, "seconds": 60.0, "memory_mb": 512.0}


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


def _has_residual_input(kwargs: dict[str, Any]) -> bool:
    if kwargs.get("matrix") is not None or isinstance(kwargs.get("residual_packet"), dict):
        return True
    frames = kwargs.get("frames")
    return isinstance(frames, list) and len(frames) > 0


def forge_video(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Forge under Hephaestus.

    A matrix, frame list, or residual packet is drafted and verified by the
    layer-scale codec. Two frames are a residual phase step: only the
    residual packet travels. ``clip=True`` compresses a supplied sequence
    as one base packet plus delta packets and checks that sequence. It does
    not generate video. A provider is used only for an inconclusive upscale
    of a residual delta. A prompt with no residual input stays the video
    request: a configured provider, or UNAVAILABLE with no invented URL.
    """
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
    if bool(kwargs.get("clip")) or isinstance(kwargs.get("sequence"), dict):
        from resileos.studio.sequence_stage import run_sequence_stage

        produced = run_sequence_stage(
            stage=stage,
            prompt=prompt,
            frames=kwargs.get("frames"),
            sequence=kwargs.get("sequence") if isinstance(kwargs.get("sequence"), dict) else None,
            context=kwargs.get("context"),
            control=kwargs.get("control"),
            provider_fn=kwargs.get("provider_fn"),
            learn=kwargs.get("learn"),
            bypass_zeus=bool(kwargs.get("bypass_zeus")),
            zeus=kwargs.get("zeus"),
            history=kwargs.get("clip_history"),
        )
        if not produced.get("hades_checkpoint"):
            produced["checkpoint"] = None
            produced["hades_checkpoint"] = False
        return produced
    if _has_residual_input(kwargs):
        from resileos.studio.residual_cascade import run_visual_stage

        produced = run_visual_stage(
            stage=stage,
            prompt=prompt,
            matrix=kwargs.get("matrix"),
            frames=kwargs.get("frames"),
            residual_packet=kwargs.get("residual_packet")
            if isinstance(kwargs.get("residual_packet"), dict)
            else None,
            provider_fn=kwargs.get("provider_fn"),
            control=kwargs.get("control"),
            learn=kwargs.get("learn"),
            bypass_zeus=bool(kwargs.get("bypass_zeus")),
            zeus=kwargs.get("zeus"),
            previous=kwargs.get("previous"),
            keyframe=kwargs.get("keyframe"),
            draft=kwargs.get("draft"),
            prediction=str(kwargs.get("prediction") or "previous"),
        )
        produced["checkpoint"] = None
        produced["hades_checkpoint"] = False
        return produced
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
    from resileos.studio.residual_cascade import (
        cascade_scale,
        remember_accepted,
        text_matrix,
    )

    decisions: list[dict[str, Any]] = []
    claims: list[list[str]] = []
    residual_candidates: list[dict[str, Any]] = []
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
        label = " ".join(part for part in (row["subject"], row["relation"], row["obj"]) if part)
        if not label:
            label = candidate if isinstance(candidate, str) else json.dumps(candidate, default=str)[:500]
        evolved = cascade_scale(
            text_matrix(label),
            prompt=label[:200],
            register=False,
            address=False,
        )
        summary = evolved.get("compression") if isinstance(evolved.get("compression"), dict) else {}
        row["residual_hash"] = str(evolved.get("packet_hash") or "")
        row["residual"] = {
            "packet_hash": row["residual_hash"],
            "scale_mode": evolved.get("scale_mode"),
            "layer_scale": evolved.get("layer_scale"),
            "credit_cost": summary.get("credit_cost"),
            "outcome": evolved.get("outcome"),
        }
        residual_candidates.append(
            {
                "action": action,
                "subject": row["subject"],
                "relation": row["relation"],
                "obj": row["obj"],
                "packet_hash": row["residual_hash"],
                "scale_mode": evolved.get("scale_mode"),
            }
        )
        decisions.append(row)
        if commit and action == "accept" and row["subject"] and row["relation"] and row["obj"]:
            claims.append([row["subject"], row["relation"], row["obj"]])
            remember_accepted(row["subject"], row["relation"], row["obj"], evolved)
    return {
        "decisions": decisions,
        "claims": claims,
        "learned": len(claims),
        "residual_candidates": residual_candidates,
    }


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


# ── Muse: the native generative leaf (legion under Apollo) ──────────────

def _evidence_id(obj: Any) -> str:
    import hashlib

    import numpy as np

    h = hashlib.sha256()

    def feed(x: Any) -> None:
        if isinstance(x, np.ndarray):
            h.update(np.round(x, 4).tobytes())
        elif isinstance(x, dict):
            for k in sorted(x):
                h.update(str(k).encode())
                feed(x[k])
        elif isinstance(x, (list, tuple)):
            for v in x:
                feed(v)
        else:
            h.update(json.dumps(x, sort_keys=True, default=str).encode())

    feed(obj)
    return "ev-" + h.hexdigest()[:16]


def _muse_clip(brief: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    from resileos.studio import level_core as core
    from resileos.studio.clip_metrics import clip_check_metrics, phase_band_coherence

    keys = list(brief.get("keyframes") or [])
    if len(keys) < 2:
        return {"status": "NOTHING", "reason": "a clip needs two or more keyframes", "confidence": 0.0}
    seq = core.phase_clip(keys, per=int(brief.get("per") or 4), holds=brief.get("holds"),
                          cap=int(brief.get("cap") or 24))
    gray = [f.mean(axis=2) if f.ndim == 3 else f for f in seq]
    bands = phase_band_coherence(seq)
    return {
        "status": "MADE",
        "evidence": {"frames": [np.round(f, 3) for f in seq], "fps": 8, "keyframes": len(keys),
                     "method": "keyframes with phase-based in-betweens on the cascade bands",
                     "metrics": {**clip_check_metrics(gray), "phase_band_coherence": bands}},
        "confidence": float(bands["R"] or 0.0),
    }


def _muse_environment(brief: dict[str, Any]) -> dict[str, Any]:
    from resileos.studio import level_core as core
    from resileos.studio.projects import check_game, check_timeline, game_lean_source

    project = dict(brief.get("project") or {})
    env = core.environment(project, seed=brief.get("seed"))
    if not env.get("ok"):
        return {"status": "FAILED", "reason": env.get("reason"), "confidence": 0.0}
    game = project.get("game") or {}
    bible = project.get("bible") or {}
    checks = {
        "regions_fit": env["regions"]["adjacency_ok"],
        "tiles_fit": env["tiles"]["adjacency_ok"],
        "tiles_nest_in_regions": env["tiles"]["nested_in_regions"],
    }
    game_out = check_game(game) if game.get("stats") else None
    if game_out is not None:
        checks["game_rules_hold"] = bool(game_out.get("ok"))
    timeline = check_timeline(bible.get("timeline") or []) if bible.get("timeline") else None
    if timeline is not None:
        checks["timeline_fits"] = bool(timeline.get("ok"))
    return {
        "status": "MADE",
        "evidence": {**env, "game": game_out, "timeline": timeline, "checks": checks,
                     "lean_source": game_source if (game_source := game_lean_source(game)) else None,
                     "method": "leveled wave function collapse: regions at frame 3, places at 5, scene tiles at 9"},
        "confidence": sum(bool(v) for v in checks.values()) / len(checks),
    }


def _muse_text_video(brief: dict[str, Any]) -> dict[str, Any]:
    """Words alone are not turned into pictures. A clip is made only from a
    scene whose place is in the world bible: a slow pan over that world's
    generated map. Otherwise UNAVAILABLE with url None."""
    import math

    import numpy as np

    from resileos.studio import level_core as core
    from resileos.studio.clip_metrics import clip_check_metrics, phase_band_coherence
    from resileos.ui.cascade_address import BELT
    from resileos.ui.residual_frame import motion_scale

    project = dict(brief.get("project") or {})
    scene = next((s for s in project.get("scenes") or [] if s.get("id") == brief.get("scene")), None)
    places = {p.get("id") for p in (project.get("bible") or {}).get("places") or []}
    if scene is None or not scene.get("place") or scene.get("place") not in places:
        return {"status": "UNAVAILABLE", "url": None, "confidence": 0.0,
                "reason": "Muse makes video only from a scene set in a place of this world. "
                          "Words alone are not turned into pictures."}
    env = core.environment(project, seed=brief.get("seed"))
    if not env.get("ok"):
        return {"status": "UNAVAILABLE", "url": None, "confidence": 0.0, "reason": env.get("reason")}
    where = next(p for p in env["places"] if p["id"] == scene["place"])
    big = np.kron(env["map"], np.ones((2, 2, 1)))  # 72 × 72
    side = big.shape[0] * 2 // 3  # 48-pixel window
    room = big.shape[1] - side
    ri, rj = where["region"]
    top = int(min(room, max(0, (ri + 0.5) * big.shape[0] / 3 - side / 2)))
    start = float(min(room, max(0, (rj + 0.5) * big.shape[1] / 3 - side / 2)))
    step = motion_scale()  # the magnetic-phase / φ motion step, as in clip_from_code
    direction = -1.0 if start > room / 2 else 1.0
    seq = []
    for t in range(12):
        x = start + direction * t * step / (2 * math.pi) * side / BELT
        x = min(float(room), max(0.0, x))
        lo = int(math.floor(x))
        frac = x - lo
        a = big[top:top + side, lo:lo + side]
        b = big[top:top + side, min(lo + 1, room):min(lo + 1, room) + side]
        seq.append((1 - frac) * a + frac * b)
    gray = [f.mean(axis=2) for f in seq]
    return {
        "status": "MADE",
        "url": None,
        "evidence": {"frames": [np.round(f, 3) for f in seq], "fps": 8, "scene": scene.get("id"), "place": where["name"],
                     "method": "a slow pan over this world's generated map, starting at the scene's place; "
                               "your words were not turned into pictures",
                     "metrics": {**clip_check_metrics(gray), "phase_band_coherence": phase_band_coherence(seq)},
                     "regions": env["regions"]["grid"]},
        "confidence": 1.0 if env["tiles"]["adjacency_ok"] and env["tiles"]["nested_in_regions"] else 0.0,
    }


def muse(seen: dict[str, Any], *, brief: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
    """Muse: native video and environment generation. Evidence, never facts."""
    brief = dict(brief or {})
    kind = str(brief.get("kind") or "")
    if kind not in MUSE_KINDS:
        return {"status": "NOTHING", "reason": f"unknown Muse brief: {kind!r}", "confidence": 0.0}
    return {"clip": _muse_clip, "environment": _muse_environment, "text_video": _muse_text_video}[kind](brief)


def _muse_ready() -> bool:
    return "muse" in {row["name"] for row in kin_catalogue("apollo")}


def run_muse(
    brief: dict[str, Any],
    *,
    packet: Any = None,
    hades: Any = None,
) -> dict[str, Any]:
    """Call Muse explicitly. Uniform leaf: ControlPacket + brief in,
    evidence + confidence + cost out.

    The budget guard runs first and counts ``seconds`` and ``memory_mb``.
    The run is timed and its peak traced memory measured; both are taken
    off the packet's budget and recorded as ``generative_cost``. A run
    that overspends returns OVER_BUDGET and its evidence is dropped. The
    result is never verified and never a fact. If ``hades`` is given it
    keeps one line, the lesson, and nothing else from this run.
    """
    import time
    import tracemalloc

    from resileos.harness.packet import ControlPacket

    register_studio_legions()
    host = packet if packet is not None else ControlPacket(id=f"muse-{uuid.uuid4().hex[:8]}",
                                                           budget_remaining=dict(MUSE_BUDGET))
    budget = host.budget_remaining if isinstance(host, ControlPacket) else host.setdefault("budget_remaining", dict(MUSE_BUDGET))
    for key in ("seconds", "memory_mb"):
        budget.setdefault(key, MUSE_BUDGET[key])
    guard = budget_and_stuck_guard({"budget_remaining": dict(budget), "history": []})
    if not guard["ok"]:
        return {"status": "OVER_BUDGET", "evidence": None, "confidence": 0.0, "cost": {"seconds": 0.0, "memory_mb": 0.0},
                "verified": False, "is_fact": False, "url": None, "reason": guard["reason"]}
    tracing = tracemalloc.is_tracing()
    if not tracing:
        tracemalloc.start()
    tracemalloc.reset_peak()
    began = time.perf_counter()
    try:
        out = invoke_legion("apollo", "muse", host, brief=brief)
    finally:
        seconds = time.perf_counter() - began
        peak = tracemalloc.get_traced_memory()[1] / (1024 * 1024)
        if not tracing:
            tracemalloc.stop()
    cost = {"seconds": round(seconds, 3), "memory_mb": round(peak, 2)}
    budget["seconds"] = round(float(budget["seconds"]) - seconds, 3)
    budget["memory_mb"] = round(float(budget["memory_mb"]) - peak, 2)
    status = str(out.get("status") or "NOTHING")
    evidence = out.get("evidence")
    if budget["seconds"] < 0 or budget["memory_mb"] < 0:
        status, evidence = "OVER_BUDGET", None
    kind = str(brief.get("kind") or "")
    source = f"muse/native:{kind}"
    evidence_id = _evidence_id(evidence) if evidence is not None else None
    if isinstance(host, ControlPacket):
        host.generative_source, host.generative_cost, host.generative_evidence_id = source, cost, evidence_id
        host.verified = False
    else:
        host.update({"generative_source": source, "generative_cost": cost,
                     "generative_evidence_id": evidence_id, "verified": False})
    lesson = f"muse {kind}: {status.lower()}, confidence {float(out.get('confidence') or 0.0):.2f}, {cost['seconds']:.2f}s"
    if hades is not None and isinstance(host, ControlPacket):
        hades.save(ControlPacket(id=host.id, verified=False), lesson=lesson)
    return {
        "status": status,
        "evidence": evidence,
        "confidence": round(float(out.get("confidence") or 0.0), 4),
        "cost": cost,
        "reason": out.get("reason"),
        "url": out.get("url") if status != "UNAVAILABLE" else None,
        "generative_source": source,
        "generative_evidence_id": evidence_id,
        "lesson": lesson,
        "verified": False,
        "is_fact": False,
        "learned": False,
    }


def register_studio_legions() -> list[str]:
    """Register the Studio legions once. Idempotent."""
    if not _studio_ready():
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
    if not _muse_ready():
        register_legion(
            "apollo",
            muse,
            name="muse",
            constraints={
                "action": "generate studio evidence",
                "writes_residual": False,
                "executes": True,
                "may_set_verified": False,
                "evidence_only": True,
            },
        )
    from resileos.kin.scene_legions import register_scene_legions

    register_scene_legions()
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
    matrix: Any = None,
    frames: list[Any] | None = None,
    residual_packet: dict[str, Any] | None = None,
    learn_fn: Callable[..., Any] | None = None,
    bypass_zeus: bool = False,
    zeus: Any = None,
    previous: Any = None,
    keyframe: Any = None,
    draft: Any = None,
    prediction: str = "previous",
    clip: bool = False,
    sequence: dict[str, Any] | None = None,
    context: list[Any] | None = None,
    clip_history: list[Any] | None = None,
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
        matrix=matrix,
        frames=frames,
        residual_packet=residual_packet,
        control=host,
        learn_fn=learn_fn,
        bypass_zeus=bypass_zeus,
        zeus=zeus,
        previous=previous,
        keyframe=keyframe,
        draft=draft,
        prediction=prediction,
        clip=clip,
        sequence=sequence,
        context=context,
        clip_history=clip_history,
    )
    meta = swarm_meta(host)
    owner = str(meta["attempt_id"]) if meta else str(host.get("id") or "forge")
    if meta is None:
        note_worker(owner, "forge_video", result)
    result["clotho_owner"] = owner
    if not result.get("hades_checkpoint"):
        result["checkpoint"] = None
        result["hades_checkpoint"] = False
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
