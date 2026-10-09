"""
Root-level shim for `scripts/titanos.py`.

Exists so that `py-modules = ["titanos"]` in pyproject.toml resolves after
`pip install -e .`, without requiring `scripts/` to be a package.

All behaviour lives in scripts/titanos.py.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent / "scripts" / "titanos.py"
_spec = importlib.util.spec_from_file_location("_titanos_impl", _SCRIPTS)
_impl = importlib.util.module_from_spec(_spec)
sys.modules["_titanos_impl"] = _impl
_spec.loader.exec_module(_impl)

Titanos = _impl.Titanos
TitanosConfig = _impl.TitanosConfig
Answer = _impl.Answer
parse_query = _impl.parse_query


def main() -> int:
    """Console entry point declared in pyproject.toml."""
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    args = p.parse_args()

    cfg = (
        TitanosConfig.from_json(args.config)
        if args.config else TitanosConfig()
    )
    titan = Titanos(cfg)
    print(f"conf_mode = {cfg.conf_mode}  alpha = {cfg.conf_alpha}")
    print(f"stats     = {titan.stats()}")
    return 0


__all__ = ["Titanos", "TitanosConfig", "Answer", "parse_query", "main"]


if __name__ == "__main__":
    sys.exit(main())
