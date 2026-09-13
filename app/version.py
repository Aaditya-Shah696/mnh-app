"""Which commit is running. Exposed on /api/health so CI can confirm a deploy.

Resolution order: DISCHARGE_GIT_SHA (set by the deploy script), then
`git rev-parse HEAD` in the checkout, then "unknown". Computed once at
import; a running process never changes commit.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _detect() -> str:
    env = os.environ.get("DISCHARGE_GIT_SHA", "").strip()
    if env:
        return env
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=5, check=True,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


GIT_SHA = _detect()
