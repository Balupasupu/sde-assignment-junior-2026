# \# AI Usage Disclosure

#

# \## Tools used

#

# \- ChatGPT (OpenAI)

#

# \## What I used them for

#

# \- Understanding the Assignment A requirements and breaking the work into smaller tasks.

# \- Getting explanations of Python, SQLite, data ingestion, encryption, and event processing.

# \- Getting coding guidance for CSV validation, phone/date/decimal normalization, event deduplication, lead linking, and report generation.

# \- Debugging Python errors, including SQLite database locking and import issues.

# \- Creating initial normalization test cases.

# \- Reviewing submission documentation.

#

# \## What I wrote or decided myself

#

# \- I worked through the assignment step by step and ran the commands in my local Windows environment.

# \- I reviewed the generated outputs and shared errors when something did not work.

# \- I made decisions about the implementation with guidance, including using SQLite and processing the two data drops in order.

# \- I ran the ingestion commands, checked repeated ingestion, generated the reports, and reviewed the data-quality totals.

# \- I am responsible for understanding, reviewing, and verifying the submitted implementation.

#

# \## Where the AI was wrong or unhelpful

#

# \- An earlier repair approach opened multiple SQLite connections while updating orphan events. This caused a `database is locked` error.

# \- I tested the updated approach that reads and resolves events before saving repairs through one connection. The retry completed successfully.

# \- A currency-normalization regex was initially copied with incorrect character encoding and formatting. I corrected it and verified that `₹27,554` returns `27554.00`.

# \- The initial pytest command had an import-path issue in my environment. Running `python -m pytest -q` successfully discovered and ran the tests.

#

# \## How I verified AI-generated code

#

# \- Compiled Python modules using `python -m py\\\_compile`.

# \- Ran the ingestion pipeline for drop 1 and drop 2.

# \- Re-ran both drops to check that processed files were skipped.

# \- Generated all five reports using the report command.

# \- Checked the values in `reports/data\\\_quality.json`.

# \- Ran `python -m pytest -q`; all 12 normalization tests passed.

# \- Manually reviewed command output and investigated errors rather than assuming generated code was correct.
