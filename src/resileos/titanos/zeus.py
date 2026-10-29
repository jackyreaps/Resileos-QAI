"""Zeus agency child (RES-324).

An AgencyChild (RES-307) that composes structured answers from a
Titanos store and declines when the substrate field is unlocked.

The handler signature is fixed by RES-307:

    HandlerFn = Callable[[Any, str, str, bool], Any]

i.e. `handler(parent, subject, relation, inverse) -> Answer | None`.
`parent` is the caller's Titanos instance. Zeus uses `parent.ask`,
`parent.ask_inverse`, and `parent.chain`. It returns whatever those
methods return, or `None` to decline.

Mode A (structured composer) is the whole of this module. Mode B
(carrier-modulated prose via RES-315) is reserved for the RES-315
experiment and not implemented here. If a `carrier` object is passed
to `make_zeus_handler`, it is stored on the closure for future use
but not called.

Off states (explicit):
    generation      off. Zeus composes structured answers, not prose.
    truth claim     off. Zeus returns whatever the parent's structured
                    lookup returns.
    carrier mode    off. Reserved for RES-315.
    fitness update  off. The agency group handles this via record().
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


# ── config ──────────────────────────────────────────────────────────────
@dataclass
class ZeusConfig:
    """Zeus behavior thresholds.

    r_decline_threshold   R below which Zeus declines; parent answers
    max_hops              max composite relation length
    """
    r_decline_threshold: float = 0.3
    max_hops: int = 4

    def __post_init__(self) -> None:
        self.r_decline_threshold = float(self.r_decline_threshold)
        self.max_hops = int(self.max_hops)
        if not (0.0 <= self.r_decline_threshold <= 1.0):
            raise ValueError(
                f"r_decline_threshold must be in [0, 1], got "
                f"{self.r_decline_threshold}"
            )
        if self.max_hops < 1:
            raise ValueError("max_hops must be >= 1")


# ── handler factory ─────────────────────────────────────────────────────
def make_zeus_handler(
    *,
    composite_relations: Optional[dict[str, list[str]]] = None,
    field_R_fn: Optional[Callable[[], float]] = None,
    stream: Any = None,
    stack: Any = None,
    carrier: Any = None,
    cfg: Optional[ZeusConfig] = None,
) -> Callable[[Any, str, str, bool], Any]:
    """Build a Zeus handler that fits the RES-307 HandlerFn contract.

    Args:
        composite_relations   map relation-name -> list of hops. If a
                              request's relation matches a key and the
                              request is not inverse, Zeus runs
                              parent.chain(subject, hops). Otherwise it
                              runs parent.ask / parent.ask_inverse.
        field_R_fn            callable returning the current R. If None,
                              Zeus treats the field as locked (R=1.0) and
                              never declines on the R gate.
        stream                optional StreamState. Reserved for Mode B.
        stack                 optional MaskStack. Reserved for Mode B.
        carrier               optional carrier MLP. Reserved for Mode B;
                              stored on the closure but not called.
        cfg                   ZeusConfig. Defaults are in ZeusConfig.

    Returns:
        A handler(parent, subject, relation, inverse) -> Answer | None.
    """
    composite = dict(composite_relations) if composite_relations else {}
    config = cfg or ZeusConfig()

    def handler(
        parent: Any, subject: str, relation: str, inverse: bool
    ) -> Any:
        # 0. Sector policy (Tier A). Parent may set _route_sector.
        #    On gbx_like, decline cheaply so fitness still records a
        #    query while exact band stays on the parent path.
        sector = str(getattr(parent, "_route_sector", "") or "")
        if sector == "gbx_like" and not inverse and not relation.endswith("_of"):
            return None

        # 1. R gate. If the field is unlocked, decline so the parent
        #    handles the request without context. This is Zeus's
        #    strongest correctness guard: declining keeps Zeus out of
        #    queries whose context would be crosstalk.
        if field_R_fn is not None:
            try:
                R_now = float(field_R_fn())
            except Exception:
                R_now = 0.0
            if R_now < config.r_decline_threshold:
                return None

        # 2. Composite relation: expand to a chain.
        if relation in composite and not inverse:
            hops = list(composite[relation])
            if not (1 <= len(hops) <= config.max_hops):
                return None
            try:
                return parent.chain(subject, hops)
            except Exception:
                return None

        # 3. Fallback: single-hop lookup.
        try:
            if inverse:
                return parent.ask_inverse(subject, relation)
            return parent.ask(subject, relation)
        except Exception:
            return None

    # Closure metadata, for inspection and future use.
    handler.__zeus_composite__ = composite
    handler.__zeus_field_R_fn__ = field_R_fn
    handler.__zeus_stream__ = stream
    handler.__zeus_stack__ = stack
    handler.__zeus_carrier__ = carrier
    handler.__zeus_cfg__ = config

    return handler


# ── call loop helper ────────────────────────────────────────────────────
def run_zeus_query(
    group,
    parent: Any,
    subject: str,
    relation: str,
    inverse: bool = False,
    csi_fn: Optional[Callable[[], float]] = None,
    prune: bool = False,
) -> Any:
    """Run one query through the agency group's select -> invoke ->
    record -> (optional) prune loop.

    AgencyGroup does not wrap this loop internally; the caller is
    expected to do select/handler/record/prune manually. This helper
    makes the correct sequence hard to get wrong.

    Args:
        group      AgencyGroup instance
        parent     the value passed to the selected child's handler as
                   its first argument (typically the Titanos instance)
        subject    query subject
        relation   query relation
        inverse    query direction
        csi_fn     optional callable returning the current CSI. Used to
                   update the selected child's fitness. If None,
                   csi=1.0 is recorded.
        prune      if True, call group.evaluate_and_prune() after the
                   record.

    Returns:
        The Answer from the selected child, or None if no child was
        selected or the selected child declined.
    """
    child = group.select()
    if child is None:
        return None

    try:
        answer = child.handler(parent, subject, relation, inverse)
    except Exception:
        answer = None

    accepted = answer is not None
    csi = float(csi_fn()) if csi_fn is not None else 1.0
    group.record(child.name, csi=csi, accepted=accepted)

    if prune:
        group.evaluate_and_prune()

    return answer


__all__ = [
    "ZeusConfig",
    "make_zeus_handler",
    "run_zeus_query",
]
