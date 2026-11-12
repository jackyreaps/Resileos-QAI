"""Shared labels for measurement artifacts.

These helpers do not score a bench. They stamp the date and describe
the machine the numbers came from, and they strip secrets before a
report is written.
"""
from __future__ import annotations

import os
import platform
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_SECRET_ENV = (
    "BENCH_LLM_KEY",
    "BENCH_LLM_URL",
    "RESILEOS_API_KEY",
    "LLM_API_KEY",
    "OPENAI_API_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_API_KEY",
    "STRIPE_WEBHOOK_SECRET",
)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def utc_day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def dated_artifact(kind: str, day: str | None = None) -> Path:
    """``landing/artifacts/report_<kind>_<YYYY-MM-DD>.json``."""
    stamp = day or utc_day()
    return ROOT / "landing" / "artifacts" / f"report_{kind}_{stamp}.json"


def environment() -> dict:
    """Honest label for this process. No hostname."""
    cpu = ""
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        cpu = ""
    return {
        "label": "cursor cloud agent VM",
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "cpu_model": cpu or None,
        "note": (
            "Numbers in this file were measured in this process on this "
            "VM. They are not a hosted API sample and not a claim about "
            "another machine."
        ),
    }


def secret_values() -> list[str]:
    found: list[str] = []
    for name in _SECRET_ENV:
        value = os.getenv(name, "") or ""
        if len(value) >= 4 and value not in found:
            found.append(value)
    return found


def redact_text(text: str) -> str:
    """Remove env secrets, bearer tokens, and sk- style keys."""
    out = str(text)
    for secret in secret_values():
        out = out.replace(secret, "[redacted]")
    out = re.sub(r"Bearer\s+\S+", "Bearer [redacted]", out, flags=re.IGNORECASE)
    out = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "[redacted]", out)
    return out


def percentile(values: list[float], p: float) -> float | None:
    """Linear interpolation. ``p`` is in ``[0, 100]``.

    For 100 samples, p50 is the midpoint of the 50th and 51st sorted
    values (index 49.5). p95 is index 94.05.
    """
    if not values:
        return None
    if not 0.0 <= p <= 100.0:
        raise ValueError("p must be between 0 and 100")
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (p / 100.0) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def latency_summary(samples_ms: list[float]) -> dict:
    n = len(samples_ms)
    return {
        "n": n,
        "p50_ms": percentile(samples_ms, 50),
        "p95_ms": percentile(samples_ms, 95),
        "p99_ms": percentile(samples_ms, 99),
        "min_ms": min(samples_ms) if samples_ms else None,
        "max_ms": max(samples_ms) if samples_ms else None,
        "mean_ms": (sum(samples_ms) / n) if n else None,
        "percentile_method": (
            "linear interpolation between nearest ranks on the sorted "
            "sample; p50 of 100 values is the midpoint of sorted indexes "
            "49 and 50"
        ),
    }
