#!/usr/bin/env python3
"""
Resileos Chat — memory-first UI over the hosted API.

The store is the source of truth. The model (if any) is only a mouth.
  streamlit run ui_chat.py --server.port 8501 --server.address 127.0.0.1

Env:
  RESILEOS_BACKEND_URL  default http://127.0.0.1:8000/api/v1
  RESILEOS_API_KEY      optional default key (sidebar can override)
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import requests
import streamlit as st

st.set_page_config(
    page_title="Resileos Chat",
    page_icon="◈",
    layout="centered",
    initial_sidebar_state="expanded",
)

BACKEND = os.getenv("RESILEOS_BACKEND_URL", "http://127.0.0.1:8000/api/v1").rstrip(
    "/"
)
# Accept either .../api/v1 or host root
if not BACKEND.endswith("/api/v1") and "/api/" not in BACKEND:
    # user may pass https://api.example.com
    pass

DEFAULT_KEY = os.getenv("RESILEOS_API_KEY", "")


# ── HTTP ───────────────────────────────────────────────────────────────────


def headers(key: str) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if key:
        h["X-API-Key"] = key
    return h


def api_get(path: str, key: str, timeout: float = 8.0) -> tuple[int, Any]:
    url = f"{BACKEND}{path}" if path.startswith("/") else f"{BACKEND}/{path}"
    try:
        r = requests.get(url, headers=headers(key), timeout=timeout)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:500]}
    except requests.RequestException as e:
        return 0, {"error": str(e)}


def api_post(path: str, key: str, payload: dict, timeout: float = 30.0) -> tuple[int, Any]:
    url = f"{BACKEND}{path}" if path.startswith("/") else f"{BACKEND}/{path}"
    try:
        r = requests.post(
            url, headers=headers(key), json=payload, timeout=timeout
        )
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:500]}
    except requests.RequestException as e:
        return 0, {"error": str(e)}


# ── parse simple "remember" lines ──────────────────────────────────────────

_REMEMBER = re.compile(
    r"^\s*(?:remember|learn)\s*[:\-]?\s+(\S+)\s+(\S+)\s+(.+?)\s*$",
    re.I,
)
_QUERY_TRIPLE = re.compile(
    r"^\s*(?:what(?:'s| is)|query)?\s*(\S+)\s+(\S+)\s*\??\s*$",
    re.I,
)


def try_remember(text: str) -> dict | None:
    m = _REMEMBER.match(text.strip())
    if not m:
        return None
    return {
        "subject": m.group(1).strip(),
        "relation": m.group(2).strip(),
        "obj": m.group(3).strip(),
    }


def try_triple_query(text: str) -> dict | None:
    t = text.strip()
    m = _QUERY_TRIPLE.match(t)
    if m:
        return {"subject": m.group(1), "relation": m.group(2)}
    parts = t.replace("?", "").split()
    if len(parts) == 2 and parts[0].lower() not in ("what", "who", "where"):
        return {"subject": parts[0], "relation": parts[1]}
    return None


# ── session ────────────────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Resileos Chat — exact memory.\n\n"
                "• Ask: `Zeus domain` or use Query below\n"
                "• Teach: `remember Zeus domain sky`\n"
                "• Empty answers mean **not in the store**, not a guess."
            ),
        }
    ]


# ── sidebar ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### Connection")
    backend_in = st.text_input("API base", value=BACKEND)
    if backend_in.strip():
        BACKEND = backend_in.strip().rstrip("/")
    key = st.text_input(
        "API key",
        value=DEFAULT_KEY,
        type="password",
        help="X-API-Key for protected routes",
    )
    use_render = st.checkbox(
        "Request prose (render)",
        value=False,
        help="If the server supports answer render / mouth",
    )
    st.divider()
    code, body = api_get("/ready", key)
    if code == 200 and isinstance(body, dict):
        st.success("Store ready")
        st.caption(
            f"facts={body.get('facts', body.get('stats', {}).get('facts', '?'))} · "
            f"auth_required={body.get('auth_required', '?')}"
        )
    elif code == 0:
        st.error(f"Unreachable: {body}")
    else:
        st.warning(f"ready → HTTP {code}")
        st.json(body)

    if st.button("Refresh /stats"):
        sc, sb = api_get("/stats", key)
        st.write(f"HTTP {sc}")
        st.json(sb)

    st.divider()
    st.markdown("### Teach (form)")
    with st.form("learn_form"):
        s = st.text_input("Subject", placeholder="Zeus")
        r = st.text_input("Relation", placeholder="domain")
        o = st.text_input("Object", placeholder="sky")
        submitted = st.form_submit_button("Learn")
        if submitted and s and r and o:
            sc, sb = api_post(
                "/learn", key, {"subject": s, "relation": r, "obj": o}
            )
            if sc == 200:
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": f"Learned `{s} —{r}→ {o}`.\n\n`{json.dumps(sb)[:400]}`",
                    }
                )
                st.rerun()
            else:
                st.error(f"HTTP {sc}: {sb}")


# ── main ───────────────────────────────────────────────────────────────────

st.title("Resileos Chat")
st.caption("Memory engine · store is truth · models optional")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Ask the store, or: remember Subject relation object")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    reply = ""
    # 1) remember
    fact = try_remember(prompt)
    if fact:
        sc, sb = api_post("/learn", key, fact)
        if sc == 200:
            reply = (
                f"Stored **{fact['subject']} —{fact['relation']}→ {fact['obj']}**.\n\n"
                f"```json\n{json.dumps(sb, indent=2)[:600]}\n```"
            )
        else:
            reply = f"Learn failed (HTTP {sc}):\n```\n{sb}\n```"
    else:
        # 2) structured query
        q = try_triple_query(prompt)
        payload: dict[str, Any]
        if q:
            payload = {**q}
            if use_render:
                payload["render"] = True
            sc, sb = api_post("/query", key, payload)
        else:
            # free text → /answer if available, else guide user
            payload = {"question": prompt} if not use_render else {
                "question": prompt,
                "render": True,
            }
            # try answer endpoint; fall back to query-shaped hint
            sc, sb = api_post("/answer", key, payload)
            if sc == 404:
                sc, sb = api_post(
                    "/query",
                    key,
                    {
                        "subject": prompt.split()[0] if prompt.split() else prompt,
                        "relation": prompt.split()[1]
                        if len(prompt.split()) > 1
                        else "is_a",
                    },
                )

        if sc == 200 and isinstance(sb, dict):
            value = sb.get("value", sb.get("answer", sb.get("answer_text")))
            status = sb.get("status", "")
            answer_text = sb.get("answer_text") or sb.get("text")
            if value is None and status in ("ABSTAINED", "EMPTY", ""):
                reply = (
                    "**Not in store** (honest empty).\n\n"
                    "Teach with: `remember Subject relation object`"
                )
            elif answer_text:
                reply = str(answer_text)
                if value is not None:
                    reply += f"\n\n_value:_ `{value}`"
            elif value is not None:
                reply = f"**{value}**"
            else:
                reply = f"```json\n{json.dumps(sb, indent=2)[:800]}\n```"
            conf = sb.get("confidence")
            if conf is not None:
                reply += f"\n\n_confidence:_ `{conf}` · _status:_ `{status}`"
        elif sc == 401:
            reply = "Unauthorized — set API key in the sidebar."
        elif sc == 403:
            reply = "Forbidden — invalid API key."
        elif sc == 503:
            reply = "Service refuses open access — configure API keys on the server."
        else:
            reply = f"HTTP {sc}:\n```\n{sb}\n```"

    st.session_state.messages.append({"role": "assistant", "content": reply})
    with st.chat_message("assistant"):
        st.markdown(reply)
