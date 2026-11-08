"""Shared portable UI for Studio and Chat.

Both entry points call this module. Genesis and other hosts can import main().
"""
from __future__ import annotations

import os


def main() -> None:
    """Run the Streamlit surface. Mode via RESILEOS_UI_MODE (studio|chat)."""
    mode = os.getenv("RESILEOS_UI_MODE", "studio")
    _run_surface(mode)


def _run_surface(mode: str) -> None:
    import json
    import os
    import re
    import uuid
    from datetime import datetime, timezone
    from typing import Any
    from urllib.parse import quote

    import requests
    import streamlit as st

    try:
        from resileos.answer.user_profile import (
            PERSONA_PACKS,
            extract_interest_signal,
            load_profile,
            save_profile_facts,
            shape_reply,
        )
        _HAS_PROFILE = True
    except ImportError:
        _HAS_PROFILE = False
        PERSONA_PACKS = {"honest": {"label": "Honest", "tone": "neutral"}}

    st.set_page_config(page_title="Resileos Studio", page_icon="◈", layout="wide")
    st.markdown(
        "<style>.block-container{padding-top:1rem;max-width:1120px}"
        ".hit{font-size:1.2rem;font-weight:650;color:#143d73}"
        ".empty{color:#9a6700}.muted{color:#666;font-size:.9rem}</style>",
        unsafe_allow_html=True,
    )

    BACKEND = os.getenv("RESILEOS_BACKEND_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
    DEFAULT_KEY = os.getenv("RESILEOS_API_KEY", "")
    PROVIDER = os.getenv("RESILEOS_IMAGE_PROVIDER", "pollinations").strip().lower()
    IMAGE_API_URL = os.getenv("RESILEOS_IMAGE_API_URL", "").rstrip("/")
    IMAGE_API_KEY = os.getenv("RESILEOS_IMAGE_API_KEY", "")


    def headers(key: str) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if key:
            h["X-API-Key"] = key
        return h


    def api_get(path: str, key: str, timeout: float = 12.0) -> tuple[int, Any]:
        url = f"{BACKEND}{path}"
        try:
            r = requests.get(url, headers=headers(key), timeout=timeout)
            try:
                return r.status_code, r.json()
            except Exception:
                return r.status_code, {"raw": (r.text or "")[:800]}
        except requests.RequestException as e:
            return 0, {"error": str(e)}


    def api_post(path: str, key: str, payload: dict, timeout: float = 60.0) -> tuple[int, Any]:
        url = f"{BACKEND}{path}"
        try:
            r = requests.post(url, headers=headers(key), json=payload, timeout=timeout)
            try:
                return r.status_code, r.json()
            except Exception:
                return r.status_code, {"raw": (r.text or "")[:800]}
        except requests.RequestException as e:
            return 0, {"error": str(e)}


    def search_answer(key: str, subject: str = "", relation: str = "", question: str = "") -> dict:
        payload: dict[str, Any] = {}
        if subject and relation:
            payload["subject"] = subject.strip()
            payload["relation"] = relation.strip()
        if question:
            payload["question"] = question.strip()
        sc, sb = api_post("/answer", key, payload)
        return {"endpoint": "/answer", "http": sc, "body": sb}


    def search_query(key: str, subject: str, relation: str) -> dict:
        sc, sb = api_post("/query", key, {"subject": subject.strip(), "relation": relation.strip()})
        return {"endpoint": "/query", "http": sc, "body": sb}


    def search_sparql(key: str, query: str) -> dict:
        sc, sb = api_post("/sparql", key, {"query": query})
        return {"endpoint": "/sparql", "http": sc, "body": sb}


    def search_chain(key: str, start: str, relations: list[str]) -> dict:
        sc, sb = api_post("/chain", key, {"start": start.strip(), "relations": relations})
        return {"endpoint": "/chain", "http": sc, "body": sb}


    def format_result(result: dict) -> str:
        sc, body = result.get("http"), result.get("body")
        if sc != 200:
            return f"HTTP {sc}: `{body}`"
        if not isinstance(body, dict):
            return str(body)
        rows = body.get("rows")
        answer_text = body.get("answer_text") or body.get("text")
        value = body.get("value")
        status = body.get("status", "")
        if rows is not None:
            if not rows:
                return f"Not in store (`{status or 'empty'}`). Teach with remember S R O."
            lines = [f"**{len(rows)} row(s)** · `{status}`"]
            if answer_text:
                lines.append(answer_text)
            for row in rows[:25]:
                lines.append(f"- `{row}`")
            return "\n".join(lines)
        if value is None and status in ("ABSTAINED", "NONE_CHANNEL", "EMPTY", ""):
            return f"Not in store (`{status or 'miss'}`)."
        if answer_text:
            return answer_text
        if value is not None:
            return f"**{value}**"
        return f"```json\n{json.dumps(body, indent=2)[:2500]}\n```"


    def generate_image_pollinations(prompt: str, width: int = 1024, height: int = 1024) -> dict:
        seed = uuid.uuid4().hex[:8]
        url = (
            f"https://image.pollinations.ai/prompt/{quote(prompt.strip()[:500])}"
            f"?width={width}&height={height}&nologo=true&seed={seed}"
        )
        try:
            r = requests.get(url, timeout=90, stream=True)
            return {"ok": r.status_code == 200, "url": url, "provider": "pollinations", "status": r.status_code}
        except requests.RequestException as e:
            return {"ok": True, "url": url, "provider": "pollinations", "warning": str(e)}


    def generate_image_openai(prompt: str) -> dict:
        if not IMAGE_API_URL:
            return {"ok": False, "error": "RESILEOS_IMAGE_API_URL not set"}
        h = {"Content-Type": "application/json"}
        if IMAGE_API_KEY:
            h["Authorization"] = f"Bearer {IMAGE_API_KEY}"
        try:
            r = requests.post(
                IMAGE_API_URL,
                headers=h,
                json={"prompt": prompt, "n": 1, "size": "1024x1024"},
                timeout=120,
            )
            data = r.json() if r.content else {}
            if r.status_code >= 400:
                return {"ok": False, "error": data or r.text}
            url = None
            if isinstance(data.get("data"), list) and data["data"]:
                url = data["data"][0].get("url")
            url = url or data.get("url") or data.get("image_url") or data.get("output")
            if url:
                return {"ok": True, "url": str(url), "provider": "openai_compat"}
            return {"ok": False, "error": data}
        except requests.RequestException as e:
            return {"ok": False, "error": str(e)}


    def generate_image(prompt: str, width: int = 1024, height: int = 1024) -> dict:
        if PROVIDER == "none":
            return {"ok": False, "error": "provider disabled"}
        if PROVIDER == "openai" or (IMAGE_API_URL and PROVIDER != "pollinations"):
            out = generate_image_openai(prompt)
            if out.get("ok"):
                return out
            if PROVIDER == "openai":
                return out
        return generate_image_pollinations(prompt, width=width, height=height)


    def register_media(key: str, kind: str, path: str, title: str, world_id: str = "default", note: str = "") -> dict:
        aid = f"a_{uuid.uuid4().hex[:10]}"
        wid = world_id or "default"
        sc, sb = api_post(
            "/world/register",
            key,
            {"world_id": wid, "asset_id": aid, "kind": kind, "path": path[:2000], "title": (title or aid)[:200]},
        )
        if sc in (200, 201):
            return {"ok": True, "asset_id": aid, "body": sb}
        subj = f"world:{wid}:asset:{aid}"
        facts = [
            [subj, "kind", kind],
            [subj, "path", path[:500]],
            [subj, "title", (title or aid)[:200]],
            [subj, "created", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")],
        ]
        if note:
            facts.append([subj, "note", note[:200]])
        sc2, sb2 = api_post("/learn_batch", key, {"facts": facts})
        if sc2 == 200:
            return {"ok": True, "asset_id": aid, "subject": subj, "body": sb2}
        n = 0
        for s, r, o in facts:
            c, _ = api_post("/learn", key, {"subject": s, "relation": r, "obj": o})
            n += int(c == 200)
        return {"ok": n > 0, "asset_id": aid, "subject": subj, "stored": n}


    _REMEMBER = re.compile(r"^\s*(?:remember|learn)\s*[:\-]?\s+(\S+)\s+(\S+)\s+(.+?)\s*$", re.I)


    def parse_remember(text: str) -> dict | None:
        m = _REMEMBER.match(text.strip())
        if not m:
            return None
        return {"subject": m.group(1).strip(), "relation": m.group(2).strip(), "obj": m.group(3).strip()}


    def parse_pair(text: str) -> tuple[str, str] | None:
        t = text.strip().rstrip("?")
        parts = t.split()
        if len(parts) == 2 and parts[0].lower() not in ("what", "who", "where", "how", "why", "find"):
            return parts[0], parts[1]
        m = re.match(r"(?:what(?:'s| is)\s+)?(\S+?)(?:'s)?\s+(\S+)\s*$", t, re.I)
        return (m.group(1), m.group(2)) if m else None


    if "messages" not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant",
            "content": (
                "Resileos Studio — exact memory + real search + image gen.\n\n"
                "• `Zeus domain` search · `remember Zeus domain sky` teach\n"
                "• `draw bronze antikythera on marble` generates + stores image\n"
                "• Search / Media tabs for full tools"
            ),
        }]
    if "search_log" not in st.session_state:
        st.session_state.search_log = []
    if "assets_local" not in st.session_state:
        st.session_state.assets_local = []

    with st.sidebar:
        st.markdown("## Resileos Studio")
        b = st.text_input("API base URL", value=BACKEND)
        if b.strip():
            BACKEND = b.strip().rstrip("/")
        key = st.text_input("API key", value=DEFAULT_KEY, type="password")
        user_id = st.text_input("User id", value=st.session_state.get("user_id", "anon"), help="Stable id for user: hub memory")
        st.session_state["user_id"] = user_id.strip() or "anon"
        display_name = st.text_input("Display name", value=st.session_state.get("display_name", ""))
        st.session_state["display_name"] = display_name
        persona = st.selectbox(
            "Persona",
            list(PERSONA_PACKS.keys()),
            format_func=lambda k: PERSONA_PACKS[k].get("label", k),
            index=list(PERSONA_PACKS.keys()).index(st.session_state.get("persona", "honest"))
            if st.session_state.get("persona", "honest") in PERSONA_PACKS
            else 0,
        )
        st.session_state["persona"] = persona
        if st.button("Load / save profile", use_container_width=True) and _HAS_PROFILE:
            def _post(path, payload):
                return api_post(path, key, payload)
            prof = load_profile(user_id, _post)
            if display_name:
                prof.display_name = display_name
            prof.persona = persona
            n = save_profile_facts(prof, _post)
            st.session_state["profile"] = prof
            st.success(f"Profile stored ({n} fields) under user:{prof.user_id}")
        elif not _HAS_PROFILE:
            st.caption("Install resileos.answer.user_profile for durable persona")

        c1, c2 = st.columns(2)
        cr, br = api_get("/ready", key)
        with c1:
            st.metric("API", "Ready" if cr == 200 else str(cr or "Down"))
        with c2:
            sc, sb = api_get("/stats", key)
            st.metric("Facts", sb.get("facts", "—") if sc == 200 and isinstance(sb, dict) else "—")
        with st.form("teach"):
            qs = st.text_input("Subject", placeholder="Zeus")
            qr = st.text_input("Relation", placeholder="domain")
            qo = st.text_input("Object", placeholder="sky")
            if st.form_submit_button("Save fact", use_container_width=True) and qs and qr and qo:
                sc, sb = api_post("/learn", key, {"subject": qs.strip(), "relation": qr.strip(), "obj": qo.strip()})
                st.success("Saved") if sc == 200 else st.error(f"{sc}: {sb}")
        if st.button("Seed demo facts", use_container_width=True):
            demo = [
                ["Zeus", "domain", "sky"], ["Poseidon", "domain", "sea"],
                ["Athena", "domain", "wisdom"], ["Zeus", "parent_of", "Athena"],
                ["Athena", "is_a", "olympian"], ["Zeus", "is_a", "olympian"],
            ]
            sc, sb = api_post("/learn_batch", key, {"facts": demo})
            st.success(str(sb)) if sc == 200 else st.error(f"{sc}: {sb}")

    tab_chat, tab_search, tab_media, tab_make, tab_diag, tab_help = st.tabs(["Chat", "Search", "Media", "Make", "Diagnostics", "Help"])

    with tab_chat:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("image_url"):
                    st.image(msg["image_url"], use_container_width=True)
        prompt = st.chat_input("Ask, remember S R O, or: draw <prompt>")
        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            reply, image_url = "", None
            low = prompt.lower().strip()
            if low.startswith(("draw ", "image ", "generate image")):
                gen_prompt = re.sub(r"^(draw|image|generate image)\s+", "", prompt, flags=re.I).strip()
                with st.spinner("Generating image…"):
                    gen = generate_image(gen_prompt or prompt)
                if gen.get("url"):
                    image_url = gen["url"]
                    reg = register_media(key, "image", image_url, gen_prompt[:80], note=f"provider={gen.get('provider')}")
                    reply = f"Image via **{gen.get('provider')}**. Registered `{reg.get('asset_id')}` (ok={reg.get('ok')})."
                    st.session_state.assets_local.insert(0, {"id": reg.get("asset_id"), "kind": "image", "path": image_url, "title": gen_prompt[:80]})
                else:
                    reply = f"Generation failed: `{gen}`"
            else:
                fact = parse_remember(prompt)
                if fact:
                    sc, sb = api_post("/learn", key, fact)
                    reply = f"Saved **{fact['subject']} —{fact['relation']}→ {fact['obj']}**" if sc == 200 else f"Fail {sc}: `{sb}`"
                else:
                    pair = parse_pair(prompt)
                    if pair:
                        result = search_answer(key, subject=pair[0], relation=pair[1], question=prompt)
                        body = result.get("body") if isinstance(result.get("body"), dict) else {}
                        if result.get("http") == 200 and not body.get("rows") and body.get("value") is None:
                            result = search_query(key, pair[0], pair[1])
                        reply = format_result(result)
                    else:
                        reply = format_result(search_answer(key, question=prompt))
            if _HAS_PROFILE:
                def _post(path, payload):
                    return api_post(path, key, payload)
                prof = st.session_state.get("profile")
                if prof is None:
                    prof = load_profile(st.session_state.get("user_id", "anon"), _post)
                prof.display_name = st.session_state.get("display_name") or prof.display_name
                prof.persona = st.session_state.get("persona", prof.persona)
                prof.turn_count = int(getattr(prof, "turn_count", 0)) + 1
                sig = extract_interest_signal(prompt)
                if sig and sig not in prof.interests:
                    prof.interests.append(sig)
                reply = shape_reply(reply, prof)
                save_profile_facts(prof, _post)
                st.session_state["profile"] = prof
            st.session_state.messages.append({"role": "assistant", "content": reply, "image_url": image_url})
            with st.chat_message("assistant"):
                st.markdown(reply)
                if image_url:
                    st.image(image_url, use_container_width=True)

    with tab_search:
        st.subheader("Find")
        qfind = st.text_input("Find something", key="find_q")
        if st.button("Look up", key="find_btn") and qfind:
            from resileos.ui.search_flow import search
            from resileos.ui.explain_remember import explain
            out = search(qfind)
            st.write(explain(qfind, out["hub"])["text"])
            st.markdown(f"[Web results]({out['web_url']})")
            if out["offer_save"]:
                st.caption("Not in your hub. Save it after you read it.")
        st.divider()
        st.subheader("Search the store")
        mode = st.radio("Mode", ["Answer", "Triple", "SPARQL", "Chain"], horizontal=True)
        left, right = st.columns([3, 2])
        result = None
        with left:
            if mode == "Answer":
                q = st.text_input("Question / subject", placeholder="Zeus domain")
                rel = st.text_input("Relation (optional)", placeholder="domain")
                if st.button("Search", type="primary") and q.strip():
                    pair = parse_pair(q)
                    if rel.strip() and len(q.split()) == 1:
                        result = search_answer(key, subject=q.strip(), relation=rel.strip())
                    elif pair:
                        result = search_answer(key, subject=pair[0], relation=pair[1], question=q)
                    else:
                        result = search_answer(key, question=q)
            elif mode == "Triple":
                c1, c2 = st.columns(2)
                with c1:
                    subj = st.text_input("Subject", key="ts")
                with c2:
                    rel = st.text_input("Relation", key="tr")
                if st.button("Query", type="primary") and subj and rel:
                    result = search_query(key, subj, rel)
            elif mode == "SPARQL":
                sparql = st.text_area("Query", height=100, placeholder="SELECT ?o WHERE Zeus --domain--> ?o")
                if st.button("Run SPARQL", type="primary") and sparql.strip():
                    result = search_sparql(key, sparql.strip())
            else:
                start = st.text_input("Start", placeholder="Zeus")
                rels = st.text_input("Relations", placeholder="parent_of, domain")
                if st.button("Run chain", type="primary") and start:
                    result = search_chain(key, start, [x.strip() for x in rels.split(",") if x.strip()])
            if result is not None:
                st.session_state.search_log.insert(0, result)
        with right:
            st.markdown("#### Result")
            if st.session_state.search_log:
                last = st.session_state.search_log[0]
                st.write(f"`{last.get('endpoint')}` · HTTP **{last.get('http')}**")
                st.markdown(format_result(last))
                with st.expander("Raw JSON"):
                    st.json(last.get("body"))
            else:
                st.caption("Run a search.")

    with tab_media:
        st.subheader("Generate image & register media")
        st.markdown("Default generator: **Pollinations** (no key). Results are saved into Titanos as facts.")
        a, b = st.columns(2)
        with a:
            prompt = st.text_area("Image prompt", height=90, placeholder="cinematic bronze mechanism on marble")
            w = st.selectbox("Width", [768, 1024, 1280], index=1)
            h = st.selectbox("Height", [768, 1024, 1280], index=1)
            auto = st.checkbox("Auto-register in store", value=True)
            world_id = st.text_input("World id", value="default")
            if st.button("Generate image", type="primary", use_container_width=True) and prompt.strip():
                with st.spinner("Generating…"):
                    gen = generate_image(prompt, width=int(w), height=int(h))
                if gen.get("url"):
                    st.image(gen["url"], use_container_width=True)
                    st.caption(gen["url"][:100])
                    if auto:
                        reg = register_media(key, "image", gen["url"], prompt[:80], world_id=world_id, note=f"provider={gen.get('provider')}")
                        st.success(f"Registered `{reg.get('asset_id')}` ok={reg.get('ok')}")
                        st.session_state.assets_local.insert(0, {"id": reg.get("asset_id"), "kind": "image", "path": gen["url"], "title": prompt[:80]})
                else:
                    st.error(gen)
            st.markdown("#### Register existing URL")
            kind = st.selectbox("Kind", ["image", "video", "audio", "game_codex", "other"])
            title = st.text_input("Title", key="rt")
            path = st.text_input("URL or path", key="rp")
            if st.button("Register", use_container_width=True) and path.strip():
                reg = register_media(key, kind, path.strip(), title or path[:40], world_id=world_id)
                st.success(f"{reg.get('asset_id')}") if reg.get("ok") else st.error(reg)
                if reg.get("ok"):
                    st.session_state.assets_local.insert(0, {"id": reg.get("asset_id"), "kind": kind, "path": path.strip(), "title": title})
            st.info("Video generation is not bundled. Register MP4/WebM URLs to preview and store.")
        with b:
            st.markdown("#### Library")
            for asset in st.session_state.assets_local[:12]:
                st.markdown(f"**{asset.get('title') or asset.get('id')}** · `{asset.get('kind')}`")
                p = asset.get("path") or ""
                if p.startswith("http"):
                    if asset.get("kind") == "video" or p.lower().endswith((".mp4", ".webm", ".mov")):
                        st.video(p)
                    else:
                        try:
                            st.image(p, use_container_width=True)
                        except Exception:
                            st.write(p)
                if asset.get("id") and st.button("Query stored path", key=f"q{asset['id']}"):
                    sc, sb = api_post("/query", key, {"subject": f"world:{world_id}:asset:{asset['id']}", "relation": "path"})
                    st.write(sc)
                    st.json(sb)


    
    with tab_make:
        st.subheader("Make a world")
        prompt = st.text_input("What should it look like", key="make_prompt")
        world = st.text_input("World", value="world:mine", key="make_world")
        if st.button("Make art", key="make_art_btn") and prompt:
            from resileos.ui.make_world import make_art
            art = make_art(prompt, world_id=world)
            st.json({"art": art.get("art"), "kept": art.get("kept"), "facts": art.get("facts")})
        if st.button("Make recesses", key="make_rec_btn") and prompt:
            from resileos.ui.make_world import make_recess_sequence
            seq = make_recess_sequence(prompt, world_id=world)
            st.json({"recesses": len(seq["recesses"]), "rows": seq["rows"]})
        if st.button("Make still", key="make_btn") and prompt:
            from resileos.ui.make_world import make_still
            out = make_still(prompt, world_id=world)
            st.json({"address": out["address"], "rows": out["rows"], "backend": out["backend"]})
            st.session_state["last_address"] = out["address"]
        if st.button("Continue", key="cont_btn") and st.session_state.get("last_address"):
            from resileos.ui.make_world import continue_from
            nxt = continue_from(st.session_state["last_address"], prompt or "continue", world_id=world)
            st.json({"address": nxt["address"], "rows": nxt["rows"]})
            st.session_state["last_address"] = nxt["address"]

    with tab_diag:
        st.subheader("Photo diagnostics")
        st.caption("Inspection figures for work photos. Not medical or forensic claims.")
        up = st.file_uploader("Upload a photo", type=["png", "jpg", "jpeg"], key="diag_up")
        if up is not None:
            try:
                import numpy as np
                from PIL import Image
                from resileos.ui.diagnostics import diagnose_image, histogram_rows
                img = np.array(Image.open(up).convert("RGB"))
                d = diagnose_image(img)
                c1, c2, c3 = st.columns(3)
                c1.metric("Mean luma", d.get("mean_luma"))
                c2.metric("Edge density", d.get("edge_density"))
                c3.metric("Aspect", d.get("aspect"))
                if "channel_means" in d:
                    st.write(d["channel_means"])

                st.bar_chart(histogram_rows(d))
                from resileos.ui.studio_scale import diagnose_with_scale
                st.write("Scale")
                st.json(diagnose_with_scale(img))
                st.divider()
                st.subheader("Candidate triples (not facts)")
                cap = st.text_input("Caption for this photo", key="diag_cap")
                if cap:
                    from resileos.ui.perception import perception_payload
                    payload = perception_payload(cap, subject="uploaded_photo")
                    st.json(payload)
                    st.caption("Send each candidate through /api/v1/eat before it becomes a fact.")

            except Exception as e:
                st.error(f"Diagnostics failed: {e}")

    with tab_help:
        st.markdown(
            """
        ### Why this is useful
        | Capability | Implementation |
        |------------|----------------|
        | Fact memory | `/learn`, `/learn_batch`, `/query`, `/answer` |
        | Search | Answer + Triple + SPARQL + Chain (live API) |
        | Images | Pollinations HTTP generate + auto `/learn_batch` register |
        | Video | Register/preview URLs (bring your own encoder) |
        | Product | Same API keys as paid hosting |

        ### Persona / user memory (PAL-style)
        Set **User id** + **Persona** in the sidebar. Profile triples live under `user:<id>` (display_name, persona, interest, turn_count). Tone adapts; **facts still only come from the store**.

        ### Optional paid images
        ```bash
        export RESILEOS_IMAGE_PROVIDER=openai
        export RESILEOS_IMAGE_API_URL=https://api.openai.com/v1/images/generations
        export RESILEOS_IMAGE_API_KEY=sk-...
        ```
        """
            )
