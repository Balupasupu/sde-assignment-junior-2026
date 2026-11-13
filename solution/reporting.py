
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from database import get_connection
from security import decrypt_text
from dispositions import load_dispositions
from lead_ingestion import process_lead_csv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
IST = ZoneInfo("Asia/Kolkata")


def parse_timestamp(value):
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=IST)

    return timestamp.astimezone(IST)


def write_csv(path, columns, rows):
    with open(path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def collect_database_data():
    connection = get_connection()

    try:
        leads = connection.execute(
            "SELECT * FROM leads ORDER BY workflow_id, external_ref"
        ).fetchall()

        events = connection.execute(
            "SELECT * FROM events"
        ).fetchall()

        orphan_count = connection.execute(
            "SELECT COUNT(*) FROM orphan_events"
        ).fetchone()[0]

        lead_data = []

        for row in leads:
            data = json.loads(decrypt_text(row["encrypted_data"]))

            lead_data.append({
                "id": row["id"],
                "workflow_id": row["workflow_id"],
                "batch_id": row["batch_id"],
                "external_ref": row["external_ref"],
                "phone": data.get("phone"),
                "data": data,
            })

        event_data = []

        for row in events:
            event = json.loads(decrypt_text(row["encrypted_event"]))
            event["lead_id"] = row["lead_id"]
            event_data.append(event)

        return lead_data, event_data, orphan_count

    finally:
        connection.close()


def calculate_calls(event_data, dispositions):
    grouped = defaultdict(list)

    for event in event_data:
        if event.get("lead_id") is None:
            continue

        key = (
            event["workflow_id"],
            event["call_id"],
        )

        grouped[key].append(event)

    calls = []

    for (workflow_id, call_id), events in grouped.items():
        initiated = [
            event for event in events
            if event["event_type"] == "call.initiated"
        ]

        if not initiated:
            continue

        initiated.sort(
            key=lambda event: parse_timestamp(event["occurred_at"])
        )

        start_event = initiated[0]
        lead_id = start_event["lead_id"]

        connected = any(
            event["event_type"] == "call.connected"
            for event in events
        )

        telephony_failed = any(
            event["event_type"] == "call.telephony_failed"
            for event in events
        )

        overrides = []
        normal_dispositions = []

        for event in events:
            event_type = event["event_type"]

            if event_type not in (
                "disposition.set",
                "disposition.override",
            ):
                continue

            code = (
                event.get("payload") or {}
            ).get("disposition_code")

            disposition = dispositions.get(
                (workflow_id, str(code).strip().lower())
            ) if code else None

            if disposition is None:
                continue

            item = {
                "code": code.strip().lower(),
                "details": disposition,
                "time": parse_timestamp(event["occurred_at"]),
            }

            if event_type == "disposition.override":
                overrides.append(item)
            else:
                normal_dispositions.append(item)

        effective = None

        if overrides:
            effective = max(overrides, key=lambda item: item["time"])
        elif normal_dispositions:
            effective = max(
                normal_dispositions,
                key=lambda item: item["time"],
            )

        calls.append({
            "workflow_id": workflow_id,
            "call_id": call_id,
            "lead_id": lead_id,
            "started_at": parse_timestamp(start_event["occurred_at"]),
            "connected": connected,
            "telephony_failed": telephony_failed,
            "disposition": effective,
        })

    return calls


def generate_batch_summary(leads, calls):
    calls_by_lead = defaultdict(list)

    for call in calls:
        calls_by_lead[call["lead_id"]].append(call)

    grouped = defaultdict(lambda: defaultdict(int))

    for lead in leads:
        lead_calls = calls_by_lead[lead["id"]]

        if not lead_calls:
            bucket = "yet_to_reach_out"

        elif any(
            call["disposition"]
            and call["disposition"]["details"]["is_terminal"]
            for call in lead_calls
        ):
            bucket = "completed"

        elif all(call["telephony_failed"] for call in lead_calls):
            bucket = "in_progress_telephony_failed"

        else:
            bucket = "in_progress_dialed"

        grouped[(lead["workflow_id"], lead["batch_id"])][bucket] += 1

    columns = [
        "workflow_id",
        "batch_id",
        "total_leads",
        "yet_to_reach_out",
        "in_progress_telephony_failed",
        "in_progress_dialed",
        "completed",
    ]

    rows = []

    for (workflow, batch), counts in sorted(grouped.items()):
        rows.append({
            "workflow_id": workflow,
            "batch_id": batch,
            "total_leads": sum(counts.values()),
            "yet_to_reach_out": counts["yet_to_reach_out"],
            "in_progress_telephony_failed": counts[
                "in_progress_telephony_failed"
            ],
            "in_progress_dialed": counts["in_progress_dialed"],
            "completed": counts["completed"],
        })

    return columns, rows


def generate_daily_overview(calls):
    grouped = defaultdict(list)

    for call in calls:
        date = call["started_at"].date().isoformat()
        grouped[(call["workflow_id"], date)].append(call)

    columns = [
        "workflow_id",
        "date",
        "total_calls",
        "connected_calls",
        "connectivity_rate",
        "success_leads",
    ]

    rows = []

    for (workflow, date), daily_calls in sorted(grouped.items()):
        total = len(daily_calls)
        connected = sum(call["connected"] for call in daily_calls)

        successful_leads = {
            call["lead_id"]
            for call in daily_calls
            if call["disposition"]
            and call["disposition"]["details"]["is_success"]
        }

        rows.append({
            "workflow_id": workflow,
            "date": date,
            "total_calls": total,
            "connected_calls": connected,
            "connectivity_rate": f"{connected / total:.4f}",
            "success_leads": len(successful_leads),
        })

    return columns, rows


def generate_lead_report(leads, calls):
    calls_by_lead = defaultdict(list)

    for call in calls:
        calls_by_lead[call["lead_id"]].append(call)

    columns = [
        "workflow_id",
        "external_ref",
        "batch_id",
        "phone_masked",
        "bucket",
        "total_calls",
        "connected_calls",
        "last_call_at",
        "current_disposition",
        "ever_success",
    ]

    rows = []

    for lead in leads:
        lead_calls = sorted(
            calls_by_lead[lead["id"]],
            key=lambda call: call["started_at"],
        )

        if not lead_calls:
            bucket = "yet_to_reach_out"
        elif any(
            call["disposition"]
            and call["disposition"]["details"]["is_terminal"]
            for call in lead_calls
        ):
            bucket = "completed"
        elif all(call["telephony_failed"] for call in lead_calls):
            bucket = "in_progress_telephony_failed"
        else:
            bucket = "in_progress_dialed"

        latest_with_disposition = next(
            (
                call for call in reversed(lead_calls)
                if call["disposition"]
            ),
            None,
        )

        current_disposition = (
            latest_with_disposition["disposition"]["code"]
            if latest_with_disposition else ""
        )

        ever_success = any(
            call["disposition"]
            and call["disposition"]["details"]["is_success"]
            for call in lead_calls
        )

        phone = lead["phone"] or ""
        digits = "".join(ch for ch in phone if ch.isdigit())
        masked = "+91******" + digits[-4:] if len(digits) >= 4 else ""

        last_call = lead_calls[-1] if lead_calls else None

        rows.append({
            "workflow_id": lead["workflow_id"],
            "external_ref": lead["external_ref"] or "",
            "batch_id": lead["batch_id"],
            "phone_masked": masked,
            "bucket": bucket,
            "total_calls": len(lead_calls),
            "connected_calls": sum(
                call["connected"] for call in lead_calls
            ),
            "last_call_at": (
                last_call["started_at"].isoformat()
                if last_call else ""
            ),
            "current_disposition": current_disposition,
            "ever_success": str(ever_success).lower(),
        })

    rows.sort(key=lambda row: (
        row["workflow_id"],
        row["external_ref"],
    ))

    return columns, rows


def generate_rejections_and_lead_quality():
    folders = [
        PROJECT_ROOT / "data" / "drop_1" / "leads",
        PROJECT_ROOT / "data" / "drop_2" / "leads",
    ]

    rejection_rows = []
    total = 0
    warnings = 0
    duplicates = 0
    seen = set()
    reasons = defaultdict(int)

    for folder in folders:
        for file in sorted(folder.glob("*/*.csv")):
            workflow = file.parent.name
            result = process_lead_csv(file, workflow)

            total += result["lead_rows_total"]
            warnings += result["field_warnings"]

            for row in result["rejected_rows"]:
                rejection_rows.append(row)
                reasons[row["reason"]] += 1

            for lead in result["valid_rows"]:
                identity = (workflow, lead["phone"])

                if identity in seen:
                    duplicates += 1
                else:
                    seen.add(identity)

    rejection_rows.sort(
        key=lambda row: (
            row["workflow_id"],
            row["batch_id"],
            row["row_number"],
        )
    )

    columns = [
        "workflow_id",
        "batch_id",
        "row_number",
        "reason",
    ]

    return (
        columns,
        rejection_rows,
        {
            "lead_rows_total": total,
            "lead_rows_rejected": len(rejection_rows),
            "rejections_by_reason": dict(sorted(reasons.items())),
            "duplicate_lead_rows_merged": duplicates,
            "field_warnings": warnings,
        },
    )


def generate_event_quality(event_data, orphan_count):
    folders = [
        PROJECT_ROOT / "data" / "drop_1" / "events",
        PROJECT_ROOT / "data" / "drop_2" / "events",
    ]

    total = 0
    malformed = 0
    duplicates = 0
    seen = set()

    dispositions = load_dispositions()
    unknown = 0

    for folder in folders:
        for file in sorted(folder.glob("*.jsonl")):
            with open(file, "r", encoding="utf-8") as source:
                for line in source:
                    if not line.strip():
                        continue

                    total += 1

                    try:
                        event = json.loads(line)

                        if not isinstance(event, dict) or not event.get("event_id"):
                            malformed += 1
                            continue

                    except json.JSONDecodeError:
                        malformed += 1
                        continue

                    event_id = event["event_id"]

                    if event_id in seen:
                        duplicates += 1
                        continue

                    seen.add(event_id)

                    if event.get("event_type") in (
                        "disposition.set",
                        "disposition.override",
                    ):
                        code = (
                            event.get("payload") or {}
                        ).get("disposition_code")

                        if not code or (
                            event.get("workflow_id"),
                            str(code).strip().lower(),
                        ) not in dispositions:
                            unknown += 1

    return {
        "events_total": total,
        "malformed_events": malformed,
        "duplicate_events_dropped": duplicates,
        "orphan_events": orphan_count,
        "unknown_disposition_events": unknown,
    }


def generate_reports(output_directory):
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    leads, events, orphan_count = collect_database_data()
    dispositions = load_dispositions()

    calls = calculate_calls(events, dispositions)

    columns, rows = generate_batch_summary(leads, calls)
    write_csv(output / "batch_summary.csv", columns, rows)

    columns, rows = generate_daily_overview(calls)
    write_csv(output / "daily_overview.csv", columns, rows)

    columns, rows = generate_lead_report(leads, calls)
    write_csv(output / "lead_report.csv", columns, rows)

    columns, rejected, lead_quality = (
        generate_rejections_and_lead_quality()
    )
    write_csv(output / "rejections.csv", columns, rejected)

    quality = lead_quality
    quality.update(generate_event_quality(events, orphan_count))

    with open(
        output / "data_quality.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(quality, file, indent=2)

    print("All five reports generated in:", output.resolve())
