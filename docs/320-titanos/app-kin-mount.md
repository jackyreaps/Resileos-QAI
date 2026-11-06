---
doc: RES-339-kin-mount
title: Mount Kin Routes and Mouth Gate on app.py
status: implemented
depends_on: [RES-338-kin-eat]
---

# Mount Kin on app.py

After `titanos_singleton` exists and Zeus is registered (already on main):

```python
# near other imports
from resileos.kin.wiring import wire_kin

# after agency.add_child("zeus", ...):
wire_kin(app, titanos_singleton, auth_dep=verify_api_key)
```

Optional mouth gate inside `titanos_answer` when `render` / prose is requested:

```python
from resileos.kin.mouth_policy import should_render_prose

want_prose = bool(getattr(payload, "render", False))
if want_prose and not should_render_prose(
    True,
    metrics=None,
    agency_group=getattr(titanos_singleton, "agency", None),
    run_cycle=False,
    default_if_no_policy=True,
):
    # return rows + empty answer_text or structured-only response
    pass
```

## Routes added

| Method | Path | Effect |
|--------|------|--------|
| POST | `/api/v1/eat` | filter + learn |
| POST | `/api/v1/eat/preview` | filter only |
| POST | `/api/v1/kin/cycle` | Iris → Metis report |

All use the same `verify_api_key` dependency when `auth_dep` is passed.
