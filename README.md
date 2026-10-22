# Sequential Health-State Recognition

An educational web application that analyses sequential patient-monitoring observations from the [VitalDB](https://vitaldb.net/) surgical dataset and identifies patterns corresponding to different health states using a transparent, rule-based algorithm.

> **⚠️ Disclaimer:** This application is for **educational and research demonstration only**. It does not provide medical diagnosis, clinical decision support, or validated health alerts.

## Features

- **Real clinical data** from the VitalDB open dataset (de-identified surgical monitoring)
- **SQLite database** for local storage of imported cases and observations
- **Interactive dashboard** with case selection and vital-sign charts (Chart.js)
- **Paginated observation table** with signal filtering
- **Rule-based sequential analysis** with configurable demonstration thresholds
- **Trend detection** for sustained increases/decreases in vital signs
- **Clean macOS-inspired UI** built with HTML5, CSS3, and vanilla JavaScript
- **REST API** with Flask backend

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.10+ with Flask |
| Database | SQLite (built-in `sqlite3`) |
| Frontend | HTML5, CSS3, vanilla JavaScript |
| Charts | Chart.js (CDN) |
| Data Access | Official `vitaldb` Python package |
| Testing | pytest |

## Dataset — VitalDB

### About

VitalDB is a high-fidelity, multi-parameter vital signs database containing de-identified perioperative (surgical) clinical records and physiological monitoring data from over 6,000 surgical patients.

**Important context:** This data comes from **surgical monitoring** (perioperative setting), not general long-term patient monitoring. The signals were recorded during surgical procedures.

### Signals Used

| Signal | VitalDB Track | Unit |
|--------|--------------|------|
| Heart Rate | `Solar8000/HR` | bpm |
| SpO₂ | `Solar8000/SPO2` | % |
| Systolic BP | `Solar8000/NIBP_SBP` | mmHg |
| Diastolic BP | `Solar8000/NIBP_DBP` | mmHg |
| Temperature | `Solar8000/BT` | °C |

Not all signals are available for every case. The application handles missing signals gracefully.

### Citation

> Lee HC, Park Y, Yoon SB, Yang SM, Park D, Jung CW. VitalDB, a high-fidelity multi-parameter vital signs database in surgical patients. *Scientific Data*. 2022;9(1):279. doi:[10.1038/s41597-022-01411-5](https://doi.org/10.1038/s41597-022-01411-5)

### License

The VitalDB dataset is available under the **Creative Commons Attribution 4.0 International (CC BY 4.0)** license.

PhysioNet repository: [https://physionet.org/content/vitaldb/1.0.0/](https://physionet.org/content/vitaldb/1.0.0/)

## Setup Instructions

### 1. Clone and create virtual environment

```powershell
# Windows PowerShell
cd sequential-health-recognition
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux / macOS
cd sequential-health-recognition
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Initialize the database

```bash
python scripts/init_db.py
```

This creates `instance/health_states.db` with the required tables.

### 4. Import VitalDB data

```bash
# Import 5 cases (default)
python scripts/import_vitaldb.py

# Or specify a different number
python scripts/import_vitaldb.py --num-cases 3
```

This downloads real surgical monitoring data from VitalDB via the official Python package. An internet connection is required on first run.

The import is **idempotent** — re-running it will skip already-imported cases.

### 5. Run the application

```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

### Stopping the server

Press `Ctrl+C` in the terminal.

### Resetting the database

Delete the database file and re-run the setup:

```bash
# Delete database
rm instance/health_states.db      # Linux/macOS
del instance\health_states.db     # Windows

# Re-initialise and re-import
python scripts/init_db.py
python scripts/import_vitaldb.py
```

## Database Schema

### `cases`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment internal ID |
| `source_case_id` | INTEGER | VitalDB case identifier |
| `source_name` | TEXT | Source dataset name ("VitalDB") |
| `imported_at` | TEXT | ISO 8601 import timestamp |
| `metadata_json` | TEXT | Optional JSON metadata |

**Unique constraint:** `(source_case_id, source_name)` prevents duplicate imports.

### `observations`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment internal ID |
| `case_id` | INTEGER FK | References `cases.id` |
| `observed_at_seconds` | REAL | Elapsed seconds from case start |
| `signal_name` | TEXT | Normalised signal name |
| `value` | REAL | Measured value |
| `unit` | TEXT | Measurement unit |
| `source_track_name` | TEXT | Original VitalDB track name |

**Unique constraint:** `(case_id, observed_at_seconds, signal_name)` prevents duplicate records.

### `analysis_results`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment internal ID |
| `case_id` | INTEGER FK | References `cases.id` |
| `algorithm_version` | TEXT | Version of the rule-based algorithm |
| `analyzed_at` | TEXT | ISO 8601 analysis timestamp |
| `summary_json` | TEXT | JSON analysis summary |

## Rule-Based Classification

### How it works

The analysis engine classifies each observation against **configurable demonstration thresholds**:

1. **Per-observation classification:** Each value is checked against Normal, Warning, and Critical ranges for its signal type.
2. **Sequential trend detection:** Consecutive observations (within a configurable time gap) are checked for sustained increases or decreases.
3. **Missing signal awareness:** The analysis reports which signals are unavailable and limits conclusions accordingly.

### Threshold configuration

Thresholds are defined in `services/health_analyzer.py`:

| Signal | Normal | Warning | Critical |
|--------|--------|---------|----------|
| Heart Rate | 60–100 bpm | 50–110 bpm | ≤40 or ≥130 bpm |
| SpO₂ | 95–100% | 90–94.9% | ≤89.9% |
| Systolic BP | 90–140 mmHg | 80–160 mmHg | ≤60 or ≥180 mmHg |
| Diastolic BP | 60–90 mmHg | 50–100 mmHg | ≤40 or ≥110 mmHg |
| Temperature | 36.0–37.5 °C | 35.0–38.5 °C | ≤34.0 or ≥39.5 °C |

### Sequential trends

- **Minimum consecutive observations:** 5
- **Maximum time gap:** 30 seconds (larger gaps reset the trend)
- Direction: increasing or decreasing

> These are **application-defined demonstration rules**, not clinically validated thresholds.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Application status |
| GET | `/api/cases` | List imported cases |
| GET | `/api/cases/<id>/observations` | Case observations (with `signal`, `limit`, `offset` params) |
| GET | `/api/cases/<id>/signals` | Available signals for a case |
| POST | `/api/cases/<id>/analyze` | Run rule-based analysis |

## Tests

Run tests with pytest:

```bash
pytest tests/ -v
```

Test coverage includes:
- Database initialisation and foreign-key behaviour
- Import idempotency
- API behaviour with empty and populated databases
- Unknown case ID handling
- Chronological ordering of observations
- Threshold boundary classification
- Sequential trend detection with time gaps
- Missing signal handling

## Project Structure

```
sequential-health-recognition/
├── app.py                          # Flask application
├── requirements.txt                # Python dependencies
├── README.md                       # This file
├── .gitignore
├── instance/                       # Local database (git-ignored)
│   └── health_states.db
├── data/
│   ├── README.md                   # Dataset instructions
│   └── raw/                        # Downloaded files (git-ignored)
├── scripts/
│   ├── init_db.py                  # Database initialisation
│   └── import_vitaldb.py           # VitalDB data importer
├── services/
│   ├── __init__.py
│   ├── database.py                 # SQLite connection & queries
│   ├── vitaldb_loader.py           # VitalDB data download & import
│   └── health_analyzer.py          # Rule-based analysis engine
├── tests/
│   ├── test_api.py                 # API endpoint tests
│   ├── test_database.py            # Database service tests
│   └── test_health_analyzer.py     # Analyzer tests
├── templates/
│   └── index.html                  # SPA template
└── static/
    ├── css/
    │   └── style.css               # macOS-inspired stylesheet
    └── js/
        └── app.js                  # Frontend application
```

## Limitations

- **Surgical monitoring context:** Data is from perioperative (surgical) settings, not general ward monitoring.
- **Demonstration thresholds:** Classification rules are application-defined for educational purposes, not clinically validated.
- **Missing data:** Not all signals are available for every case; analysis is limited to available signals.
- **Irregular sampling:** Observations may not be evenly spaced; trend detection accounts for time gaps.
- **No predictive model:** This is rule-based classification only, not machine learning or predictive analytics.
- **No clinical validation:** Results have not been validated against clinical outcomes or expert annotations.
- **Not for medical use:** This application must not be used for any form of clinical decision-making.
