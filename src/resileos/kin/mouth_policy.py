"""
Mouth (prose render) gate driven by Metis policy.

Use in /answer after retrieval:

    from resileos.kin.mouth_policy import should_render_prose
    if not should_render_prose(request_render_flag, metrics=...):
        # return structured rows only
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
) -> bool:
    """
    Prose mouth only if client asked AND Metis allows (when policy exists).

    If run_cycle=True, refresh Iris/Metis from metrics first.
    If no cycle has run and default_if_no_policy=True, allow when client asks
    (backward compatible until kin cycle is used in production).
    """
    if not client_requested:
        return False
    if run_cycle:
        get_kin_bundle().cycle(
            metrics=metrics or {},
            agency_group=agency_group,
            apply_policy=True,
        )
    if get_kin_bundle().last_policy is None:
        return bool(default_if_no_policy)
    return mouth_allowed_from_last_cycle(default=False)
