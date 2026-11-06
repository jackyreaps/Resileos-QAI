"""Helpers for Studio Media/Eat tab — call hosted /api/v1/eat."""
from __future__ import annotations

from typing import Any, Callable


def post_eat(
    api_post: Callable[[str, dict], tuple[int, Any]],
    claim: str | dict,
    *,
    user_id: str = "",
    preview: bool = False,
) -> tuple[int, Any]:
    path = "/eat/preview" if preview else "/eat"
    body: dict[str, Any] = {"claim": claim}
    if user_id:
        body["user_id"] = user_id
    return api_post(path, body)


def render_eat_panel(
    st: Any,
    api_post: Callable[[str, dict], tuple[int, Any]],
    *,
    user_id: str = "",
    key_prefix: str = "eat",
) -> None:
    """Drop-in Streamlit panel (pass streamlit module as st)."""
    st.markdown("#### Eat (filter → learn)")
    st.caption(
        "Structured triples only. Prose abstains. Uses POST /api/v1/eat."
    )
    mode = st.radio(
        "Input",
        ["Triple line", "JSON fields"],
        horizontal=True,
        key=f"{key_prefix}_mode",
    )
    preview = st.checkbox("Preview only (no learn)", value=False, key=f"{key_prefix}_prev")
    if mode == "Triple line":
        line = st.text_input(
            "subject relation object",
            placeholder="Zeus domain sky",
            key=f"{key_prefix}_line",
        )
        claim: Any = line
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            s = st.text_input("Subject", key=f"{key_prefix}_s")
        with c2:
            r = st.text_input("Relation", key=f"{key_prefix}_r")
        with c3:
            o = st.text_input("Object", key=f"{key_prefix}_o")
        claim = {"subject": s, "relation": r, "obj": o}
    if st.button("Run eat", type="primary", key=f"{key_prefix}_go"):
        code, body = post_eat(
            api_post, claim, user_id=user_id, preview=preview
        )
        st.write(f"HTTP **{code}**")
        st.json(body)
        if isinstance(body, dict) and body.get("action") == "accept":
            st.success("Accepted" + (" (preview)" if preview else " → learned"))
        elif isinstance(body, dict) and body.get("action") == "abstain":
            st.warning("Abstained — not learned")
        elif isinstance(body, dict) and body.get("action") == "reject":
            st.error(f"Rejected: {body.get('reason')}")
