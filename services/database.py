"""
Database service module for Sequential Health-State Recognition.

Handles SQLite connection management, schema initialization, and
parameterized queries. Uses Python's built-in sqlite3 module.
"""

import sqlite3
import os
import json
from datetime import datetime, timezone


# Default database path (relative to project root)
DEFAULT_DB_PATH = os.path.join("instance", "health_states.db")


def get_db_path(app=None):
    """Get the database path from Flask app config or use default."""
    if app and app.config.get("DATABASE_PATH"):
        return app.config["DATABASE_PATH"]
    return DEFAULT_DB_PATH


def get_connection(db_path=None):
    """
    Create a new SQLite connection with foreign keys enabled.
    
    Each call returns a fresh connection. The caller is responsible
    for closing it (use 'with' statements or try/finally).
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    # Ensure the directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Access columns by name
    conn.execute("PRAGMA foreign_keys = ON")  # Enforce foreign keys
    return conn


def init_db(db_path=None):
    """
    Create all tables if they do not already exist.
    
    Tables:
        cases         – One row per imported VitalDB surgical case.
        observations  – Chronological signal measurements per case.
        analysis_results – Stored analysis summaries for reproducibility.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()

        # ── cases table ──────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                source_case_id  INTEGER NOT NULL,
                source_name     TEXT    NOT NULL DEFAULT 'VitalDB',
                imported_at     TEXT    NOT NULL,
                metadata_json   TEXT,
                UNIQUE(source_case_id, source_name)
            )
        """)

        # ── observations table ───────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id             INTEGER NOT NULL,
                observed_at_seconds REAL    NOT NULL,
                signal_name         TEXT    NOT NULL,
                value               REAL    NOT NULL,
                unit                TEXT    NOT NULL,
                source_track_name   TEXT,
                FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
                UNIQUE(case_id, observed_at_seconds, signal_name)
            )
        """)

        # Indexes for common query patterns
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_obs_case_id
            ON observations(case_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_obs_case_time
            ON observations(case_id, observed_at_seconds)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_obs_case_signal
            ON observations(case_id, signal_name)
        """)

        # ── analysis_results table ───────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analysis_results (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id           INTEGER NOT NULL,
                algorithm_version TEXT    NOT NULL,
                analyzed_at       TEXT    NOT NULL,
                summary_json      TEXT    NOT NULL,
                FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
            )
        """)

        conn.commit()
        print("[DB] Tables created successfully.")
    finally:
        conn.close()


def get_cases(db_path=None):
    """Return all imported cases as a list of dicts."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, source_case_id, source_name, imported_at, metadata_json "
            "FROM cases ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_case(case_id, db_path=None):
    """Return a single case by internal id, or None."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id, source_case_id, source_name, imported_at, metadata_json "
            "FROM cases WHERE id = ?",
            (case_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_observations(case_id, signal_name=None, limit=500, offset=0, db_path=None):
    """
    Return observations for a case, optionally filtered by signal.
    Results are ordered chronologically.
    """
    conn = get_connection(db_path)
    try:
        query = (
            "SELECT id, case_id, observed_at_seconds, signal_name, value, unit, source_track_name "
            "FROM observations WHERE case_id = ?"
        )
        params = [case_id]

        if signal_name:
            query += " AND signal_name = ?"
            params.append(signal_name)

        query += " ORDER BY observed_at_seconds ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_observation_count(case_id, db_path=None):
    """Return total observation count for a case."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM observations WHERE case_id = ?",
            (case_id,)
        ).fetchone()
        return row["cnt"]
    finally:
        conn.close()


def get_signals_for_case(case_id, db_path=None):
    """Return distinct signal names and their units for a case."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT signal_name, unit, source_track_name "
            "FROM observations WHERE case_id = ? ORDER BY signal_name",
            (case_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_all_observations_for_case(case_id, db_path=None):
    """Return ALL observations for a case (for analysis). Ordered by time."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT observed_at_seconds, signal_name, value, unit "
            "FROM observations WHERE case_id = ? "
            "ORDER BY observed_at_seconds ASC",
            (case_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def save_analysis_result(case_id, algorithm_version, summary_json, db_path=None):
    """Save an analysis result summary."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO analysis_results (case_id, algorithm_version, analyzed_at, summary_json) "
            "VALUES (?, ?, ?, ?)",
            (case_id, algorithm_version, datetime.now(timezone.utc).isoformat(), json.dumps(summary_json))
        )
        conn.commit()
    finally:
        conn.close()


def case_exists(source_case_id, source_name="VitalDB", db_path=None):
    """Check if a case has already been imported (idempotency check)."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM cases WHERE source_case_id = ? AND source_name = ?",
            (source_case_id, source_name)
        ).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()
