from flask import Blueprint, jsonify

from services.daily_energy_service import get_daily_energy


daily_energy_bp = Blueprint(
    "daily_energy",
    __name__
)


@daily_energy_bp.route(
    "/api/energy/room/<room_id>/daily",
    methods=["GET"]
)
def get_room_daily_energy(room_id):

    result = get_daily_energy(room_id)

    return jsonify({
        "success": True,
        "data": result
    })