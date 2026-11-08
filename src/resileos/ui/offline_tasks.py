"""Task board for offline and worker work.

A task has an id, a kind, a payload, and a status.
Statuses: queued, running, done, failed.
"""
from __future__ import annotations

from typing import Any


class TaskBoard:
    def __init__(self) -> None:
        self._tasks: list[dict[str, Any]] = []
        self._n = 0

    def add(self, task: dict[str, Any]) -> dict[str, Any]:
        self._n += 1
        row = {"id": self._n, "status": "queued", **task}
        self._tasks.append(row)
        return row

    def open(self) -> list[dict[str, Any]]:
        return [t for t in self._tasks if t["status"] in {"queued", "running"}]

    def complete(self, task_id: int, result: dict[str, Any]) -> dict[str, Any] | None:
        for t in self._tasks:
            if t["id"] == task_id:
                t["status"] = "done" if result.get("ok", True) else "failed"
                t["result"] = result
                return t
        return None

    def all(self) -> list[dict[str, Any]]:
        return list(self._tasks)


def queue_task(kind: str, payload: dict[str, Any], *, note: str = "") -> dict[str, Any]:
    return {"kind": kind, "payload": payload, "note": note, "status": "queued"}


def queue_learn(facts: list[dict[str, str]], *, note: str = "") -> dict[str, Any]:
    return queue_task("learn", {"facts": facts}, note=note)


def queue_worker(code: str, *, note: str = "") -> dict[str, Any]:
    return queue_task("worker", {"code": code}, note=note)
