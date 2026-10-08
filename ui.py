"""
Streamlit dashboard for the Titanos engine.

Run (after app.py is up on :8000):
    streamlit run ui.py --server.port 8501
"""
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Titanos Engine Console", layout="wide")
st.title("Titanos Substrate Management Console")

BACKEND_URL = "http://localhost:8000/api/v1"

st.sidebar.header("System Topology")
try:
    stats = requests.get(f"{BACKEND_URL}/stats", timeout=5).json()
    st.sidebar.metric("Total Learned Facts", stats["facts"])
    st.sidebar.metric("Active Entities", stats["entities"])
    st.sidebar.text(f"Core Dim: {stats['core_matrix']}")
    st.sidebar.text(f"Latent Rank: {stats['latent_rank']}")
    st.sidebar.text(f"Packet Protocol: v{stats['packet_version']}")
except Exception:
    st.sidebar.error("Cannot connect to Titanos backend.")

tab1, tab2, tab3, tab4 = st.tabs(
    ["Fact Ingestion", "Batch Upload", "Substrate Query", "Multi-Hop Chain"]
)

# ── tab 1: single fact ────────────────────────────────────────────────────
with tab1:
    st.subheader("Memory Matrix Ingestion")
    with st.form("ingest_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            s = st.text_input("Subject", placeholder="Zeus")
        with col2:
            r = st.text_input("Relation", placeholder="parent_of")
        with col3:
            o = st.text_input("Object", placeholder="Ares")
        submitted = st.form_submit_button("Commit to Substrate")

    if submitted:
        if s and r and o:
            res = requests.post(
                f"{BACKEND_URL}/learn",
                json={"subject": s, "relation": r, "obj": o},
                timeout=30,
            ).json()
            if res.get("status") == "SUCCESS":
                st.success(f"Fact committed. Database size: {res['records']} facts.")
                st.rerun()
        else:
            st.warning("Fill all three fields.")

# ── tab 2: batch upload ───────────────────────────────────────────────────
with tab2:
    st.subheader("Batch Ingestion")
    st.caption("CSV with columns: subject, relation, obj")
    uploaded = st.file_uploader("Upload CSV", type=["csv"])

    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
            st.dataframe(df.head(20))
            if st.button("Commit all rows"):
                facts = df[["subject", "relation", "obj"]].astype(str).values.tolist()
                res = requests.post(
                    f"{BACKEND_URL}/learn_batch",
                    json={"facts": facts},
                    timeout=120,
                ).json()
                st.success(f"Added {res.get('added', 0)} facts. Total: {res.get('records')}.")
                st.rerun()
        except Exception as e:
            st.error(f"Failed to parse CSV: {e}")

# ── tab 3: query ──────────────────────────────────────────────────────────
with tab3:
    st.subheader("Substrate Probing & Abstention")
    q_s = st.text_input("Target Entity/Value")
    q_r = st.text_input("Target Relation Type")
    q_inv = st.checkbox("Inverse query")

    if st.button("Query Residual Matrix"):
        if q_s and q_r:
            ans = requests.post(
                f"{BACKEND_URL}/query",
                json={"subject": q_s, "relation": q_r, "inverse": q_inv},
                timeout=30,
            ).json()

            if ans.get("status") == "ABSTAINED":
                st.warning(f"Engine abstained: {ans.get('reason')}")
            else:
                badge = "CLASSICAL" if ans.get("mode") == "CLASSICAL" else "QUANTUM_SIM"
                st.success(
                    f"[{badge}] {ans.get('value')}  "
                    f"(confidence {ans.get('confidence', 0):.4f})"
                )

            if ans.get("trace"):
                st.subheader("Core Convergence Telemetry")
                df = pd.DataFrame(ans["trace"])
                if "scar" in df.columns:
                    st.dataframe(df.style.highlight_max(axis=0, subset=["scar"]))
                else:
                    st.dataframe(df)

# ── tab 4: chain ──────────────────────────────────────────────────────────
with tab4:
    st.subheader("Recursive Depth Chain")
    c_start = st.text_input("Starting entity")
    c_rels = st.text_input("Comma-separated relations", placeholder="parent_of,parent_of")

    if st.button("Execute Chain"):
        if c_start and c_rels:
            relations = [t.strip() for t in c_rels.split(",") if t.strip()]
            ans = requests.post(
                f"{BACKEND_URL}/chain",
                json={"start": c_start, "relations": relations},
                timeout=30,
            ).json()
            if ans.get("status") == "ACCEPTED":
                st.success(f"Chain resolved: {ans['value']}")
                st.json(ans["path"])
            else:
                st.error(f"Chain broke: {ans.get('reason')}")
