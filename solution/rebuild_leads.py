
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lead_ingestion import process_lead_csv, save_valid_leads

project_root = Path(__file__).resolve().parent.parent

total = 0
inserted = 0
merged = 0
rejected = 0
warnings = 0

folders = [
    project_root / "data" / "drop_1" / "leads",
    project_root / "data" / "drop_2" / "leads",
]

for folder in folders:
    files = sorted(folder.glob("*/*.csv"))

    for file in files:
        workflow = file.parent.name
        result = process_lead_csv(file, workflow)

        new_count, merge_count = save_valid_leads(
            result["valid_rows"], workflow
        )

        total += result["lead_rows_total"]
        inserted += new_count
        merged += merge_count
        rejected += len(result["rejected_rows"])
        warnings += result["field_warnings"]

        print(
            file.name,
            workflow,
            "valid:", len(result["valid_rows"]),
            "rejected:", len(result["rejected_rows"]),
            "inserted:", new_count,
            "merged:", merge_count,
        )

print("\nTOTAL:", total)
print("INSERTED:", inserted)
print("MERGED:", merged)
print("REJECTED:", rejected)
print("WARNINGS:", warnings)
