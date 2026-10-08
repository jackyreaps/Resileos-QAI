---
doc: RES-201
title: Control Packet
status: stable
depends_on: [RES-200]
referenced_by: [RES-202, RES-300, RES-400]
---

# Control Packet

The control packet is the single interface between the classical core and the
HDRIFT substrate. It is fixed-size, typed, and canonicalized.

## Schema

    {
      "version":            "string",
      "Ub":                 "float32[m, r]",
      "Vb":                 "float32[n, r]",
      "row_s_k":            "int16[m]",
      "col_s_k":            "int16[n]",
      "lat_s_k":            "int16[r]",
      "Lambda":             "float32[r, r]",
      "mu":                 "int8",
      "DeltaS":             "float32",
      "F_res":              "float32",
      "volume":             "float64",
      "volume_ok":          "bool",
      "rank":               "int32",
      "schedule_index":     "int32",
      "sigma1_gate":        "bool",
      "sigma1_action":      "string",
      "packet_hash":        "string"
    }

## Field semantics

| Field | Type | Meaning |
|---|---|---|
| `version` | string | Packet schema version, e.g. `"1.0.0"` |
| `Ub` | float32[m, r] | Binary factors, left (`±1`) |
| `Vb` | float32[n, r] | Binary factors, right (`±1`) |
| `row_s_k` | int16[m] | Row residual exponents |
| `col_s_k` | int16[n] | Column residual exponents |
| `lat_s_k` | int16[r] | Latent residual exponents |
| `Lambda` | float32[r, r] | Dynamical scar |
| `mu` | int8 | Residual-flux parity ∈ {0, 1} |
| `DeltaS` | float32 | Sharpness monitor |
| `F_res` | float32 | Continuous residual flux |
| `volume` | float64 | `|det J|` |
| `volume_ok` | bool | Volume-preservation flag |
| `rank` | int32 | Current Prime-Tower rank |
| `schedule_index` | int32 | Prime-Tower step index |
| `sigma1_gate` | bool | Sigma-1 gate fired this step |
| `sigma1_action` | string | `"CLEANUP"` \| `"REEMBED"` \| `"REPULSE_ABSTAIN"` \| `"NONE"` |
| `packet_hash` | string | SHA-256, see RES-202 |

## Rules

- `volume`, `volume_ok`, and `rank` are part of the full packet and are
  advisory for the quantum / coherence backend — they may be stripped or
  ignored by that backend.
- `sigma1_gate` and `sigma1_action` are always present. `sigma1_action` is
  `"NONE"` when the gate did not fire.
- Any change to field set or semantics requires a new packet `version`.

## Legacy → current schema mapping

Any legacy float32 ε-grid value `s` is converted:

    k = round(s / ε)   then clamped to [-16, +16]

Adapters must emit the integer-exponent schema before backend hand-off.

## Read next

- [Canonicalization](canonicalization.md) — RES-202
- [Moment Bundle](../300-substrate/moment-bundle.md) — RES-301