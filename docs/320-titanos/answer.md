doc: RES-327
title: Answer route and pluggable backends
status: stable
depends_on: [RES-320, RES-324]
referenced_by: []

# Answer route (RES-327)

`POST /api/v1/answer` is the exact-retrieval + render path.

1. Resolve input: structured `subject`+`relation`, or free-text via
   `parse_query` then `encode_gate` (framework-native).
2. Unresolved → `NONE_CHANNEL`.
3. Optional F2 recovery gate may `ABSTAINED`.
4. `ask_list` loads rows; backend renders one string.
5. Default backend for framework operation: `structured`.

See [gate-encoder.md](gate-encoder.md) for the gate/mouth contract.
