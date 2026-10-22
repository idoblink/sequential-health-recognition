"""
Sequential Health-State Recognition — Flask Application

A beginner-friendly educational web application that analyses
sequential patient-monitoring observations from the VitalDB
surgical dataset and identifies patterns using transparent,
rule-based demonstration thresholds.

Run with:
    python app.py
"""

import json
from flask import Flask, render_template, jsonify, request

from services.database import (
    init_db, get_cases, get_case, get_observations,
    get_observation_count, get_signals_for_case,
    get_all_observations_for_case, save_analysis_result
)
from services.health_analyzer import analyze_case, ALGORITHM_VERSION

app = Flask(__name__)

# ── Configuration ─────────────────────────────────────────────────
app.config["DATABASE_PATH"] = "instance/health_states.db"


# ── Initialise database on startup ────────────────────────────────
with app.app_context():
    init_db()


# ── Page route ────────────────────────────────────────────────────
@app.route("/")
def index():
    """Serve the single-page application."""
    return render_template("index.html")


# ── API: Health check ─────────────────────────────────────────────
@app.route("/api/health")
def api_health():
    """Return application status and whether data is available."""
    cases = get_cases()
    return jsonify({
        "status": "ok",
        "database_initialized": True,
        "cases_available": len(cases),
        "message": (
            "Application is running."
            if cases else
            "No VitalDB cases have been imported yet. "
            "Follow the dataset setup steps in README.md."
        )
    })


# ── API: List cases ──────────────────────────────────────────────
@app.route("/api/cases")
def api_cases():
    """Return all imported cases."""
    cases = get_cases()
    return jsonify({"cases": cases, "total": len(cases)})


# ── API: Case observations ───────────────────────────────────────
@app.route("/api/cases/<int:case_id>/observations")
def api_observations(case_id):
    """
    Return observations for a case.
    
    Query params:
        signal  — filter by signal name (optional)
        limit   — max rows (default 500)
        offset  — pagination offset (default 0)
    """
    case = get_case(case_id)
    if not case:
        return jsonify({"error": f"Case {case_id} not found."}), 404

    signal = request.args.get("signal")
    try:
        limit = int(request.args.get("limit", 500))
        offset = int(request.args.get("offset", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid limit or offset parameter."}), 400

    # Clamp limit
    limit = max(1, min(limit, 5000))
    offset = max(0, offset)

    observations = get_observations(case_id, signal_name=signal, limit=limit, offset=offset)
    total = get_observation_count(case_id)

    return jsonify({
        "case_id": case_id,
        "observations": observations,
        "returned": len(observations),
        "total": total,
        "limit": limit,
        "offset": offset
    })


# ── API: Case signals ────────────────────────────────────────────
@app.route("/api/cases/<int:case_id>/signals")
def api_signals(case_id):
    """List available signals and their units for a case."""
    case = get_case(case_id)
    if not case:
        return jsonify({"error": f"Case {case_id} not found."}), 404

    signals = get_signals_for_case(case_id)
    return jsonify({
        "case_id": case_id,
        "signals": signals
    })


# ── API: Analyse case ────────────────────────────────────────────
@app.route("/api/cases/<int:case_id>/analyze", methods=["POST"])
def api_analyze(case_id):
    """Run rule-based sequential analysis on a case."""
    case = get_case(case_id)
    if not case:
        return jsonify({"error": f"Case {case_id} not found."}), 404

    observations = get_all_observations_for_case(case_id)
    result = analyze_case(observations)

    # Save analysis summary for reproducibility
    try:
        save_analysis_result(case_id, ALGORITHM_VERSION, result)
    except Exception:
        pass  # Non-critical — analysis still returned to user

    return jsonify(result)


# ── Error handlers ────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Resource not found."}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error."}), 500


# ── Main ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n  Sequential Health-State Recognition")
    print("  ------------------------------------")
    print("  http://127.0.0.1:5000\n")
    app.run(debug=True, port=5000)
