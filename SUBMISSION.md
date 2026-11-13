# Submission

## Candidate

- **Name:** Pasupula Balu
- **Assignment chosen:** A – Interaction Ledger & Reporting Pipeline
- **Time spent: 6hr**

## How to run

Requirements: Python 3.13 and the dependencies in `requirements.txt`.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Configure the required `FERNET_KEY` and `PHONE_HASH_KEY` environment variables before running the pipeline. Keep these keys private.

Generate the sample data:

```powershell
python assignment-a-data/tools/generate_data.py --seed 42 --scale small --out data
```

Run ingestion in order:

```powershell
python solution/main.py ingest data/drop_1
python solution/main.py ingest data/drop_2
```

Generate reports:

```powershell
python solution/main.py report --out reports/
```

Run tests:

```powershell
python -m pytest -q
```

## Design

The solution uses Python and SQLite.

- `lead_ingestion.py` reads workflow-specific CSV files, normalizes fields, validates required values, and merges duplicate lead identities.
- `normalization.py` handles phone numbers, dates, and decimal values.
- `security.py` encrypts PII using Fernet and uses keyed phone hashes for matching.
- `event_ingestion.py` processes JSONL events, deduplicates event IDs, links events to leads, and quarantines orphan events.
- `dispositions.py` loads disposition definitions dynamically from the supplied CSV catalogue.
- `reporting.py` generates the five required reports.
- `main.py` provides the ingest and report CLI commands.

The database contains leads, events, orphan events, rejections, and processed-file tracking. Event records are retained in the ledger, and processed-file tracking helps prevent repeated ingestion.

## Decisions & assumptions

| Decision                                        | Why                                                                            | Alternative considered           |
| ----------------------------------------------- | ------------------------------------------------------------------------------ | -------------------------------- |
| SQLite                                          | Simple persistent relational database suitable for this assignment             | PostgreSQL                       |
| Fernet encryption for PII                       | Protects sensitive lead and event data at rest                                 | Plaintext storage                |
| Keyed phone hashing                             | Allows phone matching without storing raw phone numbers in the matching column | Plain phone lookup               |
| Workflow ID + normalized phone as lead identity | Identifies duplicate leads within a workflow                                   | External reference alone         |
| Process files in sorted order                   | Keeps ingestion order deterministic                                            | Unsorted file processing         |
| Naive event timestamps treated as IST           | Follows the assignment timestamp convention                                    | Treating naive timestamps as UTC |

## Failure modes considered

- Invalid phone numbers and dates are rejected or normalized according to field rules.
- Optional invalid values are handled as null with warnings.
- Duplicate lead identities are merged.
- Duplicate event IDs are ignored.
- Events that cannot be linked are quarantined and can be retried for linking later.
- Processed files are skipped during repeated ingestion.
- PII is encrypted, and phone hashes are used for matching.

Known limitations:

- Automated test coverage currently focuses on normalization functions.
- Additional automated tests for event linking, reporting, and failure recovery would improve confidence.
- SQLite is suitable for this assignment but is not intended as a high-concurrency production database.

## Testing

- Normalization tests: 12 passed.
- Python syntax compilation checked for the main implementation modules.
- Ingested drop 1 followed by drop 2.
- Re-ran both drops to verify already-processed files were skipped.
- Generated all five reports successfully.
- Verified data-quality totals in `data_quality.json`.

## Results

- Lead rows processed: 2,057
- Rejected lead rows: 108
- Duplicate lead rows merged: 57
- Final unique leads: 1,892
- Event lines processed: 8,745
- Malformed events: 8
- Duplicate events dropped: 237
- Final unique events: 8,500
- Remaining orphan events: 462
- Unknown disposition events: 19

Generated reports:

- `batch_summary.csv`
- `daily_overview.csv`
- `lead_report.csv`
- `rejections.csv`
- `data_quality.json`

## If I had another day

1. Add automated tests for event deduplication and lead linking.
2. Add tests for effective disposition and reporting bucket calculations.
3. Improve crash recovery and database transaction handling.
4. Add integration tests for incremental ingestion and report generation.
5. Improve logging and error diagnostics.
