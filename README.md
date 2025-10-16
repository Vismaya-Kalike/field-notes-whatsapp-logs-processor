# Field Notes WhatsApp Logs Processor

Tools for ingesting, cleaning, anonymizing, and analysing WhatsApp exports and coordinator field notes for Vismaya Kalike programmes.

- Parse raw WhatsApp exports for multiple geographies.
- Generate anonymised reports with AI-assisted analysis.
- Maintain coordinator field notes and child linking records in PostgreSQL.
- Flag data quality issues (missing aliases, unknown participants, etc.).

> **Sensitive data**  
> Keep raw WhatsApp media, coordinator notes, and database dumps out of git. Use the provided `.gitignore` and never commit `.env` files or personal identifiers.

---

## 1. Getting Started

### Prerequisites
- Python 3.11+
- PostgreSQL database with the Vika schema
- OpenAI API credentials for anonymisation and LLM analysis

### Installation
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Environment Variables
Copy the template and fill in real values (never commit the result):
```bash
cp env.example .env
```

Required keys:
| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string |
| `OPENAI_API_KEY` | Used by anonymiser and LLM analysis |

Optional settings can be tuned via the constants files in each module.

---

## 2. Repository Structure
| Path | Description |
| --- | --- |
| `whatsapp_database_processor.py` | Orchestrates WhatsApp ingestion workflow |
| `cleanup_reports.py`, `regenerate_reports.py` | Maintain generated reports |
| `anonymizer/` | Name detection and pseudonymisation helpers |
| `llm_analyzer/` | GPT-based qualitative analysis |
| `face_detection/` | Redact faces from submitted media |
| `database/` | Reusable DB services (children, notes, images, etc.) |
| `flag_*.py` | Data quality checks for missing or unknown notes |
| `coordinator_field_notes/` | Local JSON note exports (ignored by git) |
| `whatsapp_data_*` | Raw WhatsApp exports/media (ignored by git) |

Generated outputs and raw assets stay outside version control thanks to `.gitignore`.

---

## 3. Common Workflows

### 3.1 Import Coordinator Field Notes
```bash
python create_coordinator_field_notes.py \
  --input-dir coordinator_field_notes/venkatesh \
  --dry-run  # remove flag to write to DB
```
The script resolves coordinators, learning centres, and children, creating records where necessary.

### 3.2 Process WhatsApp Messages
```bash
python whatsapp_database_processor.py
```
Reads the configured data directories, stores conversations, and links media snapshots.

### 3.3 Regenerate Reports with Analysis
```bash
python regenerate_reports.py --help
python cleanup_reports.py
```
These scripts rebuild reports, anonymise participant names, and run LLM-based commentary where enabled.

### 3.4 Flag Data Issues
```bash
python flag_children_without_notes.py
python flag_notes_with_unknown_names.py
```
Outputs CSV/log summaries of records that need manual attention.

### 3.5 Explore Database Schema
```bash
python get_schema.py > schema_dump.txt
```
Keep the dump local; it includes host details and should remain ignored by git.

---

## 4. Development Tips
- Always activate the virtualenv before running scripts.
- Run scripts with `--dry-run` where available before writing to the DB.
- For new automation, use the services in `database/` rather than writing raw SQL.
- When handling media, use `face_detection/privacy_filter.py` to blur faces prior to sharing.

---

## 5. Contributing
1. Ensure sensitive data stays out of commits.
2. Run relevant scripts/tests for your changes.
3. Provide clear descriptions in pull requests, including data assumptions.

---

## 6. Support
For schema changes or production deployments, contact the data engineering team. For workflow questions, comment in the project’s GitHub issues.

