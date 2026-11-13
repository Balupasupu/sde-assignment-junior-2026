
import json
from pathlib import Path

from normalization import normalize_phone
from security import hash_phone, encrypt_text
from database import get_connection


def read_event_file(file_path):
    events = []
    malformed_events = 0

    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            try:
                event = json.loads(line)

                if not isinstance(event, dict) or not event.get("event_id"):
                    malformed_events += 1
                    continue

                required = [
                    "event_type",
                    "workflow_id",
                    "call_id",
                    "occurred_at",
                ]

                if any(not event.get(key) for key in required):
                    malformed_events += 1
                    continue

                events.append(event)

            except json.JSONDecodeError:
                malformed_events += 1

    return events, malformed_events


def normalize_event(event):
    normalized = event.copy()

    if normalized.get("phone"):
        normalized["phone"] = normalize_phone(normalized["phone"])

    return normalized


def find_lead_by_phone(workflow_id, phone):
    if not phone:
        return None

    phone_hash = hash_phone(phone)
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT id FROM leads
            WHERE workflow_id = ? AND phone_hash = ?
            """,
            (workflow_id, phone_hash),
        ).fetchone()

        return row["id"] if row else None
    finally:
        connection.close()


def find_lead_by_call_id(call_id):
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT lead_id FROM events
            WHERE call_id = ? AND lead_id IS NOT NULL
            LIMIT 1
            """,
            (call_id,),
        ).fetchone()

        return row["lead_id"] if row else None
    finally:
        connection.close()


def resolve_lead_id(event):
    phone = event.get("phone")

    if phone:
        lead_id = find_lead_by_phone(event["workflow_id"], phone)
        if lead_id is not None:
            return lead_id

    return find_lead_by_call_id(event["call_id"])


def save_event(event, lead_id):
    phone = event.get("phone")
    phone_hash = hash_phone(phone) if phone else None

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO events (
                event_id, event_type, workflow_id, call_id,
                occurred_at, phone_hash, encrypted_event, lead_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event["event_type"],
                event["workflow_id"],
                event["call_id"],
                event["occurred_at"],
                phone_hash,
                encrypt_text(json.dumps(event)),
                lead_id,
            ),
        )

        # If event already exists, only update its link metadata.
        if cursor.rowcount == 0 and lead_id is not None:
            connection.execute(
                """
                UPDATE events
                SET lead_id = ?
                WHERE event_id = ? AND lead_id IS NULL
                """,
                (lead_id, event["event_id"]),
            )

        connection.commit()
        return "inserted" if cursor.rowcount == 1 else "duplicate"

    finally:
        connection.close()


def quarantine_orphan(event):
    connection = get_connection()

    try:
        connection.execute(
            """
            INSERT OR IGNORE INTO orphan_events (
                event_id, workflow_id, reason
            )
            VALUES (?, ?, ?)
            """,
            (
                event["event_id"],
                event["workflow_id"],
                "matching_lead_not_found",
            ),
        )
        connection.commit()

    finally:
        connection.close()


def remove_orphan(event_id):
    connection = get_connection()

    try:
        connection.execute(
            "DELETE FROM orphan_events WHERE event_id = ?",
            (event_id,),
        )
        connection.commit()

    finally:
        connection.close()


def ingest_event_file(file_path):
    events, malformed_events = read_event_file(file_path)

    inserted = 0
    duplicates = 0
    orphan_count = 0

    for original_event in events:
        event = normalize_event(original_event)

        lead_id = resolve_lead_id(event)
        status = save_event(event, lead_id)

        if status == "inserted":
            inserted += 1
        else:
            duplicates += 1

        if lead_id is None:
            quarantine_orphan(event)
            orphan_count += 1
        else:
            remove_orphan(event["event_id"])

    return {
        "events_inserted": inserted,
        "duplicate_events": duplicates,
        "malformed_events": malformed_events,
        "orphan_events": orphan_count,
    }
