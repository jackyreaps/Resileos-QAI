---
doc: RES-202
title: Canonicalization
status: stable
depends_on: [RES-201]
referenced_by: [RES-300, RES-402]
---

# Canonicalization

`packet_hash` is a SHA-256 digest over a canonical serialization of the
control packet. Without canonicalization, hashes are not reproducible across
implementations.

## Canonical JSON rules

| Rule | Specification |
|---|---|
| Object keys | sorted lexicographically |
| Array order | preserved |
| Floats | IEEE-754 hex |
| Booleans | `true` / `false` |
| Nulls | `null` |
| `packet_hash` field | **excluded** before hashing |
| `version` field | **included** in the hash input |

## Procedure

1. Copy the packet.
2. Remove the `packet_hash` field.
3. Serialize to canonical JSON per the rules above.
4. Compute SHA-256 over the UTF-8 bytes.
5. Store the lowercase hex digest in `packet_hash`.

## Round-trip note

The residual-scale mapping

    k = round(s / ε)   then clamp to [-16, +16]

is exact inside the open interval `(-16, +16)` and saturates at the
endpoints. Round-trip tests must allow for endpoint saturation.

## Why this matters

- Replays must be bit-exact.
- Hash mismatches between producer and consumer are diagnostics, not
  tolerable noise.
- Any downstream artifact (substrate state, backend payload) that claims to
  derive from a specific packet must be verifiable against its hash.

## Read next

- [Control Packet](control-packet.md) — RES-201
- [Validation](../400-operations/validation.md) — RES-402