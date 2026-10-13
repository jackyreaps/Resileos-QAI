---
doc: RES-307
title: Agency Hierarchy (Routing Layer)
status: heuristic
depends_on: [RES-200, RES-305, RES-306]
referenced_by: []
---

# Agency Hierarchy (Routing Layer)

A routing layer for the Titanos application. Specialized query
handlers ("children") are registered with a group, selected by weight,
and deactivated when their fitness is poor.

## 0. Status

**Heuristic.** The thresholds in this layer (`eat_threshold_csi`,
`eat_threshold_contrib`, `min_queries_before_eat`, `min_weight`,
`absorption_rate`) are operational parameters, not derived invariants.
Nothing in this repository or in the external OscGraph package
establishes that a child with mean CSI below a given value should be
deactivated.

The layer is documented as a control mechanism. It is not spoken of in
the same register as volume preservation, the residual core, or the
banded-memory crosstalk theorems.

## 1. What it does

- Registers child handlers:
  `callable(parent, subject, relation, inverse) -> Answer | None`.
- Selects a handler for each query by weight (argmax among active
  children).
- After each query, updates the child's fitness: rolling CSI plus an
  EMA of "accepted" (1.0) vs "abstained" (0.0).
- Removes a child from the routing pool when its fitness falls below
  both thresholds and it has answered at least `min_queries_before_eat`
  queries.

The word "eating" refers only to removal from the routing pool. It is
not a biological process. No state from the eaten child is merged into
another child. Weight that was allocated to it is not transferred;
subsequent queries simply are not offered to it.

## 2. Write boundary

Children never write to the frozen residual core. The core's scar
matrix, volume guard, and Prime-Tower schedule are unaffected by
anything the agency layer does. The only mutable state that survives a
query is the Titanos memory layer (banded accumulators, entity
anchors), which is written by the parent's query path, not by any
child.

If a child's handler calls the parent's query method (the standard
pattern), it goes through the same write path as a normal query. It
does not have special access to core internals.

## 3. Selection

    child = argmax(weight)  among active children

Deterministic. No random sampling. If no child is active or none is
registered, the parent's own query path runs directly.

If the selected child's handler returns `None`, the parent path runs
and the child's fitness is still updated with the parent's result.
This gives a child a way to decline without losing fitness signal.

## 4. Fitness thresholds

| Parameter | Default | Meaning |
|---|---|---|
| `eat_threshold_csi` | 0.35 | mean CSI below this makes a child edible |
| `eat_threshold_contrib` | 0.15 | EMA contribution below this too |
| `min_queries_before_eat` | 10 | minimum queries before eating |
| `min_weight` | 0.05 | below this, child deactivated entirely |
| `absorption_rate` | 0.4 | weight multiplier per eat step |

`min_queries_before_eat` exists because mean CSI over the first few
queries is a noisy estimate. Without it, a good child can be eaten
after two unlucky queries.

## 5. Metrics

`snapshot()` returns:

    {
      "children": {
        "<name>": {
          "weight": ...,
          "active": ...,
          "query_count": ...,
          "accept_count": ...,
          "accept_rate": ...,
          "mean_csi": ...,
          "contribution": ...
        }
      },
      "eaten": [...]
    }

The metrics to watch when evaluating this layer:

- `weight` trajectory per child over the query sequence
- `accept_rate` per child
- number of children eaten
- post-prune routing concentration (does the surviving child handle
  the queries, and does its accuracy hold?)

## 6. What is not claimed

- That the eaten child was "wrong." Its fitness was below thresholds
  under the current query distribution.
- That the routing layer improves retrieval accuracy. That is a
  hypothesis under test.
- That the thresholds are optimal. They are defaults chosen for a
  small corpus and should be retuned per workload.
- That the layer is derived from any theory. It is not.

## 7. Read next

- [Causal Sandbox Index](causal-sandbox.md) — RES-305
- [Phasor Graph](phasor-graph.md) — RES-306
- [Classical Core](../200-core/classical-core.md) — RES-200
