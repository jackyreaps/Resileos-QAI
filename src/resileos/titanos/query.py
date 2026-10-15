"""Query language and execution engine for Titanos (RES-322).

Grammar (v1):

    query    := SELECT targets WHERE clauses
    targets  := var (',' var)*
    clauses  := clause (AND clause)*
    clause   := term ARROW term
              | term LARROW term
    term     := VAR | NAME
    VAR      := '?' identifier
    NAME     := identifier (letters, digits, '_', '.')
    ARROW    := '--' relation '-->'
    LARROW   := '<--' relation '--'

Semantics: each clause is a pattern over the graph. Variables bind to
entity names. Clauses are joined on shared variables via nested-loop
evaluation. The result is the list of bindings of the SELECT targets.

Inverse patterns: `?s <--rel-- X` means "find S such that S --rel--> X".
The parser normalises this to anchor=X with inverse=True, so the
executor reads it as an inverse lookup anchored at X.

Errors:
    QuerySyntaxError   malformed input
    QueryBindingError  unbound variable in a position requiring a name
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Protocol

# ── tokens ──────────────────────────────────────────────────────────
TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<select>\bSELECT\b)
  | (?P<where>\bWHERE\b)
  | (?P<and>\bAND\b)
  | (?P<comma>,)
  | (?P<var>\?[A-Za-z_][A-Za-z0-9_]*)
  | (?P<arrow>--[A-Za-z_][A-Za-z0-9_.]*-->)
  | (?P<larrow><--[A-Za-z_][A-Za-z0-9_.]*--)
  | (?P<name>[A-Za-z_][A-Za-z0-9_.]*)
    """,
    re.VERBOSE,
)


class QuerySyntaxError(ValueError):
    pass


class QueryBindingError(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    pos: int


def tokenize(src: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    while i < len(src):
        m = TOKEN_RE.match(src, i)
        if not m:
            raise QuerySyntaxError(
                f"unexpected character {src[i]!r} at {i}"
            )
        i = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        tokens.append(Token(kind=kind, value=m.group(), pos=m.start()))
    return tokens


# ── AST ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Name:
    value: str


Term = Var | Name


@dataclass(frozen=True)
class Pattern:
    anchor: Term
    relation: str
    target: Term
    inverse: bool


@dataclass(frozen=True)
class Query:
    targets: tuple[Var, ...]
    clauses: tuple[Pattern, ...]


# ── parser ──────────────────────────────────────────────────────────
class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.toks = tokens
        self.i = 0

    def peek(self, kind: Optional[str] = None) -> Optional[Token]:
        if self.i >= len(self.toks):
            return None
        t = self.toks[self.i]
        if kind is None or t.kind == kind:
            return t
        return None

    def eat(self, kind: str) -> Token:
        t = self.peek(kind)
        if t is None:
            got = self.toks[self.i] if self.i < len(self.toks) else None
            raise QuerySyntaxError(
                f"expected {kind}, got {got.kind if got else 'EOF'}"
            )
        self.i += 1
        return t

    def parse_term(self) -> Term:
        t = self.peek("var")
        if t is not None:
            self.i += 1
            return Var(t.value[1:])
        t = self.peek("name")
        if t is not None:
            self.i += 1
            return Name(t.value)
        raise QuerySyntaxError(
            f"expected term, got "
            f"{self.toks[self.i].kind if self.i < len(self.toks) else 'EOF'}"
        )

    def parse_clause(self) -> Pattern:
        anchor = self.parse_term()
        arrow = self.peek("arrow")
        if arrow is not None:
            self.i += 1
            rel = arrow.value[2:-3]
            target = self.parse_term()
            return Pattern(
                anchor=anchor, relation=rel, target=target, inverse=False
            )
        larrow = self.peek("larrow")
        if larrow is not None:
            self.i += 1
            rel = larrow.value[3:-2]
            target = self.parse_term()
            # `?s <--rel-- X` means `X <--rel-- ?s`, i.e. find S
            # such that `S --rel--> X`. Anchor at X, inverse lookup.
            return Pattern(
                anchor=target, relation=rel, target=anchor, inverse=True
            )
        raise QuerySyntaxError("expected --relation--> or <--relation--")

    def parse(self) -> Query:
        self.eat("select")
        targets: list[Var] = []
        t = self.peek("var")
        if t is None:
            raise QuerySyntaxError("SELECT requires at least one ?variable")
        targets.append(Var(t.value[1:]))
        self.i += 1
        while self.peek("comma") is not None:
            self.i += 1
            t = self.eat("var")
            targets.append(Var(t.value[1:]))
        self.eat("where")
        clauses = [self.parse_clause()]
        while self.peek("and") is not None:
            self.i += 1
            clauses.append(self.parse_clause())
        if self.i != len(self.toks):
            raise QuerySyntaxError(
                f"trailing tokens starting at {self.toks[self.i].pos}"
            )
        return Query(targets=tuple(targets), clauses=tuple(clauses))


def parse(query_src: str) -> Query:
    return _Parser(tokenize(query_src)).parse()


# ── executor ────────────────────────────────────────────────────────
class _Core(Protocol):
    def ask(
        self, anchor: str, relation: str, inverse: bool = False
    ) -> list[str]: ...


def _resolve(term: Term, binding: dict[str, str]) -> str:
    if isinstance(term, Name):
        return term.value
    if term.name in binding:
        return binding[term.name]
    raise QueryBindingError(
        f"variable ?{term.name} is unbound in anchor position"
    )


def execute(core: _Core, q: Query) -> list[tuple[str, ...]]:
    """Execute a parsed query. Returns a list of tuples, one per row,
    ordered as in the SELECT clause."""
    bindings: list[dict[str, str]] = [{}]
    for clause in q.clauses:
        next_bindings: list[dict[str, str]] = []
        for b in bindings:
            try:
                anchor_name = _resolve(clause.anchor, b)
            except QueryBindingError:
                # Unbound anchor. v1 does not support full scans;
                # skip this binding rather than scan.
                continue
            results = core.ask(
                anchor=anchor_name,
                relation=clause.relation,
                inverse=clause.inverse,
            )
            for r in results:
                nb = dict(b)
                if isinstance(clause.target, Var):
                    existing = nb.get(clause.target.name)
                    if existing is not None and existing != r:
                        continue
                    nb[clause.target.name] = r
                else:
                    if clause.target.value != r:
                        continue
                next_bindings.append(nb)
        bindings = next_bindings
        if not bindings:
            break
    out: list[tuple[str, ...]] = []
    for b in bindings:
        row: list[str] = []
        complete = True
        for v in q.targets:
            if v.name in b:
                row.append(b[v.name])
            else:
                complete = False
                break
        if complete:
            out.append(tuple(row))
    return out


class TitanosQueryEngine:
    """Convenience wrapper: parse + execute against a Titanos core."""

    def __init__(self, core: _Core) -> None:
        self.core = core

    def parse(self, query_src: str) -> Query:
        return parse(query_src)

    def execute(self, query_src: str) -> list[tuple[str, ...]]:
        return execute(self.core, parse(query_src))

    def execute_parsed(self, q: Query) -> list[tuple[str, ...]]:
        return execute(self.core, q)


__all__ = [
    "Query",
    "Pattern",
    "Var",
    "Name",
    "Term",
    "QuerySyntaxError",
    "QueryBindingError",
    "parse",
    "tokenize",
    "execute",
    "TitanosQueryEngine",
]
