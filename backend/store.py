"""Small SQLite store for locally saved input windows and forecast history."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def database_path(path: str | Path | None = None) -> Path:
    configured = path or os.environ.get("GRIDSENSE_DB_PATH") or ROOT / "data" / "gridsense.sqlite3"
    resolved = Path(configured).expanduser()
    if not resolved.is_absolute():
        resolved = ROOT / resolved
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _connect(path: str | Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path(path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


@contextmanager
def _database(path: str | Path | None = None):
    connection = _connect(path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_store(path: str | Path | None = None) -> None:
    with _database(path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS datasets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source TEXT NOT NULL,
                row_count INTEGER NOT NULL CHECK(row_count = 24),
                rows_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS forecasts (
                id TEXT PRIMARY KEY,
                dataset_id TEXT REFERENCES datasets(id) ON DELETE SET NULL,
                dataset_name TEXT NOT NULL,
                input_source TEXT NOT NULL,
                model_source TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS forecasts_generated_at_idx ON forecasts(generated_at DESC);
            CREATE INDEX IF NOT EXISTS datasets_created_at_idx ON datasets(created_at DESC);
            """
        )


def _name(value: Any) -> str:
    name = " ".join(str(value or "").split())
    if not name:
        raise ValueError("Give this data set a name before saving it.")
    if len(name) > 100:
        raise ValueError("Data set names must be 100 characters or fewer.")
    return name


def _metadata(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "source": row["source"],
        "row_count": row["row_count"],
        "created_at": row["created_at"],
    }


def save_dataset(name: Any, source: Any, rows: list[dict[str, Any]], path: str | Path | None = None) -> dict[str, Any]:
    dataset_name = _name(name)
    row_json = json.dumps(rows, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    dataset_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    source_label = " ".join(str(source or "Manual entry").split())[:120] or "Manual entry"
    with _database(path) as connection:
        connection.execute(
            "INSERT INTO datasets (id, name, source, row_count, rows_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (dataset_id, dataset_name, source_label, len(rows), row_json, created_at),
        )
    return {"id": dataset_id, "name": dataset_name, "source": source_label, "row_count": len(rows), "created_at": created_at}


def list_datasets(path: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with _database(path) as connection:
        rows = connection.execute(
            "SELECT id, name, source, row_count, created_at FROM datasets ORDER BY created_at DESC LIMIT ?",
            (max(1, min(int(limit), 100)),),
        ).fetchall()
    return [_metadata(row) for row in rows]


def get_dataset(dataset_id: str, path: str | Path | None = None) -> dict[str, Any] | None:
    with _database(path) as connection:
        row = connection.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    if row is None:
        return None
    return {**_metadata(row), "rows": json.loads(row["rows_json"])}


def delete_dataset(dataset_id: str, path: str | Path | None = None) -> bool:
    with _database(path) as connection:
        cursor = connection.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
    return cursor.rowcount > 0


def save_forecast(forecast: dict[str, Any], *, dataset_id: str, dataset_name: str, input_source: str, path: str | Path | None = None) -> None:
    summary_json = json.dumps(forecast["summary"], ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    payload_json = json.dumps(forecast, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    with _database(path) as connection:
        connection.execute(
            """INSERT INTO forecasts
               (id, dataset_id, dataset_name, input_source, model_source, generated_at, summary_json, payload_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                forecast["forecast_id"],
                dataset_id,
                dataset_name,
                input_source,
                forecast["model_source"],
                forecast["generated_at"],
                summary_json,
                payload_json,
            ),
        )


def list_forecasts(path: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with _database(path) as connection:
        rows = connection.execute(
            """SELECT id, dataset_id, dataset_name, input_source, model_source, generated_at, summary_json
               FROM forecasts ORDER BY generated_at DESC LIMIT ?""",
            (max(1, min(int(limit), 100)),),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "dataset_id": row["dataset_id"],
            "dataset_name": row["dataset_name"],
            "input_source": row["input_source"],
            "model_source": row["model_source"],
            "generated_at": row["generated_at"],
            "summary": json.loads(row["summary_json"]),
        }
        for row in rows
    ]


def get_forecast(forecast_id: str, path: str | Path | None = None) -> dict[str, Any] | None:
    with _database(path) as connection:
        row = connection.execute("SELECT payload_json FROM forecasts WHERE id = ?", (forecast_id,)).fetchone()
    return json.loads(row["payload_json"]) if row else None
