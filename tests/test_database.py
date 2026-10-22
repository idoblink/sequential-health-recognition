"""
Tests for the database service.

Tests cover:
  - Database initialisation
  - Table creation
  - Foreign key enforcement
  - Import idempotency
  - Observation queries
"""

import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.database import (
    init_db,
    get_connection,
    get_cases,
    get_case,
    get_observations,
    get_observation_count,
    get_signals_for_case,
    case_exists,
)


@pytest.fixture
def test_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    os.unlink(path)


@pytest.fixture
def populated_db(test_db):
    """Create a database with sample data."""
    conn = get_connection(test_db)
    try:
        cursor = conn.cursor()
        # Insert a case
        cursor.execute(
            "INSERT INTO cases (source_case_id, source_name, imported_at, metadata_json) "
            "VALUES (?, ?, ?, ?)",
            (100, "VitalDB", "2024-01-01T00:00:00Z", '{"test": true}')
        )
        case_id = cursor.lastrowid

        # Insert observations
        observations = [
            (case_id, 0.0, "heart_rate", 75.0, "bpm", "Solar8000/HR"),
            (case_id, 1.0, "heart_rate", 76.0, "bpm", "Solar8000/HR"),
            (case_id, 2.0, "heart_rate", 74.0, "bpm", "Solar8000/HR"),
            (case_id, 0.0, "spo2", 98.0, "%", "Solar8000/SPO2"),
            (case_id, 1.0, "spo2", 97.0, "%", "Solar8000/SPO2"),
        ]
        cursor.executemany(
            "INSERT INTO observations (case_id, observed_at_seconds, signal_name, value, unit, source_track_name) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            observations
        )
        conn.commit()
    finally:
        conn.close()
    return test_db


class TestDatabaseInit:
    """Test database initialisation."""

    def test_tables_created(self, test_db):
        conn = get_connection(test_db)
        try:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            table_names = [t["name"] for t in tables]
            assert "cases" in table_names
            assert "observations" in table_names
            assert "analysis_results" in table_names
        finally:
            conn.close()

    def test_foreign_keys_enabled(self, test_db):
        conn = get_connection(test_db)
        try:
            result = conn.execute("PRAGMA foreign_keys").fetchone()
            assert result[0] == 1
        finally:
            conn.close()

    def test_reinit_is_safe(self, test_db):
        """Re-running init_db should not destroy existing data."""
        conn = get_connection(test_db)
        try:
            conn.execute(
                "INSERT INTO cases (source_case_id, source_name, imported_at) "
                "VALUES (?, ?, ?)",
                (1, "VitalDB", "2024-01-01T00:00:00Z")
            )
            conn.commit()
        finally:
            conn.close()

        # Re-init
        init_db(test_db)

        cases = get_cases(test_db)
        assert len(cases) == 1


class TestForeignKeys:
    """Test foreign key enforcement."""

    def test_observation_requires_valid_case(self, test_db):
        """Inserting an observation with invalid case_id should fail."""
        conn = get_connection(test_db)
        try:
            with pytest.raises(Exception):
                conn.execute(
                    "INSERT INTO observations (case_id, observed_at_seconds, signal_name, value, unit) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (9999, 0.0, "heart_rate", 75.0, "bpm")
                )
                conn.commit()
        finally:
            conn.close()


class TestImportIdempotency:
    """Test that duplicate imports are prevented."""

    def test_unique_case_constraint(self, test_db):
        """Inserting the same source_case_id twice should fail."""
        conn = get_connection(test_db)
        try:
            conn.execute(
                "INSERT INTO cases (source_case_id, source_name, imported_at) "
                "VALUES (?, ?, ?)",
                (42, "VitalDB", "2024-01-01T00:00:00Z")
            )
            conn.commit()

            with pytest.raises(Exception):
                conn.execute(
                    "INSERT INTO cases (source_case_id, source_name, imported_at) "
                    "VALUES (?, ?, ?)",
                    (42, "VitalDB", "2024-01-02T00:00:00Z")
                )
                conn.commit()
        finally:
            conn.close()

    def test_case_exists_check(self, populated_db):
        """case_exists should return the id for an existing case."""
        result = case_exists(100, "VitalDB", populated_db)
        assert result is not None

    def test_case_not_exists(self, test_db):
        """case_exists should return None for non-existent case."""
        result = case_exists(999, "VitalDB", test_db)
        assert result is None


class TestObservationQueries:
    """Test observation retrieval."""

    def test_get_observations(self, populated_db):
        cases = get_cases(populated_db)
        case_id = cases[0]["id"]
        obs = get_observations(case_id, db_path=populated_db)
        assert len(obs) == 5

    def test_get_observations_filtered(self, populated_db):
        cases = get_cases(populated_db)
        case_id = cases[0]["id"]
        obs = get_observations(case_id, signal_name="heart_rate", db_path=populated_db)
        assert len(obs) == 3
        assert all(o["signal_name"] == "heart_rate" for o in obs)

    def test_observation_count(self, populated_db):
        cases = get_cases(populated_db)
        case_id = cases[0]["id"]
        count = get_observation_count(case_id, db_path=populated_db)
        assert count == 5

    def test_chronological_order(self, populated_db):
        cases = get_cases(populated_db)
        case_id = cases[0]["id"]
        obs = get_observations(case_id, signal_name="heart_rate", db_path=populated_db)
        times = [o["observed_at_seconds"] for o in obs]
        assert times == sorted(times)

    def test_signals_for_case(self, populated_db):
        cases = get_cases(populated_db)
        case_id = cases[0]["id"]
        signals = get_signals_for_case(case_id, db_path=populated_db)
        signal_names = [s["signal_name"] for s in signals]
        assert "heart_rate" in signal_names
        assert "spo2" in signal_names

    def test_empty_case_returns_empty(self, test_db):
        cases = get_cases(test_db)
        assert len(cases) == 0

    def test_unknown_case_returns_none(self, test_db):
        case = get_case(999, test_db)
        assert case is None
