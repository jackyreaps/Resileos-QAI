---
doc: RS-INF-mount
title: Mount workspace routes in app.py
status: note
---

# Mount workspace routes

After the Titanos singleton exists:

```python
from resileos.answer.api_routes import register_workspace_routes

register_workspace_routes(
    app,
    get_titanos=lambda: titanos_singleton,  # or your getter
    asset_index_path="artifacts/world_assets.json",  # or /app/data/...
)
```

Env (optional):

```bash
export RESILEOS_GUILD_LEDGER=/app/data/guild_ledger.json
```

Ensure the ledger path is on a persistent volume with Titanos state.
