"""
DB connection helper with retry for DuckDB lock conflicts.

If Cursor/IDE or another process holds the DB file, connect() can fail with
"Conflicting lock". This module retries the connection a few times with a short
delay so the script can succeed once the lock is released.
"""
import time
from typing import Any

import duckdb


def connect_with_retry(
    db_path: str,
    read_only: bool = True,
    retries: int = 5,
    delay_seconds: float = 2.0,
    **kwargs: Any,
) -> duckdb.DuckDBPyConnection:
    """
    Connect to DuckDB with retries on lock conflict.

    Args:
        db_path: Path to the .duckdb file
        read_only: Use read_only=True for read-only connections
        retries: Number of connection attempts
        delay_seconds: Seconds to wait between attempts
        **kwargs: Passed to duckdb.connect (e.g. read_only=True)

    Returns:
        DuckDB connection

    Raises:
        Last exception if all retries fail
    """
    kwargs["read_only"] = read_only
    last_exc = None
    for attempt in range(retries):
        try:
            return duckdb.connect(db_path, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < retries - 1 and "lock" in str(e).lower():
                print(f"DuckDB lock conflict, retrying in {delay_seconds}s... ({attempt + 1}/{retries})")
                time.sleep(delay_seconds)
            else:
                raise
    raise last_exc
