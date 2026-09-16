from flask import Blueprint, jsonify

from services.dashboard_service import get_dashboard_overview
from services.auth_service import require_landlord

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route(
    "/api/dashboard/overview",
    methods=["GET"]
)
@require_landlord
def dashboard_overview():
    try:
        result = get_dashboard_overview()

        return jsonify({
            "success": True,
            "data": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500