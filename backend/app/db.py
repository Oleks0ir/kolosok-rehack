import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://kolosok:kolosok@localhost:5432/decision_graph"
)

_SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text()


@contextmanager
def get_conn():
    conn = psycopg.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_SCHEMA_SQL)


def dict_cursor(conn):
    return conn.cursor(row_factory=dict_row)
