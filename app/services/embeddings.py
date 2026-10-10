from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

from app.services.llm import embed_texts


def _local_vector(text: str, dimensions: int = 128) -> list[float]:
    vector = [0.0] * dimensions
    tokens = re.findall(r"[a-z0-9äöüß]+", text.lower())
    counts = Counter(tokens)
    for token, count in counts.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "little") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def vectors_for(texts: list[str]) -> tuple[list[list[float]], str]:
    remote = embed_texts(texts)
    if remote and len(remote) == len(texts):
        return remote, "openai:text-embedding-3-small"
    return [_local_vector(text) for text in texts], "local-hash-v1"


def query_vector(text: str, stored_kind: str) -> list[float]:
    if stored_kind == "local-hash-v1":
        return _local_vector(text)
    if stored_kind.startswith("openai:"):
        remote = embed_texts([text])
        return remote[0] if remote else []
    return _local_vector(text)


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))
