from __future__ import annotations

from typing import Any

import yaml

from app.settings import profile_path


def load_profile(profile_id: str) -> dict[str, Any]:
    path = profile_path(profile_id)
    if not path.is_file():
        raise ValueError(f"Unknown profile: {profile_id}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data["id"] = profile_id
    weights = data.get("weights", {})
    total = sum(max(0.0, float(v)) for v in weights.values()) or 1.0
    data["weights"] = {k: max(0.0, float(v)) / total for k, v in weights.items()}
    return data


def apply_overrides(profile: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = {**profile, **overrides}
    if "weights" in overrides:
        weights = overrides["weights"]
        if not isinstance(weights, dict) or not weights:
            raise ValueError("Weight overrides must be a non-empty object")
        normalized = {str(k): max(0.0, float(v)) for k, v in weights.items()}
        total = sum(normalized.values())
        if total <= 0:
            raise ValueError("At least one scoring weight must be greater than zero")
        result["weights"] = {k: v / total for k, v in normalized.items()}
    return result
