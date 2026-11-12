"""Regression tests for the audit fixes."""
from __future__ import annotations

import json
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]


def test_query_response_is_json_and_credit_denial_is_402():
    from app import QueryRequest, titanos_query

    body = titanos_query(QueryRequest(subject="Zeus", relation="domain"))
    json.dumps(body)
    denied = QueryRequest(
        subject="Zeus", relation="domain", member="audit-broke", used_free=100,
    )
    with pytest.raises(HTTPException) as caught:
        titanos_query(denied)
    assert caught.value.status_code == 402


def test_allow_use_does_not_drive_free_negative():
    from resileos.ui.use_gate import allow_use

    over = allow_use("ada", units=100, used_free=0)
    assert over["ok"] is False
    assert over["remaining_free"] == 20
    edge = allow_use("ada", units=5, used_free=19)
    assert edge["ok"] is False
    assert edge["remaining_free"] == 1
    assert allow_use("ada", units=1, used_free=0)["remaining_free"] == 19


def test_ask_abstains_when_fact_list_is_empty():
    from titanos import Titanos, TitanosConfig

    t = Titanos(TitanosConfig(dim=256, m=16, n=16, r=4, n_loops=4, seed=1))
    t.learn_many([
        ("alice", "parent_of", "bob"),
        ("bob", "parent_of", "carol"),
    ])
    forward = t.ask("carol", "parent_of")
    inverse = t.ask_inverse("alice", "parent_of")
    assert t.ask_list("carol", "parent_of") == []
    assert t.ask_list("alice", "parent_of", inverse=True) == []
    assert forward.status == "ABSTAINED"
    assert forward.value is None
    assert inverse.status == "ABSTAINED"
    assert inverse.value is None
    stored = t.ask("bob", "parent_of")
    assert stored.status == "ACCEPTED"
    assert stored.value == "carol"


def test_cycle_fact_check_sees_the_learned_value():
    from resileos.ui.language_codex import cycle

    store = {}

    def query(s, r):
        return store.get((s, r))

    def learn(s, r, o):
        store[(s, r)] = o

    out = cycle(
        query, learn, kind="user", name="ada", relation="domain",
        obj="sky", claimed="sky",
    )
    assert out["fact_check"]["status"] == "match"
    assert out["lookup"]["obj"] == "sky"


def test_perceive_into_zero_motion_and_tokens():
    from resileos.kin.perceive_into import perception_scalar, perceive_into
    from resileos.kin.psyche import Psyche

    assert perception_scalar({"mean_luma": 0.0, "energy": 0.9}) == 0.0
    assert perception_scalar({"motion": 0.0, "mean_luma": 0.8}) == 0.0
    assert perception_scalar({"motion": 3.5, "mean_luma": 0.2}) == 3.5
    assert perception_scalar({"tokens": 4}) == 4.0
    psyche = Psyche()
    perceive_into(psyche, {"motion": 1.5, "mean_luma": 0.1, "address": {}})
    assert psyche.state["drives"]["endocrine"] == 1.5


def test_judge_without_eat_abstains():
    from resileos.kin.athena import judge

    out = judge([{"subject": "image", "address": {"residual_bin": "rcore_low"}}])
    assert out["gate"]["frame"] == "abstained"
    assert out["ok"] is False


def test_frame_codec_round_trip_and_perceive_bin():
    from resileos.ui.frame_codec import decode_frame, encode_clip, encode_frame
    from resileos.ui.make_world import make_still
    from resileos.ui.perceive_image import perceive_image
    from resileos.ui.perceive_video import perceive_video

    image = np.zeros((24, 24, 3), dtype=np.uint8)
    image[::2] = 255
    coded = encode_frame(image)
    decoded = decode_frame(coded)
    factor_mse = float(np.mean((decoded - coded["reconstruction"]) ** 2))
    assert factor_mse < 1e-5
    assert coded["mse"] >= 0.0
    assert coded["packet_hash"]
    assert coded["scar_matrix_updated"] is False
    assert coded["learned"] is False
    assert coded["residual_bin"].startswith("rcore_")
    perceived = perceive_image(image, subject="photo")
    assert perceived["address"]["residual_bin"] == coded["residual_bin"]
    assert perceived["codec"]["engine"] == "ResidualCore"
    frames = np.stack([image, np.roll(image, 1, axis=0)])
    clip = encode_clip(frames)
    assert clip["frames_encoded"] == 2
    assert clip["mse"] >= 0.0
    video = perceive_video(frames, subject="clip")
    assert video["codec"]["engine"] == "ResidualCore"
    still = make_still("a field", world_id="world:audit")
    assert still["compression"]["engine"] == "ResidualCore"
    assert "did not generate" in still["compression_note"]


def test_empty_waveform_does_not_warn():
    from resileos.ui.perceive_audio import perceive_audio

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        out = perceive_audio(np.zeros(0, dtype=np.float32), subject="silence")
    assert out["energy"] == 0.0


def test_shell_allowlist_does_not_invoke_a_shell(tmp_path, monkeypatch):
    import resileos.ui.worker_tools as wt

    monkeypatch.setattr(wt, "WORKSPACE", tmp_path)
    marker = tmp_path / "pwned"
    injected = wt.git_commit(f'x"; touch {marker}; echo "')
    assert injected["ok"] is False
    assert not marker.exists()
    blocked = wt.run_shell(f"touch {marker}")
    assert blocked["ok"] is False
    assert not marker.exists()
    chained = wt.run_shell("git status; touch pwned")
    assert chained["ok"] is False
    assert not marker.exists()
    status = wt.run_shell(["git", "status", "--short"])
    assert "error" in status or "code" in status
    assert status.get("error") != "command not allowed"


def test_learn_queue_writes_the_hub():
    from resileos.ui.offline_tasks import queue_learn
    from resileos.ui.worker_tools import board, hub_workbench, run_next

    while board.open():
        run_next()
    board.add(queue_learn([
        {"subject": "world:auditfix", "relation": "status", "obj": "stored"},
    ]))
    out = run_next()
    assert out["result"]["ok"] is True
    assert out["result"]["learned"] == 1
    rows = hub_workbench().ask_rows("world:auditfix", "status")
    assert "stored" in rows


def test_attestation_matches_schema():
    import jsonschema

    from resileos.ui.worker_tools import record_merit

    schema = json.loads((ROOT / "schemas" / "attestation.v1.json").read_text())
    merit = record_merit("builders", "ada", "fix gate", evidence="tests passed")
    jsonschema.validate(merit["attestation"], schema)
    assert "signature" not in merit["attestation"]


def test_bench_scripts_parse_and_p50_is_the_median():
    import importlib.util

    for name in ("bench_compositional.py", "bench_invention.py", "bench_vs_llm.py"):
        path = ROOT / "scripts" / "ops" / name
        compile(path.read_text(), str(path), "exec")
    spec = importlib.util.spec_from_file_location(
        "bench_vs_llm_mod", ROOT / "scripts" / "ops" / "bench_vs_llm.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.median([1.0, 2.0, 100.0]) == 2.0
    assert mod.median([1.0, 3.0]) == 2.0


def test_src_path_imports_titanos_and_app():
    code = (
        "import app, titanos, run_hybrid; "
        "assert titanos.TitanosConfig; "
        "assert callable(titanos.Titanos); "
        "assert app.QueryRequest; "
        "assert run_hybrid"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd="/tmp",
        env={
            **{k: v for k, v in __import__("os").environ.items() if k != "PYTHONPATH"},
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]


def test_studio_caption_is_not_a_multilingual_claim():
    text = (ROOT / "src" / "resileos" / "ui" / "studio_app.py").read_text()
    assert "Multilingual is the default path" not in text
    assert "script guess" in text
