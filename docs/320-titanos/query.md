doc: RES-322
title: Query Language and Execution
status: draft
depends_on: [RES-320, RES-321]
referenced_by: []

# Query Language and Execution

The Titanos API exposes `learn`, `ask`, and `chain` as method calls.
That is sufficient for programmatic use and insufficient for an
application layer. A query language gives consumers a stable surface
that does not depend on the Python class layout.

This document specifies the grammar, the AST, the parser, and the
executor for the v1 query language. It does not specify aggregations,
filters, or pagination. Those are deferred.

## 1. Grammar

    query    := SELECT targets WHERE clauses
    targets  := var (',' var)*
    clauses  := clause (AND clause)*
    clause   := term ARROW term
              | term LARROW term
    term     := VAR | NAME
    VAR      := '?' identifier
    NAME     := identifier
    ARROW    := '--' relation '-->'
    LARROW   := '<--' relation '--'

Identifiers are `[A-Za-z_][A-Za-z0-9_.]*`. `SELECT` and `WHERE` and
`AND` are case-insensitive keywords.

## 2. Examples

Forward:

    SELECT ?o WHERE alice --knows--> ?o

Inverse:

    SELECT ?s WHERE ?s <--knows-- bob

Join:

    SELECT ?o WHERE alice --knows--> ?o AND ?o --works_at--> acme

Multi-target:

    SELECT ?a, ?c WHERE ?a --knows--> ?b AND ?b --works_at--> ?c

## 3. AST

    Var(name)
    Name(value)
    Pattern(anchor: Term, relation: str, target: Term, inverse: bool)
    Query(targets: tuple[Var, ...], clauses: tuple[Pattern, ...])

Inverse patterns are normalised at parse time: `?s <--r-- X` becomes
`Pattern(anchor=X, relation=r, target=?s, inverse=False)`. The
`inverse` flag is reserved for future use and is always false in v1
after parsing.

## 4. Execution

Nested-loop join on shared variables. The executor maintains a list of
partial bindings. Each clause consumes the list and produces a new list:

    bindings = [{}]
    for clause in clauses:
        next_bindings = []
        for b in bindings:
            anchors = resolve(clause.anchor, b)      # one name
            for a in anchors:
                results = core.ask(a, clause.relation,
                                   inverse=clause.inverse)
                for r in results:
                    nb = extend(b, clause.target, r)
                    if nb is not None:
                        next_bindings.append(nb)
        bindings = next_bindings

The SELECT projection filters out bindings where any target variable is
unbound. A target variable that does not appear in any clause yields
zero rows.

## 5. Full scan

When a clause's anchor is an unbound variable — e.g. `?s --knows--> ?o`
with no prior binding for `?s` — the v1 executor would skip the
binding. This is the documented v1 behaviour in the initial commit and
it makes certain queries unanswerable.

The updated executor performs a full scan in this case: if the core
exposes `iter_entities()`, every entity is probed as the anchor, and
the binding set grows accordingly. Cores without `iter_entities()` fall
back to skipping.

The core is responsible for `iter_entities()`. For the in-memory
Titanos class it is:

    def iter_entities(self) -> list[str]:
        return list(self.entities.keys())

For the disk-backed core, iterate the index's `iter_names()`.

## 6. Errors

    QuerySyntaxError    malformed input
    QueryBindingError   unbound variable in a position requiring a name

`QueryBindingError` is raised inside `_resolve` and caught by the
executor to trigger the full-scan branch. It is not propagated to the
caller.

## 7. API

    parse(query_src: str) -> Query
    tokenize(query_src: str) -> list[Token]
    execute(core, query: Query) -> list[tuple[str, ...]]
    TitanosQueryEngine(core).execute(query_src) -> list[tuple[str, ...]]

`TitanosQueryEngine` is a thin wrapper that combines parse and execute.

## 8. Non-claims

- No aggregation. `COUNT`, `SUM`, `GROUP BY` are not in the grammar.
- No filters. `FILTER`, `LIMIT`, `ORDER BY` are not in the grammar.
- No disjunction. `OR` is not in the grammar; only `AND`.
- No query planning. Execution is nested-loop in clause order. A
  reordering that pushes selective clauses earlier is a future
  optimisation.
- No full-text. Only exact name matching on anchors and targets.

## 9. Open questions

- **Bounded full scan.** A full scan over N entities is O(N) probes.
  A secondary index on relation presence would make `?s --r--> ?o`
  cheap. Not implemented.
- **Aggregation.** The grammar extension for `COUNT` and `LIMIT` is
  small. Not in v1.
- **Variable-length paths.** `--knows+-->` (transitive closure) is not
  in v1.
- **Constant folding.** `SELECT ?o WHERE alice --knows--> bob` returns
  a boolean, not a row. v1 returns rows; the caller inspects length.

## 10. Read next

- [Disk-Backed Band Store](store.md) — RES-320
- [Dense Entity Index](index.md) — RES-321
- [Documentation Index](../readme.md)

## 11. Endpoint cardinality

`/api/v1/query` and its inverse return a single `Answer.value`.
That is correct for one-to-one relations (`domain`, `is_a`,
`roman_name`) where the question has exactly one answer.

`/api/v1/sparql` returns rows and is the correct endpoint for
one-to-many relations (`parent_of`, `sibling_of`, `symbol_of`,
`spouse_of`). `SELECT ?o WHERE Cronus --parent_of--> ?o` returns all
six children.

The Python API mirrors this: `ask()` / `ask_inverse()` return one
value; `ask_list()` returns all values for a `(subject, relation)`
pair.

Strict single-object recall on a one-to-many relation is not a
correctness metric — it measures the endpoint against the wrong gold.
The 65.8% strict figure in `report_operate_smoke.json` is that
mismatch, not a defect.
