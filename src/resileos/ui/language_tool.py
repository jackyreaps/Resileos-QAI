"""Language tool: detect, preserve native, optional translate.

Native text is the stored form. Translation is a surface that can
call an external provider. Without a provider it returns the original
and says so. This is not a full multilingual model.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional
from urllib import request

from resileos.ui.perceive_language import perceive_language


def detect_language(text: str) -> dict[str, Any]:
    """Cheap script-based detection. Not a full language ID model."""
    perc = perceive_language(text, subject="lang")
    other = perc.get("other_share", 0.0)
    latin = perc.get("latin_share", 0.0)
    if other > 0.4:
        guess = "non_latin"
    elif latin > 0.6:
        guess = "latin"
    else:
        guess = "mixed"
    return {
        "guess": guess,
        "latin_share": latin,
        "other_share": other,
        "address": perc.get("address"),
        "note": "script guess only",
    }


def translate(
    text: str,
    *,
    target: str = "en",
    source: Optional[str] = None,
) -> dict[str, Any]:
    """Translate if a provider is set. Otherwise return the original.

    Provider: RESILEOS_TRANSLATE_URL
      POST {"text","target","source"} -> {"text"}
    """
    url = os.getenv("RESILEOS_TRANSLATE_URL", "").strip()
    detected = detect_language(text)
    if not url:
        return {
            "text": text,
            "translated": text,
            "target": target,
            "source": source or detected["guess"],
            "provider": "none",
            "address": detected["address"],
            "note": "No translator set. Native text preserved.",
        }
    body = json.dumps({"text": text, "target": target, "source": source}).encode()
    req = request.Request(url, data=body, headers={"content-type": "application/json"})
    with request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())
    out = str(data.get("text", text))
    return {
        "text": text,
        "translated": out,
        "target": target,
        "source": source or detected["guess"],
        "provider": url,
        "address": detected["address"],
    }


def native_or_translate(
    text: str,
    *,
    prefer_native: bool = True,
    target: str = "en",
) -> dict[str, Any]:
    """Prefer the user's language. Translate only when asked."""
    if prefer_native:
        d = detect_language(text)
        return {
            "text": text,
            "display": text,
            "native": True,
            "address": d["address"],
            "detect": d,
        }
    tr = translate(text, target=target)
    return {
        "text": text,
        "display": tr["translated"],
        "native": False,
        "address": tr["address"],
        "translate": tr,
    }
