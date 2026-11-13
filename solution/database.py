
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "interaction_ledger.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    return connection


def initialize_database():
    connection = get_connection()

    try:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                phone_hash TEXT NOT NULL,
                encrypted_data TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                external_ref TEXT,
                UNIQUE(workflow_id, phone_hash)
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                call_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                phone_hash TEXT,
                encrypted_event TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orphan_events (
                event_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                reason TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rejections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                row_number INTEGER NOT NULL,
                reason TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS processed_files (
                file_path TEXT PRIMARY KEY,
                file_type TEXT NOT NULL,
                processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_events_call_id
            ON events(call_id);

            CREATE INDEX IF NOT EXISTS idx_events_phone
            ON events(workflow_id, phone_hash);
        """)

        # Add lead_id column if it does not exist
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(events)"
            ).fetchall()
        }

        if "lead_id" not in columns:
            connection.execute(
                "ALTER TABLE events ADD COLUMN lead_id INTEGER"
            )

        connection.commit()

    finally:
        connection.close()
