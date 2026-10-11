"""Starts agent-loop/loop.py as its own process so the GUI can trigger runs.

The loop still talks to this API over HTTP only, exactly as when run from the CLI;
the backend never imports agent-loop code. One run at a time.
shortcut: loop.py's API_BASE is hardcoded to localhost:8000, so runs only work when the
backend listens there; pass the URL through the env if that ever changes.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

LOOP_DIR = Path(__file__).resolve().parents[2] / "agent-loop"
LOG = Path(tempfile.gettempdir()) / "decision-graph-agent.log"
_proc: Optional[subprocess.Popen] = None


def _python() -> str:
    """agent-loop has its own venv (openai, requests); fall back to this interpreter."""
    for p in (LOOP_DIR / ".venv" / "Scripts" / "python.exe", LOOP_DIR / ".venv" / "bin" / "python"):
        if p.exists():
            return str(p)
    return sys.executable


def start(max_actions: int) -> None:
    global _proc
    if _proc and _proc.poll() is None:
        raise RuntimeError("the agent is already running")
    with open(LOG, "w", encoding="utf-8") as log:
        _proc = subprocess.Popen(
            [_python(), "loop.py", str(max_actions)], cwd=LOOP_DIR, stdout=log,
            stderr=subprocess.STDOUT, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )


def status() -> dict:
    running = bool(_proc and _proc.poll() is None)
    return {
        "running": running,
        "exit_code": None if running or _proc is None else _proc.returncode,
        "llm": bool(os.environ.get("OPENAI_API_KEY")),  # without a key the loop is rule-based
        "log": LOG.read_text(encoding="utf-8", errors="replace")[-3000:] if LOG.exists() else "",
    }
