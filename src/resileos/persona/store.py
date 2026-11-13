"""Persona store: individual, guild hub, and latent tiers.

The individual tier is private memory. The hub tier is one chartered
guild (``org:guild:<id>``), not the per-user store. The latent tier is
the shared frame above guilds. It starts from the self-facts seed.

Each lower frame is the residual against the frame above it: a cell is
kept only when its text differs. Promotion is opt-in at each step.
Personal facts can be shared into a guild the member belongs to. They
do not move to latent.

This module does not import Titanos or ResidualCore.
"""
from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from resileos.persona.principal import (
    NotAMember,
    NotRecurring,
    OptInRequired,
    PersonaError,
    PersonalFact,
    Principal,
    SecretRejected,
    normalize_opaque,
)
from resileos.persona.reflection import (
    FrameReflection,
    ReflectionVerdict,
    StoredFrame,
    hub_frame,
    individual_frame,
    latent_frame,
)
from resileos.persona.residual import compose, difference
from resileos.persona.seed import LABEL_SEED, SelfFacts, load_self_facts

LABEL_USER = "user-stated"
LABEL_HUB = "hub-shared"
LABEL_LATENT = "latent-promoted"

# RS-INF-003 default ladder. Local rank labels, not network office.
GUILD_RANKS = ("initiate", "member", "journeyman", "senior", "steward")
ALWAYS_PERSONAL = frozenset({"name", "goal", "skill", "preference", "stated", "tutorial"})
FACT_KINDS = ALWAYS_PERSONAL | frozenset({"shared"})

_FACT_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SECRET = re.compile(
    r"(?i)(api[_-]?key\b|\bbearer\s+\S|\bx-api-key\b|\bsk-[A-Za-z0-9]{8,})"
)
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
_OPAQUE_TOKEN = re.compile(r"^[A-Za-z0-9_\-]{40,}$")

_STORE: PersonaStore | None = None


def reject_secret(text: str) -> None:
    raw = (text or "").strip()
    if _SECRET.search(raw) or _HEX64.fullmatch(raw) or _OPAQUE_TOKEN.fullmatch(raw):
        raise SecretRejected("persona memory does not store keys")


def _as_frame(value: StoredFrame | dict | None, default: StoredFrame) -> StoredFrame:
    if value is None:
        return default
    if isinstance(value, StoredFrame):
        return value
    return StoredFrame.from_dict(value)


def _abstain_promotion(tier: str, fact_id: str, gate: dict) -> dict[str, Any]:
    """Collapse refuses the write. Abstain is not a failure."""
    return {
        "tier": tier,
        "stored": False,
        "status": "ABSTAINED",
        "failure": False,
        "fact_id": fact_id,
        "opt_in": True,
        "reason": gate.get("reason") or "",
        "reflection": gate,
        "writes_titanos": False,
        "writes_residual_core": False,
        "scores_beliefs": False,
    }


def guild_subject(guild_id: str) -> str:
    """Same subject shape as ``resileos.answer.guild.guild_subject``."""
    return f"org:guild:{normalize_opaque(guild_id)}"


def _now(clock: Callable[[], datetime]) -> datetime:
    moment = clock()
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.isoformat()


def _parse_stamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


@dataclass
class IndividualRecord:
    kind: str
    id: str
    expires_at: str | None = None
    stated: dict[str, dict] = field(default_factory=dict)
    residual: dict[str, dict] = field(default_factory=dict)
    frame: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "expires_at": self.expires_at,
            "stated": self.stated,
            "residual": self.residual,
            "frame": self.frame,
            "writes_titanos": False,
            "writes_residual_core": False,
        }


@dataclass
class GuildRecord:
    guild_id: str
    subject: str
    charter_ref: str = "GS-CHR-010"
    compact_ref: str = "GS-FND-002"
    frame_profile_ref: str = "meta.frame_profile"
    seats: list[dict] = field(default_factory=list)
    residual: dict[str, dict] = field(default_factory=dict)
    frame: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "guild_id": self.guild_id,
            "subject": self.subject,
            "charter_ref": self.charter_ref,
            "compact_ref": self.compact_ref,
            "frame_profile_ref": self.frame_profile_ref,
            "seats": self.seats,
            "residual": self.residual,
            "frame": self.frame,
            "writes_titanos": False,
            "writes_residual_core": False,
        }


class LatentHubRead:
    """Read the persona latent residual. This is not ``resileos.latent_hub``.

    The language hub (``LatentHub.put`` / ``get`` / ``nearest``) stores
    hypervectors. It is not a fact store and it scores similarity, so
    persona frames never go through it. ``read(scope)`` returns seed and
    promoted rows ``{id, text, label, source}`` from this store only.
    """

    def __init__(self, store: PersonaStore) -> None:
        self._store = store

    def read(self, scope: str = "self") -> list[dict[str, str]]:
        return self._store.read_latent(scope)


class PersonaStore:
    def __init__(
        self,
        root: str | Path,
        *,
        seed_path: str | Path | None = None,
        clock: Callable[[], datetime] | None = None,
        session_ttl_s: int | None = None,
        reflection: FrameReflection | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._seed_path = seed_path
        self._seed: SelfFacts | None = None
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        ttl = session_ttl_s
        if ttl is None:
            raw = os.environ.get("RESILEOS_PERSONA_SESSION_TTL_S", "86400")
            try:
                ttl = int(raw)
            except ValueError:
                ttl = 86400
        self.session_ttl_s = max(1, int(ttl))
        self.reflection = reflection or FrameReflection()
        self._lock = threading.Lock()
        self.writes_titanos = False
        self.writes_residual_core = False

    def seed(self) -> SelfFacts:
        if self._seed is None:
            self._seed = load_self_facts(self._seed_path)
        return self._seed

    def set_frame_reflection(self, reflection: FrameReflection) -> None:
        """Install a later gnosis implementation. The default stays a count."""
        self.reflection = reflection

    def latent_hub(self) -> LatentHubRead:
        return LatentHubRead(self)

    def _atomic(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)

    def _individual_path(self, principal: Principal) -> Path:
        return self.root / "individuals" / principal.kind / f"{principal.id}.json"

    def _guild_path(self, guild_id: str) -> Path:
        return self.root / "guilds" / f"{normalize_opaque(guild_id)}.json"

    def _latent_path(self) -> Path:
        return self.root / "latent" / "promoted.json"

    def _load_promoted(self) -> dict[str, dict]:
        path = self._latent_path()
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        cells = raw.get("residual") if isinstance(raw, dict) else None
        return dict(cells or {})

    def _save_promoted(self, residual: dict[str, dict], frame: dict | None = None) -> None:
        self._atomic(
            self._latent_path(),
            {
                "residual": residual,
                "frame": frame if frame is not None else latent_frame().to_dict(),
                "writes_titanos": False,
            },
        )

    def latent_stored_frame(self) -> dict:
        path = self._latent_path()
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = {}
            if isinstance(raw, dict) and isinstance(raw.get("frame"), dict) and raw["frame"]:
                return raw["frame"]
        return latent_frame().to_dict()

    def latent_frame(self) -> dict[str, dict]:
        """Seed plus opt-in promoted residuals. No individual stated facts."""
        return compose(self.seed().latent_frame(), self._load_promoted())

    def read_latent(self, scope: str = "self") -> list[dict[str, str]]:
        seed_rows = [
            {
                "id": row["id"],
                "text": row["text"],
                "label": LABEL_SEED,
                "source": f"seed:{row['check']}",
            }
            for row in (*self.seed().facts, *self.seed().tutorial)
        ]
        promoted = [
            {
                "id": cell["id"],
                "text": cell["text"],
                "label": LABEL_LATENT,
                "source": str(cell.get("source") or "opt-in:hub"),
            }
            for cell in self._load_promoted().values()
            if not cell.get("personal")
        ]
        if scope == "self":
            return seed_rows
        if scope == "promoted":
            return promoted
        if scope == "all":
            return seed_rows + promoted
        raise PersonaError(f"unknown latent scope {scope}")

    def _load_guild(self, guild_id: str) -> GuildRecord | None:
        path = self._guild_path(guild_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        ident = normalize_opaque(guild_id)
        return GuildRecord(
            guild_id=ident,
            subject=str(raw.get("subject") or guild_subject(ident)),
            charter_ref=str(raw.get("charter_ref") or "GS-CHR-010"),
            compact_ref=str(raw.get("compact_ref") or "GS-FND-002"),
            frame_profile_ref=str(raw.get("frame_profile_ref") or "meta.frame_profile"),
            seats=list(raw.get("seats") or []),
            residual=dict(raw.get("residual") or {}),
            frame=dict(raw.get("frame") or hub_frame(ident).to_dict()),
        )

    def _save_guild(self, record: GuildRecord) -> None:
        self._atomic(self._guild_path(record.guild_id), record.to_dict())

    def open_guild(self, guild_id: str, *, charter_ref: str = "GS-CHR-010") -> GuildRecord:
        """Record a guild seat file. Does not call ``join_guild`` or ``learn``."""
        ident = normalize_opaque(guild_id)
        with self._lock:
            existing = self._load_guild(ident)
            if existing is not None:
                return existing
            record = GuildRecord(
                guild_id=ident,
                subject=guild_subject(ident),
                charter_ref=charter_ref or "GS-CHR-010",
                frame=hub_frame(ident).to_dict(),
            )
            self._save_guild(record)
            return record

    def seat_member(
        self,
        guild_id: str,
        moniker: str,
        individual_id: str,
        *,
        rank: str = "member",
        kind: str = "account",
    ) -> dict[str, str]:
        if rank not in GUILD_RANKS:
            raise PersonaError(f"unknown rank {rank}")
        if kind not in {"account", "session"}:
            raise PersonaError("seat kind must be account or session")
        seat = {
            "moniker": normalize_opaque(moniker),
            "individual_id": normalize_opaque(individual_id),
            "kind": kind,
            "rank": rank,
        }
        with self._lock:
            record = self._load_guild(guild_id)
            if record is None:
                ident = normalize_opaque(guild_id)
                record = GuildRecord(
                    guild_id=ident,
                    subject=guild_subject(ident),
                    frame=hub_frame(ident).to_dict(),
                )
            seats = [
                row
                for row in record.seats
                if not (
                    row.get("individual_id") == seat["individual_id"]
                    and row.get("kind") == seat["kind"]
                )
            ]
            seats.append(seat)
            record.seats = seats
            self._save_guild(record)
        return seat

    def _seat(self, guild_id: str, principal: Principal) -> dict | None:
        record = self._load_guild(guild_id)
        if record is None:
            return None
        for row in record.seats:
            if row.get("individual_id") == principal.id and row.get("kind", "account") == principal.kind:
                return row
        return None

    def is_member(self, guild_id: str, principal: Principal) -> bool:
        return self._seat(guild_id, principal) is not None

    def guilds_for(self, principal: Principal) -> list[GuildRecord]:
        found: list[GuildRecord] = []
        root = self.root / "guilds"
        if not root.exists():
            return found
        for path in sorted(root.glob("*.json")):
            record = self._load_guild(path.stem)
            if record is None:
                continue
            for row in record.seats:
                if (
                    row.get("individual_id") == principal.id
                    and row.get("kind", "account") == principal.kind
                ):
                    found.append(record)
                    break
        return found

    def upper_for(self, principal: Principal) -> dict[str, dict]:
        """Latent frame, plus hub residuals for guilds this individual sits in."""
        frame = self.latent_frame()
        for guild in self.guilds_for(principal):
            frame = compose(frame, guild.residual)
        return frame

    def _empty(self, principal: Principal, expires_at: str | None) -> IndividualRecord:
        return IndividualRecord(
            kind=principal.kind,
            id=principal.id,
            expires_at=expires_at,
            frame=individual_frame(principal.id).to_dict(),
        )

    def _read_record(self, principal: Principal) -> IndividualRecord | None:
        path = self._individual_path(principal)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return IndividualRecord(
            kind=str(raw.get("kind") or principal.kind),
            id=str(raw.get("id") or principal.id),
            expires_at=raw.get("expires_at"),
            stated=dict(raw.get("stated") or {}),
            residual=dict(raw.get("residual") or {}),
            frame=dict(raw.get("frame") or individual_frame(principal.id).to_dict()),
        )

    def _expired(self, record: IndividualRecord, moment: datetime) -> bool:
        if record.kind != "session":
            return False
        deadline = _parse_stamp(record.expires_at)
        return deadline is not None and moment >= deadline

    def _save_individual(self, record: IndividualRecord) -> None:
        principal = Principal(record.kind, record.id)
        self._atomic(self._individual_path(principal), record.to_dict())

    def _drop_individual(self, principal: Principal) -> None:
        path = self._individual_path(principal)
        if path.exists():
            path.unlink()

    def load_individual(self, principal: Principal) -> IndividualRecord:
        with self._lock:
            return self._load_individual_locked(principal)

    def _load_individual_locked(self, principal: Principal) -> IndividualRecord:
        moment = _now(self.clock)
        record = self._read_record(principal)
        if record is None:
            expires = None
            if principal.kind == "session":
                expires = _stamp(moment + timedelta(seconds=self.session_ttl_s))
            return self._empty(principal, expires)
        if self._expired(record, moment):
            self._drop_individual(principal)
            return self._empty(principal, None)
        fresh = difference(record.stated, self.upper_for(principal))
        if fresh != record.residual:
            record.residual = fresh
            self._save_individual(record)
        return record

    def list_stated(self, principal: Principal) -> list[dict]:
        record = self.load_individual(principal)
        if record.kind == "session" and record.expires_at is None and not record.stated:
            return []
        rows = [dict(cell) for cell in record.stated.values()]
        rows.sort(key=lambda cell: cell.get("id") or "")
        return rows

    def list_residual(self, principal: Principal) -> list[dict]:
        record = self.load_individual(principal)
        rows = [dict(cell) for cell in record.residual.values()]
        rows.sort(key=lambda cell: cell.get("id") or "")
        return rows

    def put_stated(
        self,
        principal: Principal,
        fact_id: str,
        text: str,
        *,
        kind: str = "stated",
        personal: bool | None = None,
    ) -> dict:
        reject_secret(text)
        slot = (fact_id or "").strip().lower()
        if not _FACT_ID.fullmatch(slot):
            raise PersonaError("fact id must match [a-z][a-z0-9_]{0,63}")
        if kind not in FACT_KINDS:
            raise PersonaError(f"unknown fact kind {kind}")
        body = " ".join(str(text or "").split())
        if not body:
            raise PersonaError("text is required")
        if len(body) > 240:
            raise PersonaError("text is longer than 240 characters")
        is_personal = True
        if kind == "shared" and personal is False:
            is_personal = False
        if kind in ALWAYS_PERSONAL:
            is_personal = True
        moment = _stamp(_now(self.clock))
        with self._lock:
            record = self._load_individual_locked(principal)
            if principal.kind == "session" and not record.stated and record.expires_at is None:
                record.expires_at = _stamp(
                    _now(self.clock) + timedelta(seconds=self.session_ttl_s)
                )
            prior = record.stated.get(slot) or {}
            cell = {
                "id": slot,
                "text": body,
                "kind": kind,
                "label": LABEL_USER,
                "source": LABEL_USER,
                "personal": is_personal,
                "stated_at": str(prior.get("stated_at") or moment),
                "updated_at": moment,
            }
            record.stated[slot] = cell
            record.residual = difference(record.stated, self.upper_for(principal))
            self._save_individual(record)
        return dict(cell)

    def delete_stated(self, principal: Principal, fact_id: str) -> bool:
        slot = (fact_id or "").strip().lower()
        with self._lock:
            record = self._read_record(principal)
            if record is None or slot not in record.stated:
                return False
            if self._expired(record, _now(self.clock)):
                self._drop_individual(principal)
                return False
            record.stated.pop(slot, None)
            record.residual = difference(record.stated, self.upper_for(principal))
            if record.stated:
                self._save_individual(record)
            else:
                self._drop_individual(principal)
        return True

    def record_tutorial(self, principal: Principal, step_id: str) -> dict | None:
        step = step_id.strip()
        known = {row["id"] for row in self.seed().tutorial}
        if step not in known:
            return None
        return self.put_stated(
            principal,
            f"progress_{step}",
            "done",
            kind="tutorial",
            personal=True,
        )

    def read_hub(self, guild_id: str, principal: Principal) -> dict[str, Any]:
        """Hub residual and roster. Members only. No other individual's stated facts."""
        with self._lock:
            record = self._load_guild(guild_id)
            seat = self._seat(guild_id, principal) if record is not None else None
            if record is None or seat is None:
                raise NotAMember("hub data is visible to seated members")
            residual = [dict(cell) for cell in record.residual.values()]
            residual.sort(key=lambda cell: cell.get("id") or "")
            seats = [
                {"moniker": row.get("moniker"), "rank": row.get("rank")}
                for row in record.seats
            ]
            return {
                "guild_id": record.guild_id,
                "subject": record.subject,
                "charter_ref": record.charter_ref,
                "compact_ref": record.compact_ref,
                "frame_profile_ref": record.frame_profile_ref,
                "residual": residual,
                "seats": seats,
                "frame": record.frame or hub_frame(record.guild_id).to_dict(),
                "writes_titanos": False,
                "writes_residual_core": False,
            }

    def promote_to_hub(
        self,
        principal: Principal,
        guild_id: str,
        fact_id: str,
        *,
        opt_in: bool,
        proposed: StoredFrame | dict | None = None,
        axis_merge_reason: str = "",
    ) -> dict[str, Any]:
        if not opt_in:
            raise OptInRequired("individual to hub requires opt_in")
        slot = (fact_id or "").strip().lower()
        with self._lock:
            seat = self._seat(guild_id, principal)
            record = self._load_guild(guild_id)
            if record is None or seat is None:
                raise NotAMember("a seat is required to promote into a guild hub")
            individual = self._load_individual_locked(principal)
            cell = individual.stated.get(slot)
            if cell is None:
                raise PersonaError("no user-stated fact with that id")
            lower = StoredFrame.from_dict(individual.frame or individual_frame(principal.id).to_dict())
            higher = _as_frame(proposed, hub_frame(record.guild_id))
            gate = self.reflection.gate(
                lower, higher, axis_merge_reason=axis_merge_reason
            )
            if gate["abstain"]:
                return _abstain_promotion("hub", slot, gate)
            latent = self.latent_frame()
            above = latent.get(slot)
            stored = False
            if above is None or above.get("text") != cell.get("text"):
                shared = dict(cell)
                shared["label"] = LABEL_HUB
                shared["source"] = "opt-in:individual"
                shared["promoted_by_moniker"] = seat.get("moniker")
                record.residual[slot] = shared
                record.frame = higher.to_dict()
                self._save_guild(record)
                stored = True
            elif not record.frame:
                record.frame = higher.to_dict()
                self._save_guild(record)
            self._recompute_members_locked(record)
            return {
                "tier": "hub",
                "stored": stored,
                "status": "ACCEPTED",
                "failure": False,
                "fact_id": slot,
                "opt_in": True,
                "frame": higher.to_dict(),
                "reflection": gate,
                "writes_titanos": False,
                "writes_residual_core": False,
            }

    def promote_to_latent(
        self,
        principal: Principal,
        guild_id: str,
        fact_id: str,
        *,
        opt_in: bool,
        proposed: StoredFrame | dict | None = None,
        axis_merge_reason: str = "",
    ) -> dict[str, Any]:
        """Promote a recurring hub residual. Personal facts are refused.

        ``FrameReflection.recurring`` is the gnosis extension point. The
        default only counts members. Nothing here runs on ``put_stated``.
        """
        if not opt_in:
            raise OptInRequired("hub to latent requires opt_in")
        slot = (fact_id or "").strip().lower()
        with self._lock:
            record = self._load_guild(guild_id)
            seat = self._seat(guild_id, principal) if record is not None else None
            if record is None or seat is None:
                raise NotAMember("a seat is required to promote toward latent")
            if seat.get("rank") != "steward":
                raise PersonaError("latent promotion is a steward act in this guild")
            cell = record.residual.get(slot)
            if cell is None:
                raise PersonaError("that residual is not on the guild hub")
            if cell.get("personal") or cell.get("kind") in ALWAYS_PERSONAL:
                raise PersonalFact("personal facts do not move to latent")
            lower = StoredFrame.from_dict(record.frame or hub_frame(record.guild_id).to_dict())
            higher = _as_frame(proposed, latent_frame())
            gate = self.reflection.gate(
                lower, higher, axis_merge_reason=axis_merge_reason
            )
            if gate["abstain"]:
                return _abstain_promotion("latent", slot, gate)
            texts: list[str] = []
            for member in record.seats:
                kind = str(member.get("kind") or "account")
                try:
                    who = Principal(kind, str(member.get("individual_id")))
                except (TypeError, ValueError):
                    continue
                stated = (self._read_record(who) or IndividualRecord(kind, who.id)).stated
                match = stated.get(slot)
                if match and match.get("text") == cell.get("text"):
                    texts.append(str(match.get("text") or ""))
            verdict: ReflectionVerdict = self.reflection.recurring(
                texts, str(cell.get("text") or "")
            )
            if not verdict.recurring:
                raise NotRecurring(verdict.reason)
            promoted = self._load_promoted()
            lifted = {
                "id": slot,
                "text": cell.get("text"),
                "kind": cell.get("kind"),
                "label": LABEL_LATENT,
                "source": "opt-in:hub",
                "personal": False,
                "stated_at": cell.get("stated_at") or "",
                "updated_at": _stamp(_now(self.clock)),
                "guild_id": record.guild_id,
                "holders": verdict.holders,
                "gnosis": verdict.gnosis,
            }
            promoted[slot] = lifted
            self._save_promoted(promoted, higher.to_dict())
            record.residual.pop(slot, None)
            record.residual = difference(record.residual, self.latent_frame())
            self._save_guild(record)
            self._recompute_members_locked(record)
            report = verdict.to_dict()
            report["collapse"] = gate["collapse"]
            report["failure"] = False
            report["scores_beliefs"] = False
            return {
                "tier": "latent",
                "stored": True,
                "status": "ACCEPTED",
                "failure": False,
                "fact_id": slot,
                "opt_in": True,
                "frame": higher.to_dict(),
                "reflection": report,
                "writes_titanos": False,
                "writes_residual_core": False,
            }

    def _recompute_members_locked(self, record: GuildRecord) -> None:
        for member in record.seats:
            kind = str(member.get("kind") or "account")
            ident = str(member.get("individual_id") or "")
            if not ident:
                continue
            self._load_individual_locked(Principal(kind, ident))

    def purge_expired(self) -> int:
        removed = 0
        root = self.root / "individuals" / "session"
        if not root.exists():
            return 0
        moment = _now(self.clock)
        with self._lock:
            for path in root.glob("*.json"):
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                deadline = _parse_stamp(raw.get("expires_at"))
                if deadline is not None and moment >= deadline:
                    path.unlink()
                    removed += 1
        return removed


def get_persona_store() -> PersonaStore:
    global _STORE
    if _STORE is None:
        root = os.environ.get("RESILEOS_PERSONA_DIR", "data/persona")
        _STORE = PersonaStore(root)
    return _STORE


def set_persona_store(store: PersonaStore | None) -> None:
    global _STORE
    _STORE = store
