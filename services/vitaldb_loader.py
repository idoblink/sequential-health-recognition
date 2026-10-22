"""
VitalDB data loader module.

Uses the official `vitaldb` Python package to download a configurable
subset of surgical cases and extract vital-sign tracks.  Only real
data from VitalDB is stored — no synthetic or fabricated values.

Supported signals and their VitalDB track names:
    heart_rate   → Solar8000/HR
    spo2         → Solar8000/SPO2
    systolic_bp  → Solar8000/NIBP_SBP  (non-invasive systolic BP)
    diastolic_bp → Solar8000/NIBP_DBP  (non-invasive diastolic BP)
    temperature  → Solar8000/BT        (body temperature)
"""

import os
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from services.database import get_connection, case_exists

# ── Track configuration ──────────────────────────────────────────
# Maps normalised signal names → (VitalDB track name, unit)
TRACK_MAP = {
    "heart_rate":   ("Solar8000/HR",         "bpm"),
    "spo2":         ("Solar8000/PLETH_SPO2", "%"),
    "systolic_bp":  ("Solar8000/NIBP_SBP",   "mmHg"),
    "diastolic_bp": ("Solar8000/NIBP_DBP",   "mmHg"),
    "temperature":  ("Solar8000/BT",         "°C"),
}

# Default number of cases to import
DEFAULT_NUM_CASES = 5

# Sampling interval in seconds (1-second resolution keeps data manageable)
SAMPLE_INTERVAL = 1.0


def find_available_cases(num_cases=DEFAULT_NUM_CASES):
    """
    Find VitalDB case IDs that have at least heart_rate and spo2 tracks.
    Returns a list of integer case IDs (up to num_cases).
    """
    import vitaldb

    # Find cases that have both HR and SpO2 tracks available
    required_tracks = ["Solar8000/HR", "Solar8000/PLETH_SPO2"]
    case_ids = vitaldb.find_cases(required_tracks)

    if not case_ids:
        print("[VitalDB] No cases found with required tracks.")
        return []

    # Take the first N cases
    selected = case_ids[:num_cases]
    print(f"[VitalDB] Found {len(case_ids)} cases with required tracks; selected {len(selected)}.")
    return selected


def load_case_data(case_id):
    """
    Download track data for a single VitalDB case.
    
    Returns a dict of {signal_name: DataFrame with columns [time, value]}
    Only signals that actually contain data are included.
    """
    import vitaldb

    track_names = [t[0] for t in TRACK_MAP.values()]
    signal_names = list(TRACK_MAP.keys())

    print(f"[VitalDB] Downloading case {case_id} tracks: {track_names}")

    try:
        # load_case returns a numpy array: rows=time steps, cols=tracks
        # at the specified interval
        data = vitaldb.load_case(case_id, track_names, SAMPLE_INTERVAL)
    except Exception as e:
        print(f"[VitalDB] Error downloading case {case_id}: {e}")
        return {}

    if data is None or len(data) == 0:
        print(f"[VitalDB] No data returned for case {case_id}.")
        return {}

    result = {}
    num_time_steps = data.shape[0]
    time_col = np.arange(num_time_steps) * SAMPLE_INTERVAL  # elapsed seconds

    for col_idx, signal_name in enumerate(signal_names):
        values = data[:, col_idx]
        # Find valid (non-NaN) values
        valid_mask = ~np.isnan(values)
        valid_count = int(np.sum(valid_mask))

        if valid_count == 0:
            print(f"  {signal_name}: no valid values, skipping.")
            continue

        df = pd.DataFrame({
            "time": time_col[valid_mask],
            "value": values[valid_mask]
        })
        result[signal_name] = df
        print(f"  {signal_name}: {valid_count} valid observations.")

    return result


def import_cases(num_cases=DEFAULT_NUM_CASES, db_path=None):
    """
    Import a subset of VitalDB cases into the local SQLite database.
    
    This function is idempotent: re-running it will not duplicate
    already-imported cases (checked via source_case_id + source_name).
    
    Args:
        num_cases: Number of cases to import.
        db_path:   Path to the SQLite database (uses default if None).
    
    Returns:
        A dict summarising what was imported.
    """
    case_ids = find_available_cases(num_cases)
    if not case_ids:
        return {"imported": 0, "skipped": 0, "errors": 0, "message": "No cases found."}

    imported = 0
    skipped = 0
    errors = 0

    for source_id in case_ids:
        # Idempotency: skip if already imported
        existing_id = case_exists(source_id, "VitalDB", db_path)
        if existing_id is not None:
            print(f"[Import] Case {source_id} already imported (id={existing_id}), skipping.")
            skipped += 1
            continue

        # Download data from VitalDB API
        signal_data = load_case_data(source_id)
        if not signal_data:
            print(f"[Import] Case {source_id}: no usable data, skipping.")
            errors += 1
            continue

        # Insert into database within a transaction
        conn = get_connection(db_path)
        try:
            cursor = conn.cursor()

            # Insert the case record
            now_utc = datetime.now(timezone.utc).isoformat()
            metadata = {
                "source": "VitalDB",
                "source_url": "https://vitaldb.net/",
                "sample_interval_s": SAMPLE_INTERVAL,
                "signals_available": list(signal_data.keys()),
                "import_version": "1.0.0"
            }

            cursor.execute(
                "INSERT INTO cases (source_case_id, source_name, imported_at, metadata_json) "
                "VALUES (?, ?, ?, ?)",
                (source_id, "VitalDB", now_utc, json.dumps(metadata))
            )
            internal_case_id = cursor.lastrowid

            # Insert observations for each signal
            total_obs = 0
            for signal_name, df in signal_data.items():
                track_name, unit = TRACK_MAP[signal_name]
                rows = [
                    (internal_case_id, float(row["time"]), signal_name,
                     float(row["value"]), unit, track_name)
                    for _, row in df.iterrows()
                ]
                cursor.executemany(
                    "INSERT OR IGNORE INTO observations "
                    "(case_id, observed_at_seconds, signal_name, value, unit, source_track_name) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    rows
                )
                total_obs += len(rows)

            conn.commit()
            imported += 1
            print(f"[Import] Case {source_id} -> id={internal_case_id}, {total_obs} observations inserted.")

        except Exception as e:
            conn.rollback()
            errors += 1
            print(f"[Import] Error importing case {source_id}: {e}")
        finally:
            conn.close()

    summary = {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "total_requested": num_cases,
        "message": f"Import complete: {imported} new, {skipped} existing, {errors} errors."
    }
    print(f"\n[Import] {summary['message']}")
    return summary
