from flask import Blueprint, request, jsonify

from services.auth_service import require_landlord
from services.settings_service import get_settings, update_settings, get_electricity_price


settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/api/settings", methods=["GET"])
@require_landlord
def api_get_settings():
    return jsonify({
        "success": True,
        "data": get_settings(),
    })


@settings_bp.route("/api/settings", methods=["PUT"])
@require_landlord
def api_update_settings():
    data = request.get_json(silent=True) or {}
    try:
        result = update_settings(data)
        return jsonify({
            "success": True,
            "message": "Settings updated. Electricity price synced to all rooms & active contracts.",
            "data": result,
        })
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400


@settings_bp.route("/api/settings/electricity-price", methods=["GET"])
def api_get_price():
    """Public-ish: app tenant cũng cần biết giá điện hiện tại."""
    return jsonify({
        "success": True,
        "data": {
            "electricity_price": get_electricity_price(),
        },
    })
