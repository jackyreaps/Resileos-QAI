---
doc: RES-328-workbench
title: Advanced Project Workbench Mouth
status: implemented
depends_on: [RES-327, RES-325, RES-320]
---

# Advanced Project Workbench Mouth

## Purpose

Working loop for advanced projects (formalization tags, residual constants,
engineering status) **without** dumping suite theory into the repo:

1. **Ingest** working facts as triples  
2. **Ask** exact rows from Titanos  
3. **Render** via structured (default) or `local_hf` / `hosted` RAG mouth  

## Code

| Module | Role |
|--------|------|
| `src/resileos/answer/workbench.py` | parse, ingest, ask, render |
| `scripts/run_workbench.py` | CLI |

## Backends

| Name | Needs |
|------|--------|
| `structured` | nothing extra (default) |
| `local_hf` | `transformers` + model weights |
| `hosted` | API key |

Store remains source of truth. Empty rows → explicit “no record,” not invention.

## Example

```bash
python scripts/run_workbench.py ingest my_working_facts.txt
python scripts/run_workbench.py ask eps equals
```
