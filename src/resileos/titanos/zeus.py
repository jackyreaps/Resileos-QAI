"""Zeus agency child (RES-324).

An AgencyChild (RES-307) that composes structured answers from a
Titanos store and declines when the substrate field is unlocked.

The handler signature is fixed by RES-307:

    HandlerFn = Callable[[Any, str, str, bool], Any]

i.e. `handler(parent, subject, relation, inverse) -> Answer | None`.
`parent` is the caller's Titanos instance. Zeus uses `parent.ask`,
`parent.ask_inverse`, and `parent.chain`. It returns whatever those
methods return, or `None` to decline.

Temporal (RES-332): `run_zeus_query` accepts `as_of` and sets
`parent._route_as_of` around the handler call. The handler reads that
attribute and threads it into `parent.ask` / `parent.ask_inverse`.
`parent.chain` is called with `as_of=` only if its signature accepts
it; otherwise called without, so chain temporal support can be added
independently.

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

import inspect
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
                              Zeus treats the field as locked (R=1.0)
                              and never declines on the R gate.
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

    # Chain signature cached once; used to decide whether to pass as_of.
    try:
        _chain_accepts_as_of = "as_of" in inspect.signature(
            _dummy_chain_signature
        ).parameters
    except Exception:
        _chain_accepts_as_of = False

    def _call_chain(parent, subject, hops, as_of):
        """Call parent.chain, passing as_of if the method accepts it."""
        try:
            if "as_of" in inspect.signature(parent.chain).parameters:
                return parent.chain(subject, hops, as_of=as_of)
        except (TypeError, ValueError):
            pass
        return parent.chain(subject, hops)

    def handler(
        parent: Any, subject: str, relation: str, inverse: bool
    ) -> Any:
        # Temporal: read as_of from parent context if set by run_zeus_query.
        as_of = getattr(parent, "_route_as_of", None)

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
                return _call_chain(parent, subject, hops, as_of)
            except Exception:
                return None

        # 3. Fallback: single-hop lookup with as_of threaded.
        try:
            if inverse:
                return parent.ask_inverse(subject, relation, as_of=as_of)
            return parent.ask(subject, relation, as_of=as_of)
        except TypeError:
            # ask() does not accept as_of in this build; call without.
            try:
                if inverse:
                    return parent.ask_inverse(subject, relation)
                return parent.ask(subject, relation)
            except Exception:
                return None
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


def _dummy_chain_signature(as_of: Optional[str] = None) -> None:
    """Placeholder used only for signature reflection at import time."""
    return None


# ── call loop helper ────────────────────────────────────────────────────
def run_zeus_query(
    group,
    parent: Any,
    subject: str,
    relation: str,
    inverse: bool = False,
    csi_fn: Optional[Callable[[], float]] = None,
    prune: bool = False,
    as_of: Optional[str] = None,
) -> Any:
    """Run one query through the agency group's select -> invoke ->
    record -> (optional) prune loop.

    Temporal (RES-332): `as_of` is set on `parent._route_as_of` around
    the handler call so Zeus can thread it into parent.ask /
    parent.ask_inverse. The previous value is restored in a finally
    block, so nested or re-entrant calls are safe.

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
        as_of      ISO 8601 date string, or None = today, or "" = full
                   historical log.

    Returns:
        The Answer from the selected child, or None if no child was
        selected or the selected child declined.
    """
    child = group.select()
    if child is None:
        return None

    prev_as_of = getattr(parent, "_route_as_of", None)
    parent._route_as_of = as_of

    try:
        answer = child.handler(parent, subject, relation, inverse)
    except Exception:
        answer = None
    finally:
        parent._route_as_of = prev_as_of

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
