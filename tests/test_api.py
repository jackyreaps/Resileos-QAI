"""
API tests: endpoints, gating, sweep harness.

Asserts:
    - substrate_stats is always available
    - verify_manifold is gated on is_trained
    - train_substrate flips is_trained after enough steps
    - sweep_epsilon runs ungated and returns a slope near 1 on simulated data
    - sweep_epsilon rejects malformed input
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import app as app_module  # noqa: E402
from app import app, substrate_singleton, HIDDEN_DIM  # noqa: E402


@pytest.fixture
def client():
    # Reset container state between tests
    substrate_singleton.is_trained = False
    substrate_singleton.training_steps = 0
    substrate_singleton.last_train_metrics = None
    return TestClient(app)


def test_substrate_stats_available(client):
    r = client.get("/api/v1/substrate_stats")
    assert r.status_code == 200
    body = r.json()
    assert body["hidden_dim"] == HIDDEN_DIM
    assert "is_trained" in body
    assert body["bridge_locked"] is True


def test_verify_manifold_gated_when_untrained(client):
    payload = {
        "hierarchical_states": [[[[0.0] * HIDDEN_DIM]]],
        "velocity_direction": [[[0.0] * HIDDEN_DIM]],
        "g_field_sequence": [[[0.0]]],
    }
    r = client.post("/api/v1/verify_manifold", json=payload)
    assert r.status_code == 400
    assert "UNTRAINED" in r.json()["detail"]


def test_train_flips_is_trained(client):
    r = client.post("/api/v1/train_substrate", json={
        "steps": 6, "seq_len": 16, "g_field": 0.85, "seed": 0,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_steps"] == 6
    assert body["is_trained"] is True
    assert len(body["history"]) == 6
    # Each step should report finite losses
    for h in body["history"]:
        assert h["geo"] == h["geo"]      # not NaN
        assert h["fep"] == h["fep"]


def test_train_rejects_bad_steps(client):
    r = client.post("/api/v1/train_substrate", json={"steps": 0})
    assert r.status_code == 400
    r = client.post("/api/v1/train_substrate", json={"steps": 10_000})
    assert r.status_code == 400


def test_sweep_runs_ungated(client):
    """Sweep must not require is_trained."""
    assert substrate_singleton.is_trained is False

    r = client.post("/api/v1/sweep_epsilon", json={
        "mode": "simulate",
        "metric": "rmse",
        "epsilons": [0.1, 0.05, 0.02, 0.01, 0.005, 0.001],
        "g_field": 0.85,
        "seq_len": 32,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["metric"] == "rmse"
    assert len(body["errors"]) == 6
    assert abs(body["slope"] - 1.0) < 0.2, body
    assert body["r_squared"] > 0.95
    assert "verdict" in body


def test_sweep_rejects_bad_metric(client):
    r = client.post("/api/v1/sweep_epsilon", json={
        "mode": "simulate", "metric": "l2",
    })
    assert r.status_code == 400


def test_sweep_rejects_short_epsilons(client):
    r = client.post("/api/v1/sweep_epsilon", json={
        "mode": "simulate", "epsilons": [0.1],
    })
    assert r.status_code == 400


def test_sweep_rejects_nonpositive_epsilons(client):
    r = client.post("/api/v1/sweep_epsilon", json={
        "mode": "simulate", "epsilons": [0.1, 0.0],
    })
    assert r.status_code == 400


def test_sweep_data_mode_requires_trajectory(client):
    r = client.post("/api/v1/sweep_epsilon", json={
        "mode": "data",
    })
    assert r.status_code == 400
