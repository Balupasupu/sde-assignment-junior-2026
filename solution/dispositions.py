
import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DISPOSITIONS_FILE = (
    PROJECT_ROOT / "assignment-a-data" / "schemas" / "dispositions.csv"
)


def load_dispositions():
    dispositions = {}

    with open(DISPOSITIONS_FILE, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            workflow_id = row["workflow_id"].strip()
            code = row["code"].strip().lower()

            dispositions[(workflow_id, code)] = {
                "label": row["label"].strip(),
                "is_terminal": row["is_terminal"].strip().lower() == "true",
                "is_success": row["is_success"].strip().lower() == "true",
            }

    return dispositions


def get_disposition(workflow_id, code):
    if not code:
        return None

    dispositions = load_dispositions()

    return dispositions.get((workflow_id, code.strip().lower()))
