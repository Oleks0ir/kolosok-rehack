"""The decision graph's only write path (VISION.md "Write rules").

Nothing else is allowed to write nodes or edges — every agent tool and PM
action goes through add_node().
"""

import json
from typing import Any, Optional

from psycopg.types.json import Json

from .db import dict_cursor, get_conn
from .models import ID_PREFIX, NO_INPUT_REQUIRED, Node, NodeType, Relation


def _next_id(cur, node_type: NodeType) -> str:
    prefix = ID_PREFIX[node_type]
    cur.execute("SELECT count(*) AS n FROM nodes WHERE type = %s", (node_type.value,))
    n = cur.fetchone()["n"] + 1
    return f"{prefix}-{n:03d}"


def _row_to_node(row: dict[str, Any]) -> Node:
    row = dict(row)
    row["content"] = row["content"] if isinstance(row["content"], dict) else json.loads(row["content"])
    return Node(**row)


def add_node(
    type: NodeType,
    content: dict[str, Any],
    inputs: list[str],
    created_by: str,
    method: Optional[str] = None,
    rationale: Optional[str] = None,
    relation: Relation = Relation.DERIVED_FROM,
    replaces: Optional[str] = None,
) -> Node:
    """Write one new node, plus edges to the nodes it used as input.

    inputs: ids of nodes this one is derived from/scores/contradicts/decides.
    relation: the edge relation used for every (new_node -> input) edge.
    replaces: id of the node this is a new version of (versioning).
    """
    node_type = NodeType(type)

    if node_type == NodeType.DECISION and not created_by.startswith("PM:"):
        raise PermissionError("Decision nodes can only be created by the PM")

    if node_type not in NO_INPUT_REQUIRED and not inputs:
        raise ValueError(f"{node_type.value} nodes must have inputs")

    with get_conn() as conn:
        with dict_cursor(conn) as cur:
            version = 1
            if replaces:
                cur.execute("SELECT version FROM nodes WHERE id = %s", (replaces,))
                prev = cur.fetchone()
                if prev is None:
                    raise ValueError(f"replaces target {replaces} does not exist")
                version = prev["version"] + 1

            node_id = _next_id(cur, node_type)
            cur.execute(
                """
                INSERT INTO nodes (id, type, content, created_by, method, rationale, version, replaces)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (node_id, node_type.value, Json(content), created_by, method, rationale, version, replaces),
            )
            row = cur.fetchone()

            for input_id in inputs:
                cur.execute(
                    "INSERT INTO edges (from_id, to_id, relation) VALUES (%s, %s, %s)",
                    (node_id, input_id, relation.value),
                )

            if replaces:
                _mark_stale(cur, replaces)

    return _row_to_node(row)


def _mark_stale(cur, node_id: str) -> None:
    """Propagate staleness to every node that (transitively) depends on node_id."""
    seen = {node_id}
    frontier = [node_id]
    while frontier:
        cur.execute(
            "SELECT from_id FROM edges WHERE to_id = ANY(%s)",
            (frontier,),
        )
        next_frontier = [r["from_id"] for r in cur.fetchall() if r["from_id"] not in seen]
        seen.update(next_frontier)
        frontier = next_frontier

    cur.execute(
        "UPDATE nodes SET status = 'stale' WHERE id = ANY(%s)",
        (list(seen),),
    )


def get_node(node_id: str) -> Optional[Node]:
    with get_conn() as conn:
        with dict_cursor(conn) as cur:
            cur.execute("SELECT * FROM nodes WHERE id = %s", (node_id,))
            row = cur.fetchone()
    return _row_to_node(row) if row else None


def list_nodes(type: Optional[NodeType] = None) -> list[Node]:
    with get_conn() as conn:
        with dict_cursor(conn) as cur:
            if type:
                cur.execute("SELECT * FROM nodes WHERE type = %s ORDER BY timestamp", (NodeType(type).value,))
            else:
                cur.execute("SELECT * FROM nodes ORDER BY timestamp")
            rows = cur.fetchall()
    return [_row_to_node(r) for r in rows]


def get_inputs(node_id: str) -> list[Node]:
    with get_conn() as conn:
        with dict_cursor(conn) as cur:
            cur.execute(
                """
                SELECT n.* FROM nodes n
                JOIN edges e ON e.to_id = n.id
                WHERE e.from_id = %s
                """,
                (node_id,),
            )
            rows = cur.fetchall()
    return [_row_to_node(r) for r in rows]


def get_dependents(node_id: str) -> list[Node]:
    with get_conn() as conn:
        with dict_cursor(conn) as cur:
            cur.execute(
                """
                SELECT n.* FROM nodes n
                JOIN edges e ON e.from_id = n.id
                WHERE e.to_id = %s
                """,
                (node_id,),
            )
            rows = cur.fetchall()
    return [_row_to_node(r) for r in rows]
