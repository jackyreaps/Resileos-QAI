"""Tests for the expanded worker and task board."""
from resileos.ui.offline_tasks import TaskBoard, queue_learn
from resileos.ui.worker_tools import run_worker, worker_with_task


def test_numpy_and_grid():
    assert run_worker("np.arange(4).sum()")["result"] == 6
    g = run_worker("grid(2, 3, 1)")
    assert g["ok"] is True
    assert g["result"]["shape"] == [2, 3]


def test_scene_and_math():
    s = run_worker("scene('town', biome='coast')")
    assert s["result"]["name"] == "town"
    assert run_worker("math.sqrt(4)")["result"] == 2


def test_web_search_url():
    from resileos.ui.worker_tools import web_search
    out = web_search("lean theorem prover")
    assert "duckduckgo" in out["url"]
    out = worker_with_task("1+1", note="check")
    assert out["result"]["ok"] is True
    assert out["open"] == 0
    b = TaskBoard()
    t = b.add(queue_learn([{"subject": "a", "relation": "b", "obj": "c"}]))
    assert t["status"] == "queued"
    assert len(b.open()) == 1
