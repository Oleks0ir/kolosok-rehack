"""Import a CSV file as one Source node, rows included, so query_data has real data to read.

Usage (backend running): python seed.py sample_data/demo_feedback.csv

shortcut: stand-in for the ingestion module; replace with its import once that exists.
"""

import csv
import sys
from pathlib import Path

import requests

from loop import API_BASE


def seed(path: str) -> dict:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    resp = requests.post(f"{API_BASE}/tools/import_source", json={
        "content": {"file": Path(path).name, "rows": rows},
        "created_by": "import:seed",
        "rationale": "seeded so the agent loop has real rows to extract evidence from",
    })
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    node = seed(sys.argv[1])
    print(node["id"], node["content"]["file"], len(node["content"]["rows"]), "rows")
