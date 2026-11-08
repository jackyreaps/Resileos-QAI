# Guild merit and credit

## Merit

A permanent, non-transferable, non-purchasable record of verified contribution.
It is the metric for recognition and governance. It is not spent.

| Field | Value |
|-------|--------|
| Lives on | `guild:<id>` relation `merit` |
| Transferable | No |
| Purchasable | No |
| Signed | By the guild process |

## Credit

A variable internal accounting unit. It is used to access shared compute, tools, material resources, and education. It is not convertible to fiat. Protocol endpoints `/convert`, `/redeem`, and `/transfer` are prohibited (RS-INF-002 §7.2, Compact Article II).

| Field | Value |
|-------|--------|
| Lives on | `user:<member>` relation `credit_earn` / `credit_spend` |
| Used for | Compute, tools, materials, education |
| Convertible to fiat | No |
| Protocol transfer | Prohibited |
| Mutual credit | Exists as a facility among members, guild as clearinghouse |

## Free tier and earned use

A free tier exists. Credits add more. Work on a board or on the engine earns credits. Use burns them. The free tier is not removed.

## Both issued on board completion

`complete_and_credit` emits a merit candidate and a credit earn. They are not the same record.

## References

- Compact: GS-FND-002 Article II, definitions of Merit and Credits
- Credit exposure: GS-MTX-005
- Mutual credit: GS-OPS-009
- Attestation schema: schemas/attestation.v1.json
- Resileos: `src/resileos/ui/credits.py`, `src/resileos/ui/worker_tools.py`
