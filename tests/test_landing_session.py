"""Run the Pages session tests under Node as part of pytest."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_pages_session_module():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for the Pages session tests")
    proc = subprocess.run(
        [
            node,
            "--test",
            "landing/functions/_auth.test.js",
            "landing/functions/_admin.test.js",
            "landing/functions/_reports.test.js",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
