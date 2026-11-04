---
doc: RES-328-workbench
title: Workbench Mouth
status: implemented
depends_on: [RES-327, RES-320]
---

# Workbench Mouth

Ingest fact lines into Titanos, ask exact rows, render with a pluggable backend.

| Backend | Requirement |
|---------|-------------|
| `structured` | Default; no extra deps |
| `local_hf` | `transformers` + model |
| `hosted` | API key |

## CLI

```bash
python scripts/run_workbench.py ingest facts.txt
python scripts/run_workbench.py ask subject relation
```

## Code

| Path | Role |
|------|------|
| `src/resileos/answer/workbench.py` | Parse, ingest, ask, render |
| `scripts/run_workbench.py` | CLI |

Empty retrieval returns an explicit no-record answer; it does not invent rows.
