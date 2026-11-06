"""
Wire kin routes + optional declining kin onto an existing Titanos / FastAPI app.

Call once after titanos_singleton and Zeus registration:

    from resileos.kin.wiring import wire_kin
    wire_kin(app, titanos_singleton, auth_dep=verify_api_key)
"""
from __future__ import annotations

from typing import Any, Optional

from resileos.kin.bundle import (
    KinBundle,
    build_kin_bundle,
    register_declining_kin,
)
from resileos.kin.http_routes import register_kin_routes

# Process-wide bundle (one per worker)
_BUNDLE: Optional[KinBundle] = None


def get_kin_bundle() -> KinBundle:
    global _BUNDLE
    if _BUNDLE is None:
        _BUNDLE = build_kin_bundle()
    return _BUNDLE


def wire_kin(
    app: Any,
    titanos: Any,
    *,
    auth_dep: Any = None,
    register_side_handlers: bool = True,
    side_weight: float = 0.01,
) -> KinBundle:
    """
    - build KinBundle
    - optional register iris/metis/hermes as declining AgencyGroup children
    - mount POST /api/v1/eat, /eat/preview, /kin/cycle
    """
    bundle = get_kin_bundle()
    agency = getattr(titanos, "agency", None)
    if register_side_handlers and agency is not None:
        try:
            register_declining_kin(agency, bundle, weight=side_weight)
        except ValueError:
            # already registered (reload)
            pass

    def _metrics() -> dict:
        return {}

    def _agency() -> Any:
        return getattr(titanos, "agency", None)

    register_kin_routes(
        app,
        get_titanos=lambda: titanos,
        auth_dep=auth_dep,
        get_bundle=get_kin_bundle,
        get_metrics=_metrics,
        get_agency=_agency,
    )
    return bundle


def mouth_allowed_from_last_cycle(default: bool = False) -> bool:
    """Read MetisPolicy.allow_mouth from last KinBundle.cycle, if any."""
    b = get_kin_bundle()
    if b.last_policy is None:
        return default
    return bool(b.last_policy.allow_mouth)
