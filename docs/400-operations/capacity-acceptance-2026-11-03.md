---
doc: RES-330-accept
title: Capacity M1–M4 acceptance snapshot
status: measured
date: 2026-11-03
---

# Capacity M1–M4 acceptance snapshot

Source: `artifacts/report_capacity_m1m4.json` (in-process Titanos).

| Metric | Rate | Target | Pass |
|--------|------|--------|------|
| M1 tool honesty | 1.0 | 1.0 | yes |
| M2 invention | 0.0 | 0.0 | yes |
| M3 store hit | 1.0 | 1.0 | yes |
| M4 hub in-process | 1.0 | 1.0 | yes |
| M4 hub reload | 1.0 | 1.0 | yes |

Host **strict** M4 (docker compose restart) is operator-reported green; not re-run in this CI environment.

M5–M8 (latency tiers, scale admit, chat-leak, etc.) remain optional follow-ups; not blocking hosted Titanos API when M1–M4 hold.
