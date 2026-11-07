# Contributing

## Layout

The package lives under `src/resileos/`. Entry points:

- `src/resileos/core.py` — core types and helpers (not `core/`)
- `src/resileos/hierarchy/` — hierarchy package (the sibling `hierarchy.py` is unused)
- `app.py` — FastAPI surface

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

Auth tests that hit protected routes need either `RESILEOS_API_KEYS` or
`RESILEOS_AUTH_BYPASS=1`. Without keys the middleware returns 503.

## Docs

The docs index is `docs/readme.md` (lowercase). GitHub is case-sensitive;
do not link to `docs/README.md`.
