import csv
import json
import re
from database import get_connection
from security import encrypt_text, decrypt_text, hash_phone

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = PROJECT_ROOT / "assignment-a-data" / "schemas"


def load_schema(workflow_id):
    schema_path = SCHEMA_DIR / f"{workflow_id}.json"

    with open(schema_path, "r", encoding="utf-8") as file:
        return json.load(file)


def normalize_header(header):
    header = header.strip().lower()
    return re.sub(r"[_\s]+", " ", header)


def build_header_map(csv_headers, schema):
    header_map = {}

    for field in schema["fields"]:
        accepted_names = [field["name"]] + field.get("aliases", [])

        normalized_names = {
            normalize_header(name)
            for name in accepted_names
        }

        for header in csv_headers:
            if normalize_header(header) in normalized_names:
                header_map[field["name"]] = header
                break

    return header_map


from normalization import (
    normalize_phone,
    normalize_date,
    normalize_decimal,
)


def normalize_field_value(field, raw_value):
    if raw_value is None or not str(raw_value).strip():
        return None, False

    value = str(raw_value).strip()
    field_type = field["type"]

    if field_type == "string":
        return value, False

    if field_type == "phone":
        result = normalize_phone(value)
        return result, result is None

    if field_type == "date":
        result = normalize_date(value)
        return result, result is None

    if field_type == "decimal":
        result = normalize_decimal(value)
        if result is None:
            return None, True
        return str(result), False

    if field_type == "enum":
        allowed_values = [
            item.lower() for item in field.get("values", [])
        ]

        if value.lower() in allowed_values:
            return value.lower(), False

        return None, True

    return value, False

def validate_lead_row(row, schema, header_map):
    normalized_data = {}
    warnings = 0

    for field in schema["fields"]:
        field_name = field["name"]
        csv_header = header_map.get(field_name)

        raw_value = row.get(csv_header) if csv_header else None

        # Required field missing
        if raw_value is None or not str(raw_value).strip():
            if field.get("required", False):
                return None, f"missing_required:{field_name}", 0

            normalized_data[field_name] = None
            continue

        value, invalid = normalize_field_value(field, raw_value)

        # Invalid required phone
        if invalid and field["type"] == "phone" and field.get("required"):
            return None, "invalid_phone", 0

        # Invalid optional field
        if invalid:
            normalized_data[field_name] = None
            warnings += 1
        else:
            normalized_data[field_name] = value

    # Apply defaults to fields still empty
    for field in schema["fields"]:
        field_name = field["name"]

        if normalized_data.get(field_name) is None:
            if "default" in field:
                normalized_data[field_name] = field["default"]

    return normalized_data, None, warnings

def process_lead_csv(csv_path, workflow_id):
    schema = load_schema(workflow_id)

    valid_rows = []
    rejected_rows = []
    field_warnings = 0
    row_number = 0

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        header_map = build_header_map(reader.fieldnames or [], schema)

        for row in reader:
            # Skip completely blank rows
            if not row or not any(
                value and str(value).strip()
                for value in row.values()
            ):
                continue

            row_number += 1

            data, reason, warnings = validate_lead_row(
                row, schema, header_map
            )

            if reason:
                rejected_rows.append({
                    "workflow_id": workflow_id,
                    "batch_id": Path(csv_path).stem,
                    "row_number": row_number,
                    "reason": reason,
                })
            else:
                data["workflow_id"] = workflow_id
                data["batch_id"] = Path(csv_path).stem

                valid_rows.append(data)
                field_warnings += warnings

    return {
        "valid_rows": valid_rows,
        "rejected_rows": rejected_rows,
        "field_warnings": field_warnings,
        "lead_rows_total": row_number,
    }

def save_valid_leads(valid_rows, workflow_id):
    schema = load_schema(workflow_id)

    reference_field = next(
        (field["name"] for field in schema["fields"]
         if field.get("reference")),
        None
    )

    connection = get_connection()
    inserted = 0
    merged = 0

    try:
        for lead in valid_rows:
            phone_hash = hash_phone(lead["phone"])

            lead_data = {
                field["name"]: lead.get(field["name"])
                for field in schema["fields"]
            }

            existing = connection.execute(
                """
                SELECT id, encrypted_data
                FROM leads
                WHERE workflow_id = ? AND phone_hash = ?
                """,
                (workflow_id, phone_hash)
            ).fetchone()

            if existing is None:
                connection.execute(
                    """
                    INSERT INTO leads
                    (workflow_id, phone_hash, encrypted_data,
                     batch_id, external_ref)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        workflow_id,
                        phone_hash,
                        encrypt_text(json.dumps(lead_data)),
                        lead["batch_id"],
                        lead_data.get(reference_field)
                    )
                )
                inserted += 1

            else:
                old_data = json.loads(
                    decrypt_text(existing["encrypted_data"])
                )

                for key, value in lead_data.items():
                    if value is not None:
                        old_data[key] = value

                connection.execute(
                    """
                    UPDATE leads
                    SET encrypted_data = ?, external_ref = ?
                    WHERE id = ?
                    """,
                    (
                        encrypt_text(json.dumps(old_data)),
                        old_data.get(reference_field),
                        existing["id"]
                    )
                )
                merged += 1

        connection.commit()

    finally:
        connection.close()

    return inserted, merged