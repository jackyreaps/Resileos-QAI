"""Residual frames inside the persona store.

A lower tier stores only the cells whose text differs from the tier
above it. This is a dict difference. It does not call ResidualCore.
"""
from __future__ import annotations


def difference(stated: dict[str, dict], upper: dict[str, dict]) -> dict[str, dict]:
    """Cells in ``stated`` whose text is not already on ``upper``."""
    residual: dict[str, dict] = {}
    for key, cell in stated.items():
        above = upper.get(key)
        if above is not None and above.get("text") == cell.get("text"):
            continue
        residual[key] = dict(cell)
    return residual


def compose(upper: dict[str, dict], residual: dict[str, dict]) -> dict[str, dict]:
    """Upper frame plus the differences stored on the tier below."""
    merged = {key: dict(cell) for key, cell in upper.items()}
    for key, cell in residual.items():
        merged[key] = dict(cell)
    return merged
