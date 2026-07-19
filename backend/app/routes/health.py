"""
Health-check endpoint.

Purpose: a tiny route that proves the server is alive and reachable, WITHOUT
touching the ML model, the database, or anything that can be slow or fail.
Frontends, uptime monitors, and Docker/orchestration health probes hit this.

A blueprint is Flask's way of grouping related routes into a module that the
application factory then registers. Think of it as a mini-app for one feature.
"""
from datetime import datetime, timezone

from flask import Blueprint, jsonify

# url_prefix="/api" means every route here is automatically under /api,
# so the function below (@health_bp.route("/health")) serves /api/health.
health_bp = Blueprint("health", __name__, url_prefix="/api")


@health_bp.route("/health", methods=["GET"])
def health():
    """Return 200 with a small JSON body. No model, no I/O — just 'I'm up'."""
    payload = {
        "status": "ok",
        "service": "aegisbot-backend",
        "time": datetime.now(timezone.utc).isoformat(),
    }
    return jsonify(payload), 200
