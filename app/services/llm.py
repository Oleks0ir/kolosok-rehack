from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from app.settings import env


API_ROOT = "https://api.openai.com/v1"


def configured() -> bool:
    return bool(env("OPENAI_API_KEY"))


def _post(path: str, body: dict[str, Any]) -> dict[str, Any] | None:
    key = env("OPENAI_API_KEY")
    if not key:
        return None
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def complete_json(instructions: str, payload: Any) -> dict[str, Any] | None:
    result = _post(
        "/responses",
        {
            "model": env("OPENAI_MODEL", "gpt-6-luna"),
            "store": False,
            "instructions": instructions,
            "input": json.dumps(payload, ensure_ascii=False),
        },
    )
    if not result:
        return None
    text_parts: list[str] = []
    for item in result.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text_parts.append(content.get("text", ""))
    text = "\n".join(text_parts).strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    if not texts:
        return []
    result = _post(
        "/embeddings",
        {"model": "text-embedding-3-small", "input": texts, "encoding_format": "float"},
    )
    if not result:
        return None
    try:
        return [row["embedding"] for row in sorted(result["data"], key=lambda row: row["index"])]
    except (KeyError, TypeError):
        return None
