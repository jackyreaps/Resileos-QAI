---
doc: RES-341-council-frames
title: Council of Stores and Dimensional Frame Categories
status: implemented
depends_on: [RES-340-verifier-swarm]
---

# Council + Frame Categories

## Honesty frames
`exact` · `reconstructed` · `abstained` · `unresolved` · `filtered` · `provisional`

## Dimensional categories (hub / layer)
`dim.user` · `dim.world` · `dim.org` · `dim.default` · `dim.sys` · `dim.seed` · `dim.media` · `dim.policy` · `dim.multi` · `dim.conflict`

## Council
`council_query(subject, relation, ask_fn, profile=personal|policy|world)`

Precedence:
- personal: user > world > org
- policy: org > world > user
- Conflicts → status CONFLICT, dim.conflict, provenance list

## API
`POST /api/v1/council/query` (when kin routes mounted)
