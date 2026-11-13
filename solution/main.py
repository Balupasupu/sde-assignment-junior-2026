
import argparse
import json
from pathlib import Path

from database import initialize_database, get_connection
from lead_ingestion import process_lead_csv, save_valid_leads
from event_ingestion import ingest_event_file, resolve_lead_id
from reporting import generate_reports
from security import decrypt_text


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_relative_path(file_path):
    return str(Path(file_path).resolve().relative_to(PROJECT_ROOT))


def is_file_processed(file_path):
    relative_path = get_relative_path(file_path)

    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT 1 FROM processed_files WHERE file_path = ?",
            (relative_path,)
        ).fetchone()
        return row is not None
    finally:
        connection.close()


def mark_file_processed(file_path, file_type):
    relative_path = get_relative_path(file_path)

    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT OR IGNORE INTO processed_files
            (file_path, file_type)
            VALUES (?, ?)
            """,
            (relative_path, file_type)
        )
        connection.commit()
    finally:
        connection.close()



def repair_unlinked_events():
    # Step 1: Read unlinked events and close the connection.
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT event_id, encrypted_event
            FROM events
            WHERE lead_id IS NULL
            """
        ).fetchall()
    finally:
        connection.close()

    # Step 2: Resolve lead IDs without holding a database connection.
    repairs = []

    for row in rows:
        event = json.loads(
            decrypt_text(row["encrypted_event"])
        )

        lead_id = resolve_lead_id(event)

        if lead_id is not None:
            repairs.append((lead_id, row["event_id"]))

    # Step 3: Save all repairs using one connection.
    connection = get_connection()
    try:
        for lead_id, event_id in repairs:
            connection.execute(
                """
                UPDATE events
                SET lead_id = ?
                WHERE event_id = ? AND lead_id IS NULL
                """,
                (lead_id, event_id)
            )

            connection.execute(
                """
                DELETE FROM orphan_events
                WHERE event_id = ?
                """,
                (event_id,)
            )

        connection.commit()
        print("Previously unlinked events repaired:", len(repairs))

    finally:
        connection.close()


def ingest_folder(folder):
    folder = Path(folder).resolve()

    if not folder.exists() or not folder.is_dir():
        raise ValueError(
            f"Input folder does not exist: {folder}"
        )

    csv_files = sorted(
        (folder / "leads").glob("*/*.csv")
    )

    event_files = sorted(
        (folder / "events").glob("*.jsonl")
    )

    if not csv_files and not event_files:
        raise ValueError(
            "No CSV or JSONL input files found in this folder."
        )

    print("\nProcessing lead files...")

    for file_path in csv_files:
        if is_file_processed(file_path):
            print(
                "SKIPPED (already processed):",
                file_path.name
            )
            continue

        workflow_id = file_path.parent.name

        result = process_lead_csv(
            file_path,
            workflow_id
        )

        inserted, merged = save_valid_leads(
            result["valid_rows"],
            workflow_id
        )

        mark_file_processed(file_path, "leads")

        print(
            file_path.name,
            "| workflow:", workflow_id,
            "| valid:", len(result["valid_rows"]),
            "| rejected:", len(result["rejected_rows"]),
            "| inserted:", inserted,
            "| merged:", merged
        )

    print("\nProcessing event files...")

    for file_path in event_files:
        if is_file_processed(file_path):
            print(
                "SKIPPED (already processed):",
                file_path.name
            )
            continue

        result = ingest_event_file(file_path)

        mark_file_processed(file_path, "events")

        print(
            file_path.name,
            "| inserted:",
            result.get("events_inserted", 0),
            "| duplicates:",
            result.get("duplicate_events", 0),
            "| malformed:",
            result.get("malformed_events", 0),
            "| orphans:",
            result.get("orphan_events", 0)
        )

    repair_unlinked_events()

    print("\nIngestion completed.")


def main():
    parser = argparse.ArgumentParser(
        description="Interaction Ledger and Reporting Pipeline"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True
    )

    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Ingest one data drop folder"
    )

    ingest_parser.add_argument(
        "folder",
        help="Path to data/drop_1 or data/drop_2"
    )

    report_parser = subparsers.add_parser(
        "report",
        help="Generate all five reports"
    )

    report_parser.add_argument(
        "--out",
        default="reports",
        help="Output directory for reports"
    )

    args = parser.parse_args()

    initialize_database()

    if args.command == "ingest":
        ingest_folder(args.folder)

    elif args.command == "report":
        output_directory = Path(args.out)

        if not output_directory.is_absolute():
            output_directory = PROJECT_ROOT / output_directory

        generate_reports(output_directory)


if __name__ == "__main__":
    main()
