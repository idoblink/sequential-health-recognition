"""
Tests for the Flask API endpoints.

Tests cover:
  - Health check endpoint
  - Cases endpoint (empty and populated)
  - Observations endpoint (with filters)
  - Signals endpoint
  - Analysis endpoint
  - Unknown case ID handling
  - HTTP status codes
"""

import sys
import os
import json
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.database import init_db, get_connection


@pytest.fixture
def app():
    """Create a Flask test app with a temporary database."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Patch the default DB path before importing app
    import services.database as db_module
    original_path = db_module.DEFAULT_DB_PATH
    db_module.DEFAULT_DB_PATH = db_path

    init_db(db_path)

    from app import app as flask_app
    flask_app.config["TESTING"] = True
    flask_app.config["DATABASE_PATH"] = db_path

    yield flask_app

    db_module.DEFAULT_DB_PATH = original_path
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def populated_client(app):
    """Client with pre-populated test data."""
    import services.database as db_module
    conn = get_connection(db_module.DEFAULT_DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO cases (source_case_id, source_name, imported_at, metadata_json) "
            "VALUES (?, ?, ?, ?)",
            (42, "VitalDB", "2024-01-01T00:00:00Z", '{}')
        )
        case_id = cursor.lastrowid
        observations = [
            (case_id, 0.0, "heart_rate", 75.0, "bpm", "Solar8000/HR"),
            (case_id, 1.0, "heart_rate", 80.0, "bpm", "Solar8000/HR"),
            (case_id, 2.0, "spo2", 98.0, "%", "Solar8000/SPO2"),
        ]
        cursor.executemany(
            "INSERT INTO observations (case_id, observed_at_seconds, signal_name, value, unit, source_track_name) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            observations
        )
        conn.commit()
    finally:
        conn.close()
    return app.test_client()


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["database_initialized"] is True

    def test_health_empty_db(self, client):
        response = client.get("/api/health")
        data = response.get_json()
        assert data["cases_available"] == 0
        assert "No VitalDB cases" in data["message"]


class TestCasesEndpoint:
    def test_empty_cases(self, client):
        response = client.get("/api/cases")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total"] == 0
        assert data["cases"] == []

    def test_populated_cases(self, populated_client):
        response = populated_client.get("/api/cases")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total"] == 1
        assert data["cases"][0]["source_case_id"] == 42


class TestObservationsEndpoint:
    def test_observations_unknown_case(self, client):
        response = client.get("/api/cases/999/observations")
        assert response.status_code == 404

    def test_observations_populated(self, populated_client):
        response = populated_client.get("/api/cases/1/observations")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total"] == 3
        assert len(data["observations"]) == 3

    def test_observations_signal_filter(self, populated_client):
        response = populated_client.get("/api/cases/1/observations?signal=heart_rate")
        assert response.status_code == 200
        data = response.get_json()
        assert all(o["signal_name"] == "heart_rate" for o in data["observations"])

    def test_observations_pagination(self, populated_client):
        response = populated_client.get("/api/cases/1/observations?limit=2&offset=0")
        data = response.get_json()
        assert data["returned"] == 2
        assert data["total"] == 3


class TestSignalsEndpoint:
    def test_signals_unknown_case(self, client):
        response = client.get("/api/cases/999/signals")
        assert response.status_code == 404

    def test_signals_populated(self, populated_client):
        response = populated_client.get("/api/cases/1/signals")
        assert response.status_code == 200
        data = response.get_json()
        signal_names = [s["signal_name"] for s in data["signals"]]
        assert "heart_rate" in signal_names
        assert "spo2" in signal_names


class TestAnalyzeEndpoint:
    def test_analyze_unknown_case(self, client):
        response = client.post("/api/cases/999/analyze")
        assert response.status_code == 404

    def test_analyze_populated(self, populated_client):
        response = populated_client.post("/api/cases/1/analyze")
        assert response.status_code == 200
        data = response.get_json()
        assert "algorithm_version" in data
        assert "status_counts" in data
        assert "overall_status" in data
        assert "disclaimer" in data
        assert data["total_analyzed"] == 3

    def test_analyze_empty_case(self, client):
        """Analyze a case with no observations."""
        import services.database as db_module
        conn = get_connection(db_module.DEFAULT_DB_PATH)
        try:
            conn.execute(
                "INSERT INTO cases (source_case_id, source_name, imported_at) VALUES (?, ?, ?)",
                (1, "VitalDB", "2024-01-01T00:00:00Z")
            )
            conn.commit()
        finally:
            conn.close()

        response = client.post("/api/cases/1/analyze")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total_analyzed"] == 0
        assert "Insufficient" in data["overall_status"]
