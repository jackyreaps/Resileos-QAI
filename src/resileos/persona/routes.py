"""HTTP surface for the persona store.

Models are defined inside ``register_persona_routes`` so FastAPI treats
them as JSON bodies. No postponed annotations in this module.
"""
from typing import Any, Optional


def register_persona_routes(app: Any, auth_dep: Optional[Any] = None) -> None:
    """Mount ``/api/v1/persona/*``. Does not call Titanos learn."""
    try:
        from fastapi import Depends, Header, HTTPException, Query
        from pydantic import BaseModel
    except ImportError as exc:
        raise ImportError("fastapi required to register persona routes") from exc

    from resileos.persona.principal import (
        NotAMember,
        NotRecurring,
        OptInRequired,
        PersonaError,
        PersonalFact,
        SecretRejected,
        bind_authenticated,
    )
    from resileos.persona.reflect import principal_for_api, recall_packet
    from resileos.persona.store import get_persona_store, guild_subject

    deps = [Depends(auth_dep)] if auth_dep is not None else []

    class FactBody(BaseModel):
        text: str
        kind: str = "stated"
        personal: Optional[bool] = None

    class SeatBody(BaseModel):
        moniker: str
        account_id: str
        rank: str = "member"
        kind: str = "account"

    class PromoteBody(BaseModel):
        account_id: Optional[str] = None
        session_id: Optional[str] = None
        guild_id: str
        fact_id: str
        to: str = "hub"
        opt_in: bool = False

    def _fail(exc: PersonaError) -> None:
        if isinstance(exc, NotAMember):
            raise HTTPException(403, str(exc)) from exc
        if isinstance(exc, (OptInRequired, PersonalFact, NotRecurring, SecretRejected)):
            raise HTTPException(400, str(exc)) from exc
        message = str(exc)
        if message == "principal mismatch":
            raise HTTPException(403, message) from exc
        raise HTTPException(400, message) from exc

    def _who(
        account_id: Optional[str],
        session_id: Optional[str],
        authenticated: Optional[str],
    ):
        try:
            principal = principal_for_api(account_id=account_id, session_id=session_id)
            return bind_authenticated(principal, authenticated)
        except PersonaError as exc:
            _fail(exc)

    @app.get("/api/v1/persona/self", dependencies=deps)
    def api_persona_self() -> dict:
        store = get_persona_store()
        seed = store.seed()
        return {
            "version": seed.version,
            "updated": seed.updated,
            "facts": seed.public_rows(),
            "tutorial": seed.tutorial_rows(),
            "latent": store.latent_hub().read("all"),
            "frame": store.latent_stored_frame(),
            "meta_aware_root": store.reflection.root.self_check(),
            "writes_titanos": False,
        }

    @app.get("/api/v1/persona/individual", dependencies=deps)
    def api_persona_list(
        account_id: Optional[str] = Query(None),
        session_id: Optional[str] = Query(None),
        x_resileos_account: Optional[str] = Header(None),
    ) -> dict:
        principal = _who(account_id, session_id, x_resileos_account)
        store = get_persona_store()
        record = store.load_individual(principal)
        return {
            "principal": principal.to_dict(),
            "expires_at": record.expires_at,
            "stated": store.list_stated(principal),
            "residual": store.list_residual(principal),
            "frame": record.frame,
            "writes_titanos": False,
            "writes_residual_core": False,
        }

    @app.put("/api/v1/persona/individual/{fact_id}", dependencies=deps)
    def api_persona_put(
        fact_id: str,
        body: FactBody,
        account_id: Optional[str] = Query(None),
        session_id: Optional[str] = Query(None),
        x_resileos_account: Optional[str] = Header(None),
    ) -> dict:
        principal = _who(account_id, session_id, x_resileos_account)
        try:
            cell = get_persona_store().put_stated(
                principal,
                fact_id,
                body.text,
                kind=body.kind,
                personal=body.personal,
            )
        except PersonaError as exc:
            _fail(exc)
        return {"fact": cell, "writes_titanos": False, "writes_residual_core": False}

    @app.delete("/api/v1/persona/individual/{fact_id}", dependencies=deps)
    def api_persona_delete(
        fact_id: str,
        account_id: Optional[str] = Query(None),
        session_id: Optional[str] = Query(None),
        x_resileos_account: Optional[str] = Header(None),
    ) -> dict:
        principal = _who(account_id, session_id, x_resileos_account)
        removed = get_persona_store().delete_stated(principal, fact_id)
        if not removed:
            raise HTTPException(404, "no user-stated fact with that id")
        return {"deleted": True, "writes_titanos": False, "writes_residual_core": False}

    @app.get("/api/v1/persona/recall", dependencies=deps)
    def api_persona_recall(
        account_id: Optional[str] = Query(None),
        session_id: Optional[str] = Query(None),
    ) -> dict:
        key = account_id or session_id or ""
        return recall_packet(key)

    @app.get("/api/v1/persona/hub/{guild_id}", dependencies=deps)
    def api_persona_hub(
        guild_id: str,
        account_id: Optional[str] = Query(None),
        session_id: Optional[str] = Query(None),
        x_resileos_account: Optional[str] = Header(None),
    ) -> dict:
        principal = _who(account_id, session_id, x_resileos_account)
        try:
            return get_persona_store().read_hub(guild_id, principal)
        except PersonaError as exc:
            _fail(exc)

    @app.post("/api/v1/persona/hub/{guild_id}/seat", dependencies=deps)
    def api_persona_seat(guild_id: str, body: SeatBody) -> dict:
        try:
            seat = get_persona_store().seat_member(
                guild_id,
                body.moniker,
                body.account_id,
                rank=body.rank,
                kind=body.kind,
            )
        except PersonaError as exc:
            _fail(exc)
        return {
            "seat": seat,
            "subject": guild_subject(guild_id),
            "writes_titanos": False,
        }

    @app.post("/api/v1/persona/promote", dependencies=deps)
    def api_persona_promote(
        body: PromoteBody,
        x_resileos_account: Optional[str] = Header(None),
    ) -> dict:
        principal = _who(body.account_id, body.session_id, x_resileos_account)
        store = get_persona_store()
        try:
            if body.to == "latent":
                return store.promote_to_latent(
                    principal, body.guild_id, body.fact_id, opt_in=body.opt_in
                )
            if body.to != "hub":
                raise PersonaError("promote to hub or latent")
            return store.promote_to_hub(
                principal, body.guild_id, body.fact_id, opt_in=body.opt_in
            )
        except PersonaError as exc:
            _fail(exc)
