"""Studio helpers for council query + eat dim display."""
from __future__ import annotations

from typing import Any, Callable


def post_council(
    api_post: Callable[[str, dict], tuple[int, Any]],
    subject: str,
    relation: str,
    *,
    profile: str = "personal",
) -> tuple[int, Any]:
    return api_post(
        "/council/query",
        {
            "subject": subject.strip(),
            "relation": relation.strip(),
            "profile": profile,
        },
    )


def render_council_panel(
    st: Any,
    api_post: Callable[[str, dict], tuple[int, Any]],
    *,
    key_prefix: str = "council",
) -> None:
    st.markdown("#### Council query (multi-hub)")
    st.caption("user / world / org precedence — conflicts surfaced, not hidden.")
    c1, c2 = st.columns(2)
    with c1:
        subject = st.text_input("Subject", placeholder="Zeus", key=f"{key_prefix}_s")
    with c2:
        relation = st.text_input("Relation", placeholder="domain", key=f"{key_prefix}_r")
    profile = st.selectbox(
        "Profile",
        ["personal", "policy", "world"],
        key=f"{key_prefix}_p",
    )
    if st.button("Query council", type="primary", key=f"{key_prefix}_go"):
        code, body = post_council(
            api_post, subject, relation, profile=profile
        )
        st.write(f"HTTP **{code}**")
        if isinstance(body, dict):
            st.write(
                f"status=`{body.get('status')}` · "
                f"frame=`{body.get('frame')}` · dim=`{body.get('dim')}` · "
                f"hub=`{body.get('winner_hub')}`"
            )
            if body.get("value") is not None:
                st.markdown(f"**Value:** `{body.get('value')}`")
            if body.get("conflicts"):
                st.warning("Conflict across hubs")
            st.json(body)
        else:
            st.write(body)
