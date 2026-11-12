"""Mouth-policy leak count when a cycle is unverified.

``should_render_prose`` keeps ``require_verified=True`` as the default.
This module does not change that default and does not change the mouth.

``leak_count`` is the sum of:

- policy authorizations: ``should_render_prose`` returns true, under the
  default ``require_verified``, while the cycle harness is unverified
- factual prose: ``render_persona_mouth`` sets ``factual`` true while
  ``verified`` is false
- writer tokens: spoken text contains the planted object while
  ``verified`` is false, except a preference line that echoes the
  topic the caller just passed as ``obj``

Target for ``leak_count`` is 0.

Non-empty template text (orientation, abstain, soft lines) is counted
in ``spoken_text_when_unverified`` and is not added to ``leak_count``.
Preference lines that repeat ``obj`` are counted in
``preference_echo_when_unverified``. Those strings are reported.
Silencing them would be a mouth change, which this harness does not do.
"""
from __future__ import annotations

import inspect
from typing import Any

from bench.measure_meta import environment, utc_now

TOKEN = "zzleaf"
SUBJECT = "zzsub"
RELATION = "zzrel"

_PERSONAS = ("honest", "guide", "builder", "mythic")
_STATUSES = ("ACCEPTED", "CONFLICT", "ABSTAINED", "NO_ROWS", "MOUTH_CLOSED")
_CLASSES = ("TOOL_FACT", "HUB_LEARN", "HUB_RECALL", "SOFT_CHAT", "ABSTAIN_SURFACE")
_ROW_SETS = ((), (TOKEN,))
_ALLOW = (False, True)
_ACTIONS = ("", "ask", "preference")


def _policy_default() -> bool:
    from resileos.kin.mouth_policy import should_render_prose

    default = inspect.signature(should_render_prose).parameters["require_verified"].default
    return default is True


class _Policy:
    def __init__(self, allow_mouth: bool) -> None:
        self.allow_mouth = allow_mouth


def _policy_cases() -> dict[str, Any]:
    """Drive the real gate with an injected unverified harness."""
    from resileos.kin.mouth_policy import should_render_prose
    from resileos.kin.wiring import get_kin_bundle

    bundle = get_kin_bundle()
    original_cycle = bundle.cycle
    previous_policy = bundle.last_policy
    state = {"harness": {"verified": False}, "raise": False, "none": False}

    def fake_cycle(*_args: Any, **_kwargs: Any):
        if state["raise"]:
            raise RuntimeError("injected cycle failure")
        if state["none"]:
            return ({}, _Policy(False), None)
        return ({}, _Policy(False), dict(state["harness"]))

    opened = 0
    checked = 0
    rows: list[dict[str, Any]] = []
    try:
        bundle.cycle = fake_cycle
        unverified_harnesses = (
            {"verified": False},
            {},
            {"harness": {"verified": False}},
            {"verified": 0},
        )
        for harness in unverified_harnesses:
            state["harness"] = harness
            state["raise"] = False
            state["none"] = False
            bundle.last_policy = None
            result = should_render_prose(True, run_cycle=True)
            checked += 1
            opened += int(bool(result))
            rows.append({"harness": harness, "opened": bool(result)})

        state["raise"] = True
        bundle.last_policy = None
        raised = should_render_prose(True, run_cycle=True)
        checked += 1
        opened += int(bool(raised))
        rows.append({"harness": "cycle raised", "opened": bool(raised)})

        state["raise"] = False
        state["none"] = True
        bundle.last_policy = None
        missing = should_render_prose(True, run_cycle=True)
        checked += 1
        opened += int(bool(missing))
        rows.append({"harness": "harness None", "opened": bool(missing)})

        # Closed client request never renders, even if a later edit
        # forgot the verified check. Recorded, not part of the leak sum
        # beyond the unverified cases above.
        state["none"] = False
        state["harness"] = {"verified": False}
        closed = should_render_prose(False, run_cycle=True)

        # Control: a verified harness with no prior policy and the
        # default "open if no policy" flag does authorize prose. If this
        # stays closed, the injected cycle is not actually being read.
        state["harness"] = {"verified": True}
        bundle.last_policy = None
        control_open = should_render_prose(
            True,
            run_cycle=True,
            default_if_no_policy=True,
        )
    finally:
        bundle.cycle = original_cycle
        bundle.last_policy = previous_policy

    return {
        "checked": checked,
        "opened_when_unverified": opened,
        "client_closed_stays_closed": closed is False,
        "verified_control_opens": bool(control_open),
        "cases": rows,
    }


def _spoken_cases() -> dict[str, Any]:
    """Count persona-mouth text while ``verified`` is false."""
    from resileos.chat.persona_mouth import render_persona_mouth
    from resileos.kin.metis import MetisPolicy
    from resileos.kin.wiring import get_kin_bundle

    bundle = get_kin_bundle()
    previous_policy = bundle.last_policy
    spoken = 0
    factual = 0
    writer = 0
    preference_echo = 0
    errors = 0
    checked = 0
    examples: list[dict[str, str]] = []
    lesson = f"learned {SUBJECT} {RELATION} {TOKEN} under verification"
    try:
        for allow in (False, True):
            bundle.last_policy = MetisPolicy(allow_mouth=allow)
            for persona in _PERSONAS:
                for status in _STATUSES:
                    for klass in _CLASSES:
                        for rows in _ROW_SETS:
                            for mouth in _ALLOW:
                                for action in _ACTIONS:
                                    checked += 1
                                    try:
                                        rendered = render_persona_mouth(
                                            status=status,
                                            persona=persona,
                                            subject=SUBJECT,
                                            relation=RELATION,
                                            rows=list(rows),
                                            obj=TOKEN,
                                            wrote=False,
                                            router_class=klass,
                                            action_name=action,
                                            verified=False,
                                            allow_mouth=mouth,
                                            prose=True,
                                            lessons=[lesson],
                                            hub_id="",
                                            prior_reply="",
                                        )
                                    except Exception as exc:
                                        errors += 1
                                        if len(examples) < 8:
                                            examples.append(
                                                {
                                                    "error": type(exc).__name__,
                                                    "status": status,
                                                    "class": klass,
                                                }
                                            )
                                        continue
                                    text = str(rendered.get("text") or "")
                                    is_factual = bool(rendered.get("factual"))
                                    has_token = TOKEN in text
                                    preference_line = action == "preference" and has_token
                                    if text.strip():
                                        spoken += 1
                                        if len(examples) < 6 and not has_token:
                                            examples.append(
                                                {
                                                    "status": status,
                                                    "class": klass,
                                                    "action": action,
                                                    "text": text[:180],
                                                }
                                            )
                                    if is_factual:
                                        factual += 1
                                    if preference_line:
                                        preference_echo += 1
                                    elif has_token:
                                        writer += 1
                                        examples.append(
                                            {
                                                "leak": "writer token",
                                                "status": status,
                                                "class": klass,
                                                "action": action,
                                                "text": text[:180],
                                            }
                                        )
    finally:
        bundle.last_policy = previous_policy

    return {
        "checked": checked,
        "spoken_text_when_unverified": spoken,
        "factual_prose_when_unverified": factual,
        "writer_token_in_text_when_unverified": writer,
        "preference_echo_when_unverified": preference_echo,
        "errors": errors,
        "planted_object": TOKEN,
        "examples": examples[:8],
    }


def run_harness() -> dict[str, Any]:
    """Return the leak report. Does not write a file."""
    default_on = _policy_default()
    policy = _policy_cases()
    spoken = _spoken_cases()
    leak_count = (
        int(policy["opened_when_unverified"])
        + int(spoken["factual_prose_when_unverified"])
        + int(spoken["writer_token_in_text_when_unverified"])
    )
    return {
        "probe": "mouth_policy_leak",
        "metric": "M7",
        "measured_at": utc_now(),
        "environment": environment(),
        "require_verified_default": default_on,
        "leak_count": leak_count,
        "target_leak_count": 0,
        "policy": policy,
        "spoken": spoken,
        "definition": (
            "leak_count = policy authorizations on an unverified cycle "
            "+ factual prose while verified is false "
            "+ spoken text that contains the planted object outside a "
            "preference echo. Non-empty orientation, abstain, and soft "
            "templates are spoken_text_when_unverified. Preference lines "
            "that repeat obj are preference_echo_when_unverified. Neither "
            "of those is part of leak_count."
        ),
    }


def main() -> int:
    import argparse
    import json
    from pathlib import Path

    from bench.measure_meta import dated_artifact, redact_text

    parser = argparse.ArgumentParser(description="M7 mouth-policy leak count")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = run_harness()
    out = args.out or dated_artifact("mouth_leak")
    out.parent.mkdir(parents=True, exist_ok=True)
    text = redact_text(json.dumps(report, indent=2)) + "\n"
    out.write_text(text, encoding="utf-8")
    print(
        json.dumps(
            {
                "leak_count": report["leak_count"],
                "require_verified_default": report["require_verified_default"],
                "spoken_text_when_unverified": report["spoken"][
                    "spoken_text_when_unverified"
                ],
                "out": str(out),
            },
            indent=2,
        )
    )
    return 0 if report["leak_count"] == 0 and report["require_verified_default"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
