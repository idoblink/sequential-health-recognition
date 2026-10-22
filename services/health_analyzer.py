"""
Rule-based health-state recognition service.

Classifies individual observations and detects sequential trends
using configurable, transparent demonstration thresholds.

IMPORTANT: These are application-defined demonstration rules, NOT
clinically validated thresholds. Results are for educational purposes
only and must not be used for medical decision-making.

Algorithm version: 1.0.0
"""

import json
from collections import defaultdict

ALGORITHM_VERSION = "1.0.0"

# ── Configurable demonstration thresholds ─────────────────────────
# Each signal has optional Warning and Critical ranges.
# Format: {"low": value, "high": value} — either or both bounds.
THRESHOLDS = {
    "heart_rate": {
        "unit": "bpm",
        "normal": {"low": 60, "high": 100},
        "warning": {"low": 50, "high": 110},
        "critical": {"low": 40, "high": 130},
    },
    "spo2": {
        "unit": "%",
        "normal": {"low": 95, "high": 100},
        "warning": {"low": 90, "high": 100},
        "critical": {"low": 89.9, "high": None},
    },
    "systolic_bp": {
        "unit": "mmHg",
        "normal": {"low": 90, "high": 140},
        "warning": {"low": 80, "high": 160},
        "critical": {"low": 60, "high": 180},
    },
    "diastolic_bp": {
        "unit": "mmHg",
        "normal": {"low": 60, "high": 90},
        "warning": {"low": 50, "high": 100},
        "critical": {"low": 40, "high": 110},
    },
    "temperature": {
        "unit": "°C",
        "normal": {"low": 36.0, "high": 37.5},
        "warning": {"low": 35.0, "high": 38.5},
        "critical": {"low": 34.0, "high": 39.5},
    },
}

# ── Sequential trend configuration ───────────────────────────────
# Minimum consecutive observations to flag a trend
TREND_MIN_CONSECUTIVE = 5
# Maximum time gap (seconds) between observations to consider them
# part of a continuous sequence (avoids treating large gaps as trends)
TREND_MAX_GAP_SECONDS = 30.0


def classify_observation(signal_name, value):
    """
    Classify a single observation value for a known signal.
    
    Returns:
        dict with keys: status, reason
        status is one of: "Normal", "Warning", "Critical", "Unknown"
    """
    if signal_name not in THRESHOLDS:
        return {
            "status": "Unknown",
            "reason": f"No demonstration rules configured for '{signal_name}'."
        }

    config = THRESHOLDS[signal_name]
    normal = config["normal"]
    warning = config["warning"]
    critical = config["critical"]
    unit = config["unit"]

    # Check Critical first (most severe)
    if critical.get("low") is not None and value <= critical["low"]:
        return {
            "status": "Critical",
            "reason": (
                f"{signal_name} = {value} {unit} is at or below critical low "
                f"threshold ({critical['low']} {unit}). [Rule-based demonstration]"
            )
        }
    if critical.get("high") is not None and value >= critical["high"]:
        return {
            "status": "Critical",
            "reason": (
                f"{signal_name} = {value} {unit} is at or above critical high "
                f"threshold ({critical['high']} {unit}). [Rule-based demonstration]"
            )
        }

    # Check Warning
    if warning.get("low") is not None and value < warning["low"]:
        return {
            "status": "Warning",
            "reason": (
                f"{signal_name} = {value} {unit} is below warning low "
                f"threshold ({warning['low']} {unit}). [Rule-based demonstration]"
            )
        }
    if warning.get("high") is not None and value > warning["high"]:
        return {
            "status": "Warning",
            "reason": (
                f"{signal_name} = {value} {unit} is above warning high "
                f"threshold ({warning['high']} {unit}). [Rule-based demonstration]"
            )
        }

    # Within normal range (or between normal and warning — still not "critical")
    if (normal.get("low") is None or value >= normal["low"]) and \
       (normal.get("high") is None or value <= normal["high"]):
        return {
            "status": "Normal",
            "reason": f"{signal_name} = {value} {unit} is within normal range."
        }

    # Between normal and warning boundaries
    if normal.get("low") is not None and value < normal["low"]:
        return {
            "status": "Warning",
            "reason": (
                f"{signal_name} = {value} {unit} is below normal low "
                f"({normal['low']} {unit}) but above warning threshold. [Rule-based demonstration]"
            )
        }
    if normal.get("high") is not None and value > normal["high"]:
        return {
            "status": "Warning",
            "reason": (
                f"{signal_name} = {value} {unit} is above normal high "
                f"({normal['high']} {unit}) but below warning threshold. [Rule-based demonstration]"
            )
        }

    return {"status": "Normal", "reason": f"{signal_name} = {value} {unit} within range."}


def detect_trends(observations_by_signal):
    """
    Detect simple sequential trends in time-ordered observations.
    
    Looks for sustained increases or decreases in a signal over
    consecutive observations (respecting time-gap limits).
    
    Args:
        observations_by_signal: dict of signal_name → list of
            (time_seconds, value) tuples, sorted by time.
    
    Returns:
        List of trend dicts with keys:
            signal, direction, count, start_time, end_time, 
            start_value, end_value, description
    """
    trends = []

    for signal_name, points in observations_by_signal.items():
        if len(points) < TREND_MIN_CONSECUTIVE:
            continue

        # Walk through consecutive pairs tracking direction
        current_direction = None  # "increasing" or "decreasing"
        run_start_idx = 0
        run_length = 1

        for i in range(1, len(points)):
            prev_time, prev_val = points[i - 1]
            curr_time, curr_val = points[i]
            time_gap = curr_time - prev_time

            # If the gap is too large, reset the run
            if time_gap > TREND_MAX_GAP_SECONDS:
                # Check if the completed run is long enough
                if run_length >= TREND_MIN_CONSECUTIVE and current_direction:
                    trends.append(_make_trend(
                        signal_name, current_direction,
                        points, run_start_idx, i - 1
                    ))
                current_direction = None
                run_start_idx = i
                run_length = 1
                continue

            # Determine direction of this step
            if curr_val > prev_val:
                step_dir = "increasing"
            elif curr_val < prev_val:
                step_dir = "decreasing"
            else:
                step_dir = current_direction  # No change, continue run

            if step_dir == current_direction:
                run_length += 1
            else:
                # Direction changed — check if previous run was long enough
                if run_length >= TREND_MIN_CONSECUTIVE and current_direction:
                    trends.append(_make_trend(
                        signal_name, current_direction,
                        points, run_start_idx, i - 1
                    ))
                current_direction = step_dir
                run_start_idx = i - 1
                run_length = 2

        # Check final run
        if run_length >= TREND_MIN_CONSECUTIVE and current_direction:
            trends.append(_make_trend(
                signal_name, current_direction,
                points, run_start_idx, len(points) - 1
            ))

    return trends


def _make_trend(signal_name, direction, points, start_idx, end_idx):
    """Helper to create a trend dict."""
    start_time, start_val = points[start_idx]
    end_time, end_val = points[end_idx]
    count = end_idx - start_idx + 1

    return {
        "signal": signal_name,
        "direction": direction,
        "count": count,
        "start_time": start_time,
        "end_time": end_time,
        "start_value": round(start_val, 2),
        "end_value": round(end_val, 2),
        "description": (
            f"{signal_name} showed a sustained {direction} trend over "
            f"{count} consecutive observations ({start_time:.0f}s - {end_time:.0f}s): "
            f"{start_val:.2f} -> {end_val:.2f}. [Rule-based demonstration]"
        )
    }


def analyze_case(observations):
    """
    Run the full rule-based sequential analysis on a case's observations.
    
    Args:
        observations: list of dicts with keys:
            observed_at_seconds, signal_name, value, unit
            (as returned by database.get_all_observations_for_case)
    
    Returns:
        dict with analysis summary including per-observation classifications,
        trend information, counts, and limitations.
    """
    if not observations:
        return {
            "algorithm_version": ALGORITHM_VERSION,
            "total_analyzed": 0,
            "status_counts": {"Normal": 0, "Warning": 0, "Critical": 0, "Unknown": 0},
            "flagged_observations": [],
            "trends": [],
            "signals_analyzed": [],
            "limitations": ["No observations available for analysis."],
            "overall_status": "Insufficient data for classification",
            "disclaimer": (
                "This analysis uses application-defined demonstration rules and "
                "is for educational purposes only. It does not constitute medical "
                "advice, diagnosis, or a clinically validated alert."
            )
        }

    # Classify each observation
    status_counts = {"Normal": 0, "Warning": 0, "Critical": 0, "Unknown": 0}
    flagged = []
    observations_by_signal = defaultdict(list)
    signals_seen = set()

    for obs in observations:
        signal = obs["signal_name"]
        value = obs["value"]
        time_s = obs["observed_at_seconds"]
        signals_seen.add(signal)

        result = classify_observation(signal, value)
        status_counts[result["status"]] = status_counts.get(result["status"], 0) + 1

        if result["status"] in ("Warning", "Critical"):
            flagged.append({
                "time": time_s,
                "signal": signal,
                "value": value,
                "unit": obs["unit"],
                "status": result["status"],
                "reason": result["reason"]
            })

        # Collect for trend analysis
        observations_by_signal[signal].append((time_s, value))

    # Detect sequential trends
    trends = detect_trends(observations_by_signal)

    # Determine limitations
    limitations = []
    all_signals = set(THRESHOLDS.keys())
    missing = all_signals - signals_seen
    if missing:
        limitations.append(
            f"The following signals were not available: {', '.join(sorted(missing))}. "
            f"Analysis is limited to available signals."
        )

    # Overall status (most severe classification seen)
    if status_counts["Critical"] > 0:
        overall = "Critical observations detected"
    elif status_counts["Warning"] > 0:
        overall = "Warning observations detected"
    elif status_counts["Normal"] > 0:
        overall = "All analyzed observations within normal ranges"
    else:
        overall = "Insufficient data for classification"

    return {
        "algorithm_version": ALGORITHM_VERSION,
        "total_analyzed": len(observations),
        "status_counts": status_counts,
        "flagged_observations": flagged[:100],  # Limit to avoid huge responses
        "flagged_total": len(flagged),
        "trends": trends,
        "signals_analyzed": sorted(signals_seen),
        "limitations": limitations,
        "overall_status": overall,
        "disclaimer": (
            "This analysis uses application-defined demonstration rules and "
            "is for educational purposes only. It does not constitute medical "
            "advice, diagnosis, or a clinically validated alert."
        )
    }
