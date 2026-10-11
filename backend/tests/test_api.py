from fastapi.testclient import TestClient

from app import agent_runner
from app.db import get_conn, init_db
from app.main import app

client = TestClient(app)


def test_import_csv_creates_one_source_with_rows():
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE edges, nodes CASCADE")
            cur.execute("UPDATE node_counters SET next = 1")
    text = '﻿ref,text\nr1,"seats, too narrow"\nr2,quiet cabin\n'

    resp = client.post("/import/csv", json={"filename": "f.csv", "text": text, "created_by": "PM:alex"})

    assert resp.status_code == 200
    node = resp.json()
    assert node["type"] == "Source"
    assert node["content"] == {"file": "f.csv", "rows": [
        {"ref": "r1", "text": "seats, too narrow"}, {"ref": "r2", "text": "quiet cabin"}]}


def test_import_csv_rejects_header_only_file():
    resp = client.post("/import/csv", json={"filename": "f.csv", "text": "ref,text\n", "created_by": "PM:alex"})
    assert resp.status_code == 400


class _Running:
    returncode = None

    def __init__(self, *args, **kwargs):
        pass

    def poll(self):
        return None


def test_agent_run_refuses_a_second_run_while_one_is_going(monkeypatch):
    monkeypatch.setattr(agent_runner.subprocess, "Popen", _Running)
    monkeypatch.setattr(agent_runner, "_proc", None)

    assert client.post("/agent/run", json={"max_actions": 3}).json()["running"] is True
    assert client.post("/agent/run", json={"max_actions": 3}).status_code == 409
    assert client.post("/agent/run", json={"max_actions": 99}).status_code == 422


def test_datasets_list_and_import_by_name():
    listed = client.get("/datasets").json()
    assert {"name": "demo_feedback.csv", "rows": 12} in listed

    resp = client.post("/import/dataset", json={"name": "demo_feedback.csv", "created_by": "PM:alex"})
    assert resp.status_code == 200
    assert len(resp.json()["content"]["rows"]) == 12
    assert client.post("/import/dataset", json={"name": "../../.env", "created_by": "PM:alex"}).status_code == 404
