# Data Directory

This directory is used for downloaded VitalDB dataset files.

## Dataset: VitalDB

- **Source:** [VitalDB on PhysioNet](https://physionet.org/content/vitaldb/1.0.0/)
- **Website:** [vitaldb.net](https://vitaldb.net/)
- **License:** CC BY 4.0

## How data is obtained

This project uses the official `vitaldb` Python package to download case data
directly via the VitalDB API. **You do not need to manually download files.**

The import script (`scripts/import_vitaldb.py`) fetches data automatically
and stores it in the SQLite database at `instance/health_states.db`.

## `raw/` subdirectory

The `raw/` subdirectory is git-ignored and can be used to store any manually
downloaded VitalDB files if needed for advanced workflows.

## Important

- Do not commit downloaded dataset files to version control.
- Do not commit the SQLite database file.
- All data in this project comes from VitalDB and is used under CC BY 4.0.
