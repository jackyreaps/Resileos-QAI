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


def test_advance_runs_queue():
    from resileos.ui.worker_tools import advance, board
    from resileos.ui.offline_tasks import queue_worker
    board.add(queue_worker("1+1"))
    board.add(queue_worker("2+2"))
    out = advance(steps=2)
    assert len(out) == 2
    assert all(x["result"]["ok"] for x in out)
    from resileos.ui.worker_tools import complete_and_credit
    out = complete_and_credit("builders", "ada", "fix gate", evidence="tests passed")
    assert out["merit"]["relation"] == "merit"
    assert out["merit"]["attestation"]["status"] == "candidate"
    from resileos.ui.worker_tools import guild_board, run_next, board
    from resileos.ui.offline_tasks import queue_worker
    item = guild_board("builders", "fix gate")
    assert item["subject"] == "guild:builders"
    board.add(queue_worker("1+1"))
    out = run_next()
    assert out["result"]["ok"] is True
    from resileos.ui.worker_tools import run_shell
    out = run_shell("rm -rf /")
    assert out["ok"] is False
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
