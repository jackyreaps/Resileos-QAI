"""Opaque individual identity for persona memory.

Accounts are not on main. Callers pass an account id when they have one,
or a session id when the person is signed out. This module does not look
up credentials. The chat field ``hub_id`` is that opaque id. It is not a
guild hub.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ID = re.compile(r"[^a-z0-9_]")
_ANON = frozenset({"", "anon"})


class PersonaError(ValueError):
    """A persona-store request cannot be applied."""


class OptInRequired(PersonaError):
    """A tier promotion was attempted without an explicit opt-in."""


class NotAMember(PersonaError):
    """The individual has no seat in that guild."""


class PersonalFact(PersonaError):
    """A personal fact cannot be promoted to the latent tier."""


class NotRecurring(PersonaError):
    """The residual does not recur across members."""


class SecretRejected(PersonaError):
    """The text looks like a key or token."""


@dataclass(frozen=True)
class Principal:
    """One individual. ``kind`` is ``account`` or ``session``."""

    kind: str
    id: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "id": self.id}


def normalize_opaque(value: str) -> str:
    """Lowercase ``[a-z0-9_]{1,64}``. A leading ``user:`` is stripped."""
    raw = (value or "").strip().lower()
    if raw.startswith("user:"):
        raw = raw[5:]
    cleaned = _ID.sub("", raw)[:64]
    if not cleaned:
        raise PersonaError("id must contain at least one [a-z0-9_] character")
    return cleaned


def resolve_principal(
    *,
    account_id: str | None = None,
    session_id: str | None = None,
) -> Principal:
    """Account id wins when both are set. ``anon`` is not an individual."""
    if account_id and str(account_id).strip():
        ident = normalize_opaque(str(account_id))
        if ident in _ANON:
            raise PersonaError("anon is not an individual id")
        return Principal("account", ident)
    if session_id and str(session_id).strip():
        ident = normalize_opaque(str(session_id))
        if ident in _ANON:
            raise PersonaError("anon is not an individual id")
        return Principal("session", ident)
    raise PersonaError("account_id or session_id is required")


def principal_from_chat_key(chat_key: str | None) -> Principal | None:
    """Map chat ``hub_id`` to an individual. ``anon`` has no memory."""
    raw = (chat_key or "").strip().lower()
    if raw.startswith("user:"):
        raw = raw[5:]
    if raw in _ANON:
        return None
    try:
        return resolve_principal(account_id=chat_key)
    except PersonaError:
        return None


def bind_authenticated(principal: Principal, authenticated_id: str | None) -> Principal:
    """When a caller supplies an authenticated account id, it must match.

    Until sign-in lands, omit ``authenticated_id`` and the claim is the key.
    """
    if authenticated_id is None or not str(authenticated_id).strip():
        return principal
    claimed = normalize_opaque(str(authenticated_id))
    if principal.kind != "account" or principal.id != claimed:
        raise PersonaError("principal mismatch")
    return principal
