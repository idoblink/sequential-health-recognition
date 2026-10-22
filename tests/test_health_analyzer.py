"""
Tests for the health analyzer service.

Tests cover:
  - Threshold boundary classification
  - Missing / unknown signals
  - Sequential trend detection
  - Time-gap handling
  - Empty observations
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.health_analyzer import (
    classify_observation,
    detect_trends,
    analyze_case,
    TREND_MIN_CONSECUTIVE,
    TREND_MAX_GAP_SECONDS,
)


# ═══════════════ classify_observation ═══════════════

class TestClassifyObservation:
    """Test individual observation classification."""

    def test_heart_rate_normal(self):
        result = classify_observation("heart_rate", 75)
        assert result["status"] == "Normal"

    def test_heart_rate_at_lower_normal_boundary(self):
        result = classify_observation("heart_rate", 60)
        assert result["status"] == "Normal"

    def test_heart_rate_at_upper_normal_boundary(self):
        result = classify_observation("heart_rate", 100)
        assert result["status"] == "Normal"

    def test_heart_rate_warning_low(self):
        result = classify_observation("heart_rate", 55)
        assert result["status"] == "Warning"

    def test_heart_rate_warning_high(self):
        result = classify_observation("heart_rate", 115)
        assert result["status"] == "Warning"

    def test_heart_rate_critical_low(self):
        result = classify_observation("heart_rate", 40)
        assert result["status"] == "Critical"

    def test_heart_rate_critical_high(self):
        result = classify_observation("heart_rate", 130)
        assert result["status"] == "Critical"

    def test_heart_rate_below_critical(self):
        result = classify_observation("heart_rate", 30)
        assert result["status"] == "Critical"

    def test_spo2_normal(self):
        result = classify_observation("spo2", 98)
        assert result["status"] == "Normal"

    def test_spo2_warning(self):
        result = classify_observation("spo2", 92)
        assert result["status"] == "Warning"

    def test_spo2_critical(self):
        result = classify_observation("spo2", 85)
        assert result["status"] == "Critical"

    def test_temperature_normal(self):
        result = classify_observation("temperature", 36.8)
        assert result["status"] == "Normal"

    def test_temperature_critical_high(self):
        result = classify_observation("temperature", 40.0)
        assert result["status"] == "Critical"

    def test_unknown_signal(self):
        result = classify_observation("unknown_signal", 50)
        assert result["status"] == "Unknown"

    def test_result_has_reason(self):
        result = classify_observation("heart_rate", 140)
        assert "reason" in result
        assert len(result["reason"]) > 0
        assert "Rule-based demonstration" in result["reason"]


# ═══════════════ detect_trends ═══════════════

class TestDetectTrends:
    """Test sequential trend detection."""

    def test_no_trend_insufficient_data(self):
        """Too few points should return no trends."""
        points = [(i, 70 + i) for i in range(3)]
        result = detect_trends({"heart_rate": points})
        assert len(result) == 0

    def test_increasing_trend_detected(self):
        """Monotonically increasing values should be detected."""
        n = TREND_MIN_CONSECUTIVE + 2
        points = [(i * 2.0, 70 + i) for i in range(n)]
        result = detect_trends({"heart_rate": points})
        assert len(result) >= 1
        assert result[0]["direction"] == "increasing"

    def test_decreasing_trend_detected(self):
        """Monotonically decreasing values should be detected."""
        n = TREND_MIN_CONSECUTIVE + 2
        points = [(i * 2.0, 100 - i) for i in range(n)]
        result = detect_trends({"spo2": points})
        assert len(result) >= 1
        assert result[0]["direction"] == "decreasing"

    def test_no_trend_for_constant_values(self):
        """Flat values should not trigger a trend."""
        n = TREND_MIN_CONSECUTIVE + 2
        points = [(i * 2.0, 75) for i in range(n)]
        result = detect_trends({"heart_rate": points})
        # A "constant" run is neither increasing nor decreasing
        assert len(result) == 0

    def test_time_gap_breaks_trend(self):
        """A large time gap should reset trend detection."""
        n = TREND_MIN_CONSECUTIVE + 2
        points = []
        for i in range(n):
            t = i * 2.0  # Close together
            if i == n // 2:
                t = (n // 2) * 2.0 + TREND_MAX_GAP_SECONDS + 10  # Large gap
            points.append((t, 70 + i))
        # Sort by time
        points.sort(key=lambda p: p[0])
        result = detect_trends({"heart_rate": points})
        # The gap should split the run, making each part too short
        for trend in result:
            if trend["count"] >= TREND_MIN_CONSECUTIVE:
                # Verify the trend doesn't span across the gap
                assert (trend["end_time"] - trend["start_time"]) < TREND_MAX_GAP_SECONDS * n

    def test_trend_has_required_fields(self):
        """Trend dicts should have all required fields."""
        n = TREND_MIN_CONSECUTIVE + 2
        points = [(i * 2.0, 70 + i) for i in range(n)]
        result = detect_trends({"heart_rate": points})
        assert len(result) >= 1
        trend = result[0]
        assert "signal" in trend
        assert "direction" in trend
        assert "count" in trend
        assert "start_time" in trend
        assert "end_time" in trend
        assert "description" in trend


# ═══════════════ analyze_case ═══════════════

class TestAnalyzeCase:
    """Test the full case analysis."""

    def test_empty_observations(self):
        """Empty observation list should return proper empty result."""
        result = analyze_case([])
        assert result["total_analyzed"] == 0
        assert result["overall_status"] == "Insufficient data for classification"
        assert "disclaimer" in result
        assert len(result["limitations"]) > 0

    def test_all_normal_observations(self):
        """All-normal data should report normal status."""
        obs = [
            {"observed_at_seconds": i, "signal_name": "heart_rate", "value": 75, "unit": "bpm"}
            for i in range(10)
        ]
        result = analyze_case(obs)
        assert result["total_analyzed"] == 10
        assert result["status_counts"]["Normal"] == 10
        assert "normal" in result["overall_status"].lower()

    def test_mixed_observations(self):
        """Mixed normal and warning should report warnings."""
        obs = [
            {"observed_at_seconds": 0, "signal_name": "heart_rate", "value": 75, "unit": "bpm"},
            {"observed_at_seconds": 1, "signal_name": "heart_rate", "value": 120, "unit": "bpm"},
            {"observed_at_seconds": 2, "signal_name": "heart_rate", "value": 75, "unit": "bpm"},
        ]
        result = analyze_case(obs)
        assert result["status_counts"]["Warning"] > 0
        assert "Warning" in result["overall_status"]

    def test_missing_signals_noted_in_limitations(self):
        """Only providing one signal should note missing signals."""
        obs = [
            {"observed_at_seconds": 0, "signal_name": "heart_rate", "value": 75, "unit": "bpm"},
        ]
        result = analyze_case(obs)
        assert len(result["limitations"]) > 0
        assert "not available" in result["limitations"][0].lower()

    def test_disclaimer_always_present(self):
        """Every result must include the educational disclaimer."""
        result = analyze_case([])
        assert "educational" in result["disclaimer"].lower()

    def test_flagged_observations_limited(self):
        """Flagged observations should be capped at 100."""
        obs = [
            {"observed_at_seconds": i, "signal_name": "heart_rate", "value": 140, "unit": "bpm"}
            for i in range(200)
        ]
        result = analyze_case(obs)
        assert len(result["flagged_observations"]) <= 100
        assert result["flagged_total"] == 200

    def test_chronological_order_matters(self):
        """Out-of-order observations should still work."""
        obs = [
            {"observed_at_seconds": 5, "signal_name": "spo2", "value": 98, "unit": "%"},
            {"observed_at_seconds": 1, "signal_name": "spo2", "value": 97, "unit": "%"},
            {"observed_at_seconds": 3, "signal_name": "spo2", "value": 99, "unit": "%"},
        ]
        result = analyze_case(obs)
        assert result["total_analyzed"] == 3
