from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def database_path() -> Path:
    raw = env("DATABASE_PATH", "data/workbench.sqlite3")
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def profile_path(profile_id: str) -> Path:
    safe_id = "".join(c for c in profile_id if c.isalnum() or c in "_-")
    return PROJECT_ROOT / "profiles" / f"{safe_id}.yaml"
