from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=get_settings().database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row, "autocommit": False},
        )
    return _pool


@contextmanager
def db_connection() -> Iterator[psycopg.Connection]:
    with get_pool().connection() as conn:
        yield conn


def ping_database() -> bool:
    try:
        with db_connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False
