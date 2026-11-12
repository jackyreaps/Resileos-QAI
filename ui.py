"""Streamlit console: one chat column, a memory strip, and a tools drawer.

Run after the backend is up on :8000:
  streamlit run ui.py --server.port 8501 --server.address 127.0.0.1
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Resileos", layout="wide")

BACKEND_URL = os.getenv("RESILEOS_BACKEND_URL", "http://127.0.0.1:8000/api/v1")
API_KEY = st.sidebar.text_input(
    "API Key",
    type="password",
    value=os.getenv("RESILEOS_API_KEY", ""),
)
st.sidebar.caption("Sent as X-API-Key.")
HUB_ID = st.sidebar.text_input("Hub user", value="alice")
PERSONA = st.sidebar.selectbox(
    "Persona",
    ["honest", "guide", "builder", "mythic"],
    index=0,
)

EMPTY_MEMORY = 'Nothing learned about you yet. Say "remember that…" to teach me.'

MYTHOS_SEED = [
    ["Uranus", "parent_of", "Cronus"],
    ["Cronus", "parent_of", "Zeus"],
    ["Cronus", "parent_of", "Poseidon"],
    ["Cronus", "parent_of", "Hades"],
    ["Zeus", "parent_of", "Ares"],
    ["Zeus", "parent_of", "Athena"],
    ["Zeus", "domain", "sky"],
    ["Poseidon", "domain", "sea"],
    ["Hades", "domain", "underworld"],
    ["Ares", "domain", "war"],
    ["Athena", "domain", "wisdom"],
    ["Uranus", "is_a", "primordial"],
    ["Cronus", "is_a", "titan"],
    ["Zeus", "is_a", "olympian"],
    ["Poseidon", "is_a", "olympian"],
    ["Hades", "is_a", "olympian"],
    ["Ares", "is_a", "olympian"],
    ["Athena", "is_a", "olympian"],
]


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY} if API_KEY else {}


def _get(path: str, timeout: int = 5, params: dict | None = None) -> requests.Response:
    return requests.get(
        f"{BACKEND_URL}{path}", headers=_headers(), params=params, timeout=timeout
    )


def _post(path: str, payload: dict, timeout: int = 30) -> requests.Response:
    return requests.post(
        f"{BACKEND_URL}{path}", json=payload, headers=_headers(), timeout=timeout
    )


def _put(path: str, payload: dict, timeout: int = 30) -> requests.Response:
    return requests.put(
        f"{BACKEND_URL}{path}", json=payload, headers=_headers(), timeout=timeout
    )


def _delete(path: str, params: dict | None = None, timeout: int = 30) -> requests.Response:
    return requests.delete(
        f"{BACKEND_URL}{path}", headers=_headers(), params=params, timeout=timeout
    )


_CACHE_MAX_ENTRIES = 64

if "response_cache" not in st.session_state:
    st.session_state["response_cache"] = {}

if st.session_state.get("_last_api_key") != API_KEY:
    st.session_state["_last_api_key"] = API_KEY
    st.session_state["response_cache"].clear()

if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "last_tool_empty" not in st.session_state:
    st.session_state["last_tool_empty"] = False


def _cache_key(method: str, path: str, payload: dict | None = None) -> str:
    if payload is None:
        return f"{method}:{path}"
    return f"{method}:{path}:{json.dumps(payload, sort_keys=True)}"


def _cache_put(key: str, response: requests.Response) -> None:
    cache = st.session_state["response_cache"]
    if len(cache) >= _CACHE_MAX_ENTRIES:
        cache.pop(next(iter(cache)), None)
    cache[key] = response


def _cached_get(path: str, timeout: int = 5) -> requests.Response:
    key = _cache_key("GET", path)
    cache = st.session_state["response_cache"]
    if key in cache:
        return cache[key]
    resp = _get(path, timeout=timeout)
    if resp.status_code < 400:
        _cache_put(key, resp)
    return resp


def _cached_post(path: str, payload: dict, timeout: int = 30) -> requests.Response:
    key = _cache_key("POST", path, payload)
    cache = st.session_state["response_cache"]
    if key in cache:
        return cache[key]
    resp = _post(path, payload, timeout=timeout)
    if resp.status_code < 400:
        _cache_put(key, resp)
    return resp


def invalidate_response_cache() -> None:
    st.session_state["response_cache"].clear()


def _body(resp: requests.Response) -> dict:
    try:
        data = resp.json()
    except Exception:
        return {"detail": resp.text[:300]}
    return data if isinstance(data, dict) else {"detail": data}


def render_sweep(sw: dict) -> None:
    m1, m2, m3 = st.columns(3)
    m1.metric("Fitted slope", f"{sw.get('slope', float('nan')):.4f}")
    m2.metric("r²", f"{sw.get('r_squared', float('nan')):.6f}")
    m3.metric("Metric", str(sw.get("metric", "?")))
    verdict = sw.get("verdict", "—")
    if "consistent" in verdict and "not" not in verdict:
        st.success(f"Verdict: {verdict}")
    else:
        st.warning(f"Verdict: {verdict}")
    try:
        eps = np.asarray(sw["epsilons"], dtype=float)
        errs = np.asarray(sw["errors"], dtype=float)
        st.caption("Raw: residual vs ε")
        st.line_chart(
            pd.DataFrame({"epsilon": eps, "residual": errs}).set_index("epsilon")
        )
        log_eps = np.log(eps)
        log_err = np.log(errs)
        fit = sw["slope"] * log_eps + sw["intercept"]
        st.caption("Log-log: log(residual) vs log(ε), with fitted line")
        st.line_chart(
            pd.DataFrame(
                {"log_eps": log_eps, "log_residual": log_err, "fit": fit}
            ).set_index("log_eps")
        )
        with st.expander("Raw values"):
            st.dataframe(
                pd.DataFrame(
                    {
                        "epsilon": eps,
                        "residual": errs,
                        "log_epsilon": log_eps,
                        "log_residual": log_err,
                    }
                )
            )
    except (KeyError, TypeError, ValueError) as e:
        st.error(f"Could not render sweep result: {e}")


def _status_chip(message: dict) -> None:
    status = message.get("status")
    chip = message.get("chip")
    router_class = message.get("router_class")
    if router_class:
        st.caption(str(router_class))
    if status == "ACCEPTED" or not chip:
        return
    label = {"conflict": "conflict", "abstained": "abstained", "no_rows": "no rows"}.get(
        chip, chip
    )
    st.markdown(f"`{label}`")


def _send_chat(text: str, *, force_class: str | None = None) -> None:
    payload = {
        "text": text,
        "hub_id": HUB_ID or "anon",
        "persona": PERSONA,
        "last_tool_empty": bool(st.session_state.get("last_tool_empty")),
    }
    if force_class:
        payload["force_class"] = force_class
    st.session_state["messages"].append(
        {"role": "user", "text": text, "pinned": False, "status": "ACCEPTED"}
    )
    try:
        resp = _post("/chat", payload, timeout=60)
    except requests.exceptions.RequestException as exc:
        st.session_state["messages"].append(
            {
                "role": "assistant",
                "text": f"Cannot reach the backend: {exc}",
                "status": "ABSTAINED",
                "chip": "abstained",
                "pinned": False,
            }
        )
        return
    body = _body(resp)
    if resp.status_code >= 400:
        detail = body.get("detail", resp.text[:300])
        st.session_state["messages"].append(
            {
                "role": "assistant",
                "text": str(detail),
                "status": "ABSTAINED",
                "chip": "abstained",
                "pinned": False,
            }
        )
        return
    status = body.get("status") or "ACCEPTED"
    st.session_state["last_tool_empty"] = status in {"NO_ROWS", "ABSTAINED"}
    st.session_state["messages"].append(
        {
            "role": "assistant",
            "text": body.get("reply_text") or "",
            "status": status,
            "chip": body.get("chip"),
            "memory_chip": bool(body.get("memory_chip")),
            "teach_affordance": bool(body.get("teach_affordance")),
            "router_class": body.get("router_class"),
            "pinned": False,
        }
    )
    if body.get("memory_chip") or status != "ACCEPTED":
        invalidate_response_cache()


st.sidebar.header("Titanos Topology")
if not API_KEY:
    st.sidebar.warning("Enter an API key to query the backend.")
else:
    try:
        stats = _cached_get("/stats").json()
        st.sidebar.metric("Total Learned Facts", stats.get("facts", 0))
        st.sidebar.metric("Active Entities", stats.get("entities", 0))
        st.sidebar.text(f"Core Dim: {stats.get('core_matrix', '-')}")
        st.sidebar.text(f"Latent Rank: {stats.get('latent_rank', '-')}")
        st.sidebar.text(f"Packet Protocol: v{stats.get('packet_version', '-')}")
        st.sidebar.text(f"Confidence Mode: {stats.get('conf_mode', 'sim')}")
    except Exception:
        st.sidebar.error("Cannot reach Titanos backend (check API key).")

if st.sidebar.button("Seed Greek mythos corpus"):
    try:
        res = _post("/learn_batch", {"facts": MYTHOS_SEED}, timeout=60).json()
        invalidate_response_cache()
        st.sidebar.success(
            f"Added {res.get('added', 0)} facts. Total: {res.get('records')}."
        )
    except Exception as e:
        st.sidebar.error(f"Seed failed: {e}")

st.sidebar.divider()
st.sidebar.header("Substrate")
try:
    sub = _cached_get("/substrate_stats").json()
    st.sidebar.metric("Training Steps", sub.get("training_steps", 0))
    st.sidebar.text(f"hidden_dim: {sub.get('hidden_dim', '-')}")
    st.sidebar.text(f"kernel_dim: {sub.get('kernel_dim', '-')}")
    st.sidebar.text(f"is_trained: {sub.get('is_trained', False)}")
    st.sidebar.text(f"bridge_locked: {sub.get('bridge_locked', True)}")
except Exception:
    st.sidebar.error("Cannot reach substrate backend.")

gear_open = st.sidebar.checkbox("Tools", value=False)

st.title("Resileos")
st.caption('Chat with the store. Teach with "remember that…".')

chat_col, memory_col = st.columns([3, 1], gap="large")

with chat_col:
    st.subheader("Chat")
    if not st.session_state["messages"]:
        st.caption("Ask a stored fact, or teach a preference.")
    for index, message in enumerate(st.session_state["messages"]):
        with st.chat_message(message["role"]):
            st.write(message.get("text") or "")
            if message.get("memory_chip"):
                st.markdown("`memory`")
            _status_chip(message)
            if message.get("status") == "MOUTH_CLOSED":
                st.caption("The mouth is closed for prose on this turn.")
            if message.get("teach_affordance"):
                st.caption('Teach affordance: say "remember that…"')
            pin_col, remember_col = st.columns(2)
            pin_label = "unpin" if message.get("pinned") else "pin"
            if pin_col.button(pin_label, key=f"pin-{index}"):
                message["pinned"] = not message.get("pinned")
                st.rerun()
            if message["role"] == "user" and remember_col.button(
                "+ remember", key=f"remember-{index}"
            ):
                _send_chat(message.get("text") or "", force_class="HUB_LEARN")
                st.rerun()
    pinned = [m for m in st.session_state["messages"] if m.get("pinned")]
    if pinned:
        st.caption("Pinned")
        for message in pinned:
            st.markdown(f"- {message.get('text') or ''}")

    with st.form("composer", clear_on_submit=True):
        draft = st.text_area(
            "Message", height=80, placeholder="remember that I prefer exact_answers"
        )
        send_col, remember_col = st.columns(2)
        send = send_col.form_submit_button("Send")
        remember = remember_col.form_submit_button("+ remember")
    if (send or remember) and draft.strip():
        _send_chat(draft.strip(), force_class="HUB_LEARN" if remember and not send else None)
        st.rerun()

with memory_col:
    st.subheader("Memory")
    hub = (HUB_ID or "anon").strip().lower()
    st.caption(f"user:{hub}")
    ledger = None
    try:
        resp = _get(f"/hub/{HUB_ID or 'anon'}/ledger", timeout=10)
        if resp.status_code < 400:
            ledger = _body(resp)
        else:
            st.warning(_body(resp).get("detail", resp.text[:200]))
    except requests.exceptions.RequestException as exc:
        st.error(f"Cannot load memory: {exc}")
    triples = (ledger or {}).get("triples") or []
    if ledger is not None and not triples:
        st.info(EMPTY_MEMORY)
    for index, triple in enumerate(triples):
        st.markdown(f"`{triple.get('relation')}`")
        st.write(triple.get("obj") or "")
        new_relation = st.text_input(
            "relation",
            value=triple.get("relation") or "",
            key=f"rel-{index}-{triple.get('relation')}",
        )
        new_obj = st.text_input(
            "obj",
            value=triple.get("obj") or "",
            key=f"obj-{index}-{triple.get('relation')}-{triple.get('obj')}",
        )
        save_col, delete_col = st.columns(2)
        if save_col.button("Save", key=f"save-{index}"):
            edited = _put(
                f"/hub/{HUB_ID}/ledger",
                {
                    "relation": triple.get("relation"),
                    "obj": triple.get("obj"),
                    "new_relation": new_relation,
                    "new_obj": new_obj,
                },
            )
            if edited.status_code >= 400:
                st.error(_body(edited).get("detail", edited.text[:200]))
            else:
                invalidate_response_cache()
                st.rerun()
        if delete_col.button("Delete", key=f"del-{index}"):
            removed = _delete(
                f"/hub/{HUB_ID}/ledger",
                params={"relation": triple.get("relation"), "obj": triple.get("obj")},
            )
            if removed.status_code >= 400:
                st.error(_body(removed).get("detail", removed.text[:200]))
            else:
                invalidate_response_cache()
                st.rerun()


def render_companion() -> None:
    hub_id = HUB_ID or "anon"
    st.subheader("Companion")
    try:
        resp = _get(f"/aphrodite/{hub_id}/state", timeout=10)
    except requests.exceptions.RequestException as exc:
        st.error(f"Cannot load companion: {exc}")
        return
    if resp.status_code >= 400:
        st.warning(str(_body(resp).get("detail", resp.text[:200])))
        return
    state = _body(resp)
    persona = state.get("persona") or {}
    st.caption(
        f"{persona.get('name', 'Companion')} · {persona.get('tone', '')} · {persona.get('sigil', '')}"
    )
    for step in state.get("steps") or []:
        mark = "done" if step.get("done") else "open"
        st.markdown(f"`{mark}` {step.get('label') or step.get('id')}")
    if state.get("last_fragment"):
        st.caption(str(state["last_fragment"]))
    with st.form("preference_form"):
        topic = st.text_input("Topic", value="tea")
        like = st.checkbox("Like", value=True)
        care = st.number_input("Care", min_value=1, max_value=5, value=1)
        sent = st.form_submit_button("Save preference")
    if sent and topic.strip():
        saved = _post(
            f"/aphrodite/{hub_id}/preference",
            {"topic": topic.strip(), "like": bool(like), "care": int(care)},
        )
        if saved.status_code >= 400:
            st.error(str(_body(saved).get("detail", saved.text[:200])))
        else:
            invalidate_response_cache()
            st.rerun()
    if st.button("Reset companion"):
        reset = _post(f"/aphrodite/{hub_id}/reset", {})
        if reset.status_code >= 400:
            st.error(str(_body(reset).get("detail", reset.text[:200])))
        else:
            invalidate_response_cache()
            st.rerun()


def render_lookup() -> None:
    st.subheader("Store lookup")
    goal = st.text_input("Goal", value="domain of Zeus", key="lookup_goal")
    subject = st.text_input("Subject", value="Zeus", key="lookup_subject")
    relation = st.text_input("Relation", value="domain", key="lookup_relation")
    if st.button("Run lookup", key="run_lookup"):
        resp = _post(
            "/task/lookup",
            {
                "goal": goal,
                "steps": [{"subject": subject, "relation": relation}],
                "persona": PERSONA,
            },
            timeout=60,
        )
        st.json(_body(resp))

    st.subheader("Perception")
    text = st.text_input("Text", value="hello", key="perc_lang")
    if st.button("Perceive language", key="run_lang"):
        resp = _post(
            "/perceive/language",
            {"text": text, "subject": "text", "commit": False},
        )
        st.json(_body(resp))
    if st.button("Perceive a short tone", key="run_audio"):
        resp = _post(
            "/perceive/audio",
            {"wave": [0.0, 0.2, 0.0, -0.2] * 8, "subject": "tone", "commit": False},
        )
        st.json(_body(resp))
    if st.button("Perceive a short clip", key="run_clip"):
        black = [0.0, 0.0, 0.0]
        white = [1.0, 1.0, 1.0]
        frame_a = [[black, white], [white, black]]
        frame_b = [[white, black], [black, white]]
        resp = _post(
            "/perceive/video",
            {"frames": [frame_a, frame_b], "subject": "clip", "commit": False},
        )
        st.json(_body(resp))

    st.subheader("Video")
    prompt = st.text_input("Prompt", value="", key="video_prompt")
    if st.button("Request video", key="run_video"):
        resp = _post("/generate/video", {"prompt": prompt})
        st.json(_body(resp))


def render_tools() -> None:
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
        [
            "Fact Ingestion",
            "Batch Upload",
            "Substrate Query",
            "Multi-Hop Chain",
            "ε-Sweep",
            "Companion",
            "Lookup",
        ]
    )

    with tab1:
        st.subheader("Memory Matrix Ingestion")
        with st.form("ingest_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                subject = st.text_input("Subject", placeholder="Zeus")
            with col2:
                relation = st.text_input("Relation", placeholder="parent_of")
            with col3:
                obj = st.text_input("Object", placeholder="Ares")
            submitted = st.form_submit_button("Commit to Substrate")
        if submitted:
            if subject and relation and obj:
                res = _post(
                    "/learn", {"subject": subject, "relation": relation, "obj": obj}
                ).json()
                if res.get("status") == "SUCCESS":
                    invalidate_response_cache()
                    st.success(f"Fact committed. Database size: {res['records']} facts.")
                    st.rerun()
            else:
                st.warning("Fill all three fields.")

    with tab2:
        st.subheader("Batch Ingestion")
        st.caption("CSV with columns: subject, relation, obj")
        uploaded = st.file_uploader("Upload CSV", type=["csv"])
        if uploaded is not None:
            try:
                frame = pd.read_csv(uploaded)
                st.dataframe(frame.head(20))
                if st.button("Commit all rows"):
                    facts = frame[["subject", "relation", "obj"]].astype(str).values.tolist()
                    res = _post("/learn_batch", {"facts": facts}, timeout=120).json()
                    invalidate_response_cache()
                    st.success(
                        f"Added {res.get('added', 0)} facts. Total: {res.get('records')}."
                    )
                    st.rerun()
            except Exception as e:
                st.error(f"Failed to parse CSV: {e}")

    with tab3:
        st.subheader("Substrate Probing & Abstention")
        query_subject = st.text_input("Target Entity/Value")
        query_relation = st.text_input("Target Relation Type")
        inverse = st.checkbox("Inverse query")
        if st.button("Query Residual Matrix"):
            if query_subject and query_relation:
                ans = _cached_post(
                    "/query",
                    {
                        "subject": query_subject,
                        "relation": query_relation,
                        "inverse": inverse,
                    },
                ).json()
                if ans.get("status") == "ABSTAINED":
                    st.warning(f"Engine abstained: {ans.get('reason')}")
                else:
                    badge = "CLASSICAL" if ans.get("mode") == "CLASSICAL" else "QUANTUM_SIM"
                    st.success(
                        f"[{badge}] {ans.get('value')} "
                        f"(confidence {ans.get('confidence', 0):.4f})"
                    )
                    if ans.get("trace"):
                        st.subheader("Core Convergence Telemetry")
                        trace = pd.DataFrame(ans["trace"])
                        st.dataframe(trace)
                        numeric_cols = [
                            c for c in ("scar", "delta", "deltas") if c in trace.columns
                        ]
                        if numeric_cols and len(trace) > 1:
                            st.line_chart(trace.set_index("loop")[numeric_cols])

    with tab4:
        st.subheader("Recursive Depth Chain")
        start = st.text_input("Starting entity")
        rels = st.text_input(
            "Comma-separated relations", placeholder="parent_of,parent_of"
        )
        if st.button("Execute Chain"):
            if start and rels:
                relations = [token.strip() for token in rels.split(",") if token.strip()]
                ans = _cached_post(
                    "/chain", {"start": start, "relations": relations}
                ).json()
                if ans.get("status") == "ACCEPTED":
                    st.success(f"Chain resolved: {ans['value']}")
                    st.json(ans["path"])
                else:
                    st.error(f"Chain broke: {ans.get('reason')}")

    with tab5:
        st.subheader("QD-TER ε-Sweep Verification")
        st.caption(
            "Numerical check of the linearized residual scaling in RES-600 §4. "
            "Runs the reduction ODE across multiple perturbation scales ε and "
            "fits log(residual) vs log(ε). A slope near 1 under the RMSE metric "
            "is consistent with the linear O(ε) bound."
        )
        st.info(
            "**Scope:** simulated Axiom D trajectory — self-consistency check "
            "only. This does not establish that Axiom D describes a real "
            "physical medium."
        )
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            sw_mode = st.selectbox("Mode", ["simulate", "data"])
        with col_b:
            sw_metric = st.selectbox("Metric", ["rmse", "mse"])
        with col_c:
            sw_seq_len = st.number_input("seq_len", min_value=4, max_value=512, value=64)
        with col_d:
            sw_gfield = st.number_input(
                "G field", min_value=0.0, max_value=5.0, value=0.85, step=0.05
            )
        sw_eps_str = st.text_input(
            "ε values (comma-separated)", value="0.1,0.05,0.02,0.01,0.005,0.001"
        )
        if st.button("Run ε-sweep", key="run_sweep"):
            try:
                eps_list = [float(x.strip()) for x in sw_eps_str.split(",") if x.strip()]
            except ValueError:
                st.error("Could not parse ε values.")
                eps_list = []
            if len(eps_list) < 2:
                st.error("At least two ε values required.")
            elif any(e <= 0 for e in eps_list):
                st.error("All ε values must be positive.")
            else:
                payload = {
                    "mode": sw_mode,
                    "metric": sw_metric,
                    "seq_len": int(sw_seq_len),
                    "g_field": float(sw_gfield),
                    "epsilons": eps_list,
                }
                try:
                    sweep_resp = _cached_post("/sweep_epsilon", payload, timeout=60)
                    if sweep_resp.status_code != 200:
                        st.error(
                            f"Sweep failed ({sweep_resp.status_code}): {sweep_resp.text[:300]}"
                        )
                    else:
                        render_sweep(sweep_resp.json())
                except requests.exceptions.RequestException as e:
                    st.error(f"Cannot reach backend: {e}")
        with st.expander("Or load a saved sweep report"):
            uploaded_report = st.file_uploader(
                "report_sweep.json", type=["json"], key="sweep_json"
            )
            if uploaded_report is not None:
                try:
                    render_sweep(json.loads(uploaded_report.read()))
                except Exception as e:
                    st.error(f"Could not parse JSON: {e}")

    with tab6:
        render_companion()

    with tab7:
        render_lookup()

    st.subheader("Studio")
    try:
        from resileos.studio.panel import render_residual_codec

        render_residual_codec(st)
    except Exception as exc:
        st.error(f"Studio panel failed to load: {exc}")


if gear_open:
    st.divider()
    st.subheader("Tools")
    render_tools()
