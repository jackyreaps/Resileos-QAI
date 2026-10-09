"""
Streamlit dashboard for the Resileos-QAI console.

Run (after app.py is up on :8000):
    streamlit run ui.py --server.port 8501
"""
import json

import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Resileos-QAI Console", layout="wide")
st.title("Resileos-QAI Console")

BACKEND_URL = "http://localhost:8000/api/v1"

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


# ── sweep renderer (used by both live run and file load) ────────────────
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
            pd.DataFrame({
                "log_eps": log_eps,
                "log_residual": log_err,
                "fit": fit,
            }).set_index("log_eps")
        )

        with st.expander("Raw values"):
            st.dataframe(
                pd.DataFrame({
                    "epsilon": eps,
                    "residual": errs,
                    "log_epsilon": log_eps,
                    "log_residual": log_err,
                })
            )
    except (KeyError, TypeError, ValueError) as e:
        st.error(f"Could not render sweep result: {e}")


# ── sidebar ─────────────────────────────────────────────────────────────
st.sidebar.header("Titanos Topology")
try:
    stats = requests.get(f"{BACKEND_URL}/stats", timeout=5).json()
    st.sidebar.metric("Total Learned Facts", stats.get("facts", 0))
    st.sidebar.metric("Active Entities", stats.get("entities", 0))
    st.sidebar.text(f"Core Dim: {stats.get('core_matrix', '-')}")
    st.sidebar.text(f"Latent Rank: {stats.get('latent_rank', '-')}")
    st.sidebar.text(f"Packet Protocol: v{stats.get('packet_version', '-')}")
    st.sidebar.text(f"Confidence Mode: {stats.get('conf_mode', 'sim')}")
except Exception:
    st.sidebar.error("Cannot reach Titanos backend.")

if st.sidebar.button("Seed Greek mythos corpus"):
    try:
        res = requests.post(
            f"{BACKEND_URL}/learn_batch",
            json={"facts": MYTHOS_SEED},
            timeout=60,
        ).json()
        st.sidebar.success(
            f"Added {res.get('added', 0)} facts. Total: {res.get('records')}."
        )
    except Exception as e:
        st.sidebar.error(f"Seed failed: {e}")

st.sidebar.divider()
st.sidebar.header("Substrate")
try:
    sub = requests.get(f"{BACKEND_URL}/substrate_stats", timeout=5).json()
    st.sidebar.metric("Training Steps", sub.get("training_steps", 0))
    st.sidebar.text(f"hidden_dim: {sub.get('hidden_dim', '-')}")
    st.sidebar.text(f"kernel_dim: {sub.get('kernel_dim', '-')}")
    st.sidebar.text(f"is_trained: {sub.get('is_trained', False)}")
    st.sidebar.text(f"bridge_locked: {sub.get('bridge_locked', True)}")
except Exception:
    st.sidebar.error("Cannot reach substrate backend.")


# ── tabs ────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Fact Ingestion", "Batch Upload", "Substrate Query",
     "Multi-Hop Chain", "ε-Sweep"]
)


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
                st.success(
                    f"Added {res.get('added', 0)} facts. Total: {res.get('records')}."
                )
                st.rerun()
        except Exception as e:
            st.error(f"Failed to parse CSV: {e}")


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
                st.dataframe(df)
                numeric_cols = [c for c in ("scar", "delta", "deltas") if c in df.columns]
                if numeric_cols and len(df) > 1:
                    st.line_chart(df.set_index("loop")[numeric_cols])


with tab4:
    st.subheader("Recursive Depth Chain")
    c_start = st.text_input("Starting entity")
    c_rels = st.text_input(
        "Comma-separated relations", placeholder="parent_of,parent_of"
    )

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
        "ε values (comma-separated)",
        value="0.1,0.05,0.02,0.01,0.005,0.001",
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
                r = requests.post(
                    f"{BACKEND_URL}/sweep_epsilon", json=payload, timeout=60
                )
                if r.status_code != 200:
                    st.error(f"Sweep failed ({r.status_code}): {r.text[:300]}")
                else:
                    render_sweep(r.json())
            except requests.exceptions.RequestException as e:
                st.error(f"Cannot reach backend: {e}")

    with st.expander("Or load a saved sweep report"):
        up = st.file_uploader("report_sweep.json", type=["json"], key="sweep_json")
        if up is not None:
            try:
                render_sweep(json.loads(up.read()))
            except Exception as e:
                st.error(f"Could not parse JSON: {e}")
