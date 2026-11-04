---
doc: RES-328-hub-train
title: Hub Training
status: implemented
depends_on: [RES-328-hub-ns, RES-328-workbench]
---

# Hub Training

Train Titanos under hub subjects (`user:`, `world:`, `org:`). Query through the workbench mouth.

## CLI

```bash
python scripts/train_hubs.py seed --state artifacts/hub_state.json
python scripts/train_hubs.py train facts.txt --state artifacts/hub_state.json
python scripts/train_hubs.py ask world:materials status --state artifacts/hub_state.json
```

## Code

| Path | Role |
|------|------|
| `src/resileos/answer/hub_train.py` | Hub-prefix train + optional seed |
| `scripts/train_hubs.py` | CLI |

Fact file lines: `subject, relation, object` or `subject -> object : relation`.
