"""Mouth (prose render) gate driven by Metis policy.

Use in /answer after retrieval:

    from resileos.kin.mouth_policy import should_render_prose

    if not should_render_prose(request_render_flag, metrics=...):
        # return structured rows only

When a cycle runs, the harness verification state is checked. An
unverified cycle does not authorize prose: the writer may have produced
output, but the probes that would confirm it either did not run or did
not match anything.

Set `require_verified=False` only if you explicitly want the older
behaviour where any Metis policy authorises prose.
"""
from __future__ import annotations

from typing import Any, Optional

from resileos.kin.wiring import get_kin_bundle, mouth_allowed_from_last_cycle


def should_render_prose(
    client_requested: bool,
    *,
    metrics: Optional[dict[str, Any]] = None,
    agency_group: Any = None,
    run_cycle: bool = False,
    default_if_no_policy: bool = True,
    require_verified: bool = True,
) -> bool:
    """Prose mouth only if client asked AND Metis allows AND cycle verified.

    - client_requested=False → always False (client wants structured only)
    - run_cycle=True: refresh Iris/Metis from metrics, capture the
      resulting harness, and (when require_verified) deny prose if the
      harness reports verified=False.
    - run_cycle=False: read the last cycle's policy. Verification state
      from a prior cycle is not re-checked (no access to it), so the
      previous behaviour is preserved for this path.
    - No policy has ever run and default_if_no_policy=True → allow when
      client asks (backward compatible until the kin cycle is used in
      production).
    """
    if not client_requested:
        return False

    harness: Optional[dict[str, Any]] = None
    if run_cycle:
        try:
            _, _, harness = get_kin_bundle().cycle(
                metrics=metrics or {},
                agency_group=agency_group,
                apply_policy=True,
            )
        except Exception:
            harness = None

        if require_verified:
            if harness is None:
                # Cycle failed entirely; do not authorise prose.
                return False
            if not bool(harness.get("verified", False)):
                # Writer produced output, but the verification gate did
                # not pass (no evidence, zero matches, apollo failure).
                return False

    if get_kin_bundle().last_policy is None:
        return bool(default_if_no_policy)

    return mouth_allowed_from_last_cycle(default=False)


__all__ = ["should_render_prose"]
