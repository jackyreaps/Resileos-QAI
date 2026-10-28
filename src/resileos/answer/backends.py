"""Pluggable answer backends for the /api/v1/answer route (RES-327).

Three backends, selected at boot by ``RESILEOS_ANSWER_BACKEND`` (or by
explicit name). Each takes an ``AnswerContext`` (question + retrieved
rows + optional recurrent-path metadata) and returns a single string.

    structured  — template renderer, no model, ships everywhere
    local_hf    — frozen HF decoder + retrieved-rows prompt, needs
                  ``transformers`` and ≥8 GB (or a GPU)
    hosted      — OpenAI-compatible chat completion, needs
                  ``RESILEOS_ANSWER_API_KEY``

``/answer`` is the exact-retrieval + rendering path: ``Titanos.ask_list``
returns every row for a ``(subject, relation)`` pair, and the backend
renders them. For recurrent-loop semantics (sigma gate, CSI fast path,
order-parameter gate), use ``/api/v1/query``. When ``render=true`` is
passed to ``/query``, the same mouth is applied to the full ``Answer``
(path, loop_history, gate_state).

Environment
-----------
RESILEOS_ANSWER_BACKEND     structured | local_hf | hosted | auto
RESILEOS_ANSWER_MODEL       HF model id for local_hf
                            (default Qwen/Qwen2.5-0.5B)
RESILEOS_ANSWER_API_KEY     key for hosted
RESILEOS_ANSWER_API_BASE    base URL for hosted (default OpenAI)
RESILEOS_ANSWER_API_MODEL   model name for hosted (default gpt-4o-mini)

The selection is read once at first use. Env changes at runtime do not
re-select; restart the service to switch backends.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Protocol

import torch

log = logging.getLogger("resileos.answer")


# ── context ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AnswerContext:
    """Inputs to a backend's ``render``.

    ``rows`` is the exact-retrieval result from ``Titanos.ask_list``
    (or a single-element tuple derived from ``Answer.value`` when the
    context is built from a recurrent ``Answer``). Empty tuple means
    "no facts stored for this pair" — the backend should say so plainly
    rather than guess.

    ``recovery_loss`` is the F2 phase-recovery loss at render time if
    the recovery gate is enabled; otherwise 0.0. Backends may ignore it;
    the route uses it as a status field.

    Framework fields (populated only when the context is built from a
    full ``Answer`` produced by ``_ask`` / ``/api/v1/query``):

    - ``path``          — the chain of entities, not just the leaf
    - ``loop_history``  — recurrent-trace records (depth = len)
    - ``gate_state``    — final gate state string (e.g. LOCKED / MIXED)
    """

    question: str
    subject: str
    relation: str
    inverse: bool
    rows: tuple[str, ...]
    confidence: float = 1.0
    recovery_loss: float = 0.0
    path: tuple[str, ...] = ()
    loop_history: tuple = ()
    gate_state: str = ""

    @property
    def n_rows(self) -> int:
        return len(self.rows)


# ── protocol ───────────────────────────────────────────────────────────


class AnswerBackend(Protocol):
    name: str

    def available(self) -> bool:
        """True if this backend can render on the current host."""
        ...

    def render(self, ctx: AnswerContext) -> str:
        """Return a single string answer for ``ctx``. May raise; the
        route falls back to ``StructuredBackend`` on exception."""
        ...


# ── shared helpers ─────────────────────────────────────────────────────


def humanize_relation(relation: str) -> str:
    """``parent_of`` → ``parent of``. No other transformation."""
    return relation.replace("_", " ").strip()


def question_from_context(ctx: AnswerContext) -> str:
    """Use the caller's question if present; otherwise synthesise one
    from the structured fields."""
    if ctx.question.strip():
        return ctx.question.strip()
    rel = humanize_relation(ctx.relation)
    if ctx.inverse:
        return f"What has {rel} pointing at {ctx.subject}?"
    return f"What is {ctx.subject}'s {rel}?"


def build_prompt(ctx: AnswerContext) -> str:
    """Shared prompt for the model-backed backends.

    Retrieved rows go in verbatim. The model is told to answer only from
    them. Greedy decoding in the backends keeps output deterministic.
    """
    q = question_from_context(ctx)
    if ctx.rows:
        facts = "\n".join(f"- {r}" for r in ctx.rows)
    else:
        facts = "(no retrieved rows)"
    return (
        f"Retrieved facts:\n{facts}\n\n"
        f"Question: {q}\n"
        f"Answer using only the retrieved facts above. "
        f"Reply with one short sentence, nothing else.\n"
        f"Answer:"
    )


def context_from_answer(
    ans,
    *,
    subject: str,
    relation: str,
    inverse: bool = False,
    question: str = "",
) -> AnswerContext:
    """Build an ``AnswerContext`` from a recurrent ``Answer``.

    Used by ``/api/v1/query?render=true``. Maps ``Answer.value`` into
    ``rows`` (single element or empty) so every backend can render
    without special-casing the recurrent path.
    """
    value = getattr(ans, "value", None)
    rows: tuple[str, ...] = (str(value),) if value else ()
    path_raw = getattr(ans, "path", None) or []
    hist_raw = getattr(ans, "loop_history", None) or []
    return AnswerContext(
        question=question or f"{subject} {relation}",
        subject=subject,
        relation=relation,
        inverse=inverse,
        rows=rows,
        confidence=float(getattr(ans, "confidence", 0.0)),
        recovery_loss=float(getattr(ans, "recovery_loss", 0.0)),
        path=tuple(str(p) for p in path_raw),
        loop_history=tuple(hist_raw),
        gate_state=str(getattr(ans, "gate_state", "") or ""),
    )


# ── structured (template) backend ─────────────────────────────────────


def _join_rows(rows: tuple[str, ...]) -> str:
    if len(rows) == 1:
        return rows[0]
    if len(rows) == 2:
        return f"{rows[0]} and {rows[1]}"
    return ", ".join(rows[:-1]) + f", and {rows[-1]}"


class StructuredBackend:
    """Template renderer. No model, no network. Always available.

    Renders the exact retrieved rows into a single sentence. For
    single-valued facts the sentence is the answer; for multi-valued
    facts it is a list. Never invents; empty rows produce an explicit
    "no record" sentence.

    When framework fields are present (path / loop_history / gate_state)
    the sentence is enriched:

    - multi-hop ``path``  → "Starting from A, via B and C, we reach D."
    - deep recurrent loop → "(resolved after N recurrent steps)" when N > 5
    - non-LOCKED gate     → "with partial confidence"
    """

    name = "structured"

    def available(self) -> bool:
        return True

    def render(self, ctx: AnswerContext) -> str:
        rel = humanize_relation(ctx.relation)
        s = ctx.subject

        # ── path-aware multi-hop rendering ──────────────────────────
        if len(ctx.path) >= 2:
            start = ctx.path[0]
            end = ctx.path[-1]
            if len(ctx.path) == 2:
                base = f"Starting from {start}, we reach {end}."
            else:
                via = ", ".join(ctx.path[1:-1])
                base = (
                    f"Starting from {start}, via {via}, "
                    f"we reach {end}."
                )
        elif ctx.n_rows == 0:
            if ctx.inverse:
                base = (
                    f"I have no record of anything with {rel} "
                    f"pointing at {s}."
                )
            else:
                base = f"I have no record of a {rel} for {s}."
        elif ctx.n_rows == 1:
            value = ctx.rows[0]
            if ctx.inverse:
                base = f"{value}'s {rel} is {s}."
            else:
                base = f"{s}'s {rel} is {value}."
        else:
            values = _join_rows(ctx.rows)
            if ctx.inverse:
                base = f"Entities with {rel} pointing at {s}: {values}."
            else:
                base = f"{s}'s {rel}: {values}."

        # ── framework annotations (only when data is present) ───────
        notes: list[str] = []
        n_loops = len(ctx.loop_history)
        if n_loops > 5:
            notes.append(f"resolved after {n_loops} recurrent steps")
        gs = (ctx.gate_state or "").upper()
        if gs and gs != "LOCKED":
            notes.append("with partial confidence")

        if not notes:
            return base
        return f"{base.rstrip('.')} ({'; '.join(notes)})."


# ── local HF backend ──────────────────────────────────────────────────


class LocalHFBackend:
    """Frozen HF decoder. Lazy-loads on first ``render``.

    ``available()`` only checks that ``transformers`` imports. It does
    not test whether the model fits in RAM; the first ``render`` will
    raise if it does not, and the route falls back to structured.
    """

    name = "local_hf"

    def __init__(self, model_id: str | None = None) -> None:
        self.model_id = model_id or os.getenv(
            "RESILEOS_ANSWER_MODEL", "Qwen/Qwen2.5-0.5B"
        )
        self._model = None
        self._tokenizer = None
        self._device = "cpu"

    def available(self) -> bool:
        try:
            import transformers  # noqa: F401
        except ImportError:
            return False
        return True

    def _load(self) -> None:
        if self._model is not None:
            return
        from transformers import AutoModelForCausalLM, AutoTokenizer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        tok = AutoTokenizer.from_pretrained(self.model_id)
        if tok.pad_token is None:
            tok.pad_token = tok.eos_token
        model = AutoModelForCausalLM.from_pretrained(
            self.model_id, torch_dtype=torch.float32
        )
        model.to(device)
        model.eval()
        for p in model.parameters():
            p.requires_grad_(False)
        self._model = model
        self._tokenizer = tok
        self._device = device
        log.info("LocalHFBackend loaded %s on %s", self.model_id, device)

    def render(self, ctx: AnswerContext) -> str:
        self._load()
        prompt = build_prompt(ctx)
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._device)
        with torch.no_grad():
            out = self._model.generate(
                **inputs,
                max_new_tokens=48,
                do_sample=False,
                num_beams=1,
                pad_token_id=self._tokenizer.pad_token_id,
            )
        new_tokens = out[0][inputs["input_ids"].shape[1]:]
        text = self._tokenizer.decode(
            new_tokens, skip_special_tokens=True
        ).strip()
        return text or StructuredBackend().render(ctx)


# ── hosted backend ────────────────────────────────────────────────────


class HostedBackend:
    """OpenAI-compatible chat completion. Env-configured.

    Reads the key, base URL, and model name once at construction. If
    the provider returns a malformed response, falls back to the
    structured renderer rather than raising.
    """

    name = "hosted"

    def __init__(self) -> None:
        self.api_key = os.getenv("RESILEOS_ANSWER_API_KEY", "").strip()
        self.api_base = os.getenv(
            "RESILEOS_ANSWER_API_BASE", "https://api.openai.com/v1"
        ).rstrip("/")
        self.model = os.getenv(
            "RESILEOS_ANSWER_API_MODEL", "gpt-4o-mini"
        )

    def available(self) -> bool:
        return bool(self.api_key)

    def render(self, ctx: AnswerContext) -> str:
        import requests

        prompt = build_prompt(ctx)
        r = requests.post(
            f"{self.api_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 96,
                "temperature": 0.0,
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        try:
            text = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError):
            text = ""
        return text or StructuredBackend().render(ctx)


# ── selection ─────────────────────────────────────────────────────────


_BACKEND_NAMES = ("structured", "local_hf", "hosted")


def build_backend(name: str) -> AnswerBackend:
    """Construct a backend by name. Raises ``ValueError`` on unknown."""
    n = (name or "").strip().lower()
    if n == "structured":
        return StructuredBackend()
    if n == "local_hf":
        return LocalHFBackend()
    if n == "hosted":
        return HostedBackend()
    raise ValueError(f"unknown answer backend: {name!r}")


def select_backend(name: str | None = None) -> AnswerBackend:
    """Pick a backend. ``auto`` tries local_hf → hosted → structured.

    If ``name`` is given (or ``RESILEOS_ANSWER_BACKEND`` is set), try
    that backend first. If it is unavailable, log and fall through to
    the same preference order. The last fallback is always structured,
    which is always available.
    """
    requested = (
        name or os.getenv("RESILEOS_ANSWER_BACKEND", "auto")
    ).strip().lower()

    if requested and requested != "auto":
        try:
            b = build_backend(requested)
        except ValueError:
            log.warning(
                "Unknown RESILEOS_ANSWER_BACKEND=%r; falling back to auto",
                requested,
            )
            b = None
        if b is not None and b.available():
            return b
        if b is not None:
            log.warning(
                "Backend %r requested but not available; falling back",
                requested,
            )

    for candidate in ("local_hf", "hosted", "structured"):
        b = build_backend(candidate)
        if b.available():
            return b
    return StructuredBackend()


def list_backends() -> list[dict]:
    """Availability report for ``GET /api/v1/answer/backends``."""
    out = []
    for name in _BACKEND_NAMES:
        b = build_backend(name)
        out.append({"name": name, "available": bool(b.available())})
    return out
