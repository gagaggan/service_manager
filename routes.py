"""Small Flask Blueprint; FlaskFarm adapter can mount this blueprint."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from .service_manager import ServiceManager


def create_blueprint(manager: ServiceManager) -> Blueprint:
    bp = Blueprint("service_manager", __name__)

    @bp.get("/api/status")
    def status():
        return jsonify(manager.list_status())

    @bp.post("/api/restart")
    def restart():
        payload = request.get_json(silent=True) or {}
        result = manager.restart(str(payload.get("kind", "")), str(payload.get("name", "")))
        return jsonify(result), (200 if result["ok"] else 400)

    return bp

