"""In-process deferred review.

The mouth can return a reply while a SeparatedCycle review runs on a
background thread. Nothing here commits a fact. Callers that learn do
so only after reviewers approve, inside the review function.
"""
from __future__ import annotations

import threading
from typing import Any, Callable


class ReviewHandle:
    def __init__(self) -> None:
        self.finished = threading.Event()
        self.started = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None
        self.thread: threading.Thread | None = None

    def done(self) -> bool:
        return self.finished.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self.finished.wait(timeout)


_lock = threading.Lock()
_handles: list[ReviewHandle] = []


def schedule_review(fn: Callable[[], Any]) -> ReviewHandle:
    """Start ``fn`` and return before it finishes."""
    handle = ReviewHandle()

    def run() -> None:
        handle.started.set()
        try:
            handle.result = fn()
        except BaseException as exc:  # noqa: BLE001 — the caller reads handle.error
            handle.error = exc
        finally:
            handle.finished.set()

    thread = threading.Thread(target=run, name="deferred-review", daemon=True)
    handle.thread = thread
    thread.start()
    with _lock:
        _handles.append(handle)
    return handle


def deliver(reply: Any, review_fn: Callable[[], Any]) -> tuple[Any, ReviewHandle]:
    """Return ``reply`` without waiting for ``review_fn``."""
    handle = schedule_review(review_fn)
    return reply, handle


def flush_reviews(timeout: float = 5.0) -> int:
    with _lock:
        handles = list(_handles)
    finished = 0
    for handle in handles:
        if handle.wait(timeout):
            finished += 1
    return finished
