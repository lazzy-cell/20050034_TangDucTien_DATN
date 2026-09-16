from flask import Blueprint, request, jsonify

from config import Config
from services.auth_service import require_landlord
from services.occupancy_service import (
    update_occupancy,
    get_room_occupancy,
    get_all_occupancy,
    get_occupancy_history,
)


occupancy_bp = Blueprint("occupancy", __name__)


def _validate_occupancy_payload(body):
    occupied = body.get("occupied")

    if not isinstance(occupied, bool):
        return None, ({
            "success": False,
            "message": "Field 'occupied' (bool) is required and must be a boolean",
        }, 400)

    person_count = body.get("person_count", 1 if occupied else 0)

    try:
        person_count = int(person_count)
    except (TypeError, ValueError):
        return None, ({
            "success": False,
            "message": "Field 'person_count' must be an integer",
        }, 400)

    if person_count < 0:
        return None, ({
            "success": False,
            "message": "Field 'person_count' cannot be negative",
        }, 400)

    return (occupied, person_count), None


def _update_from_request(room_id):
    body = request.get_json(silent=True) or {}
    parsed, error = _validate_occupancy_payload(body)
    if error:
        return error

    occupied, person_count = parsed

    result = update_occupancy(
        room_id=room_id,
        occupied=occupied,
        person_count=person_count,
        confidence=body.get("confidence"),
        source=body.get("source", "computer_vision"),
        snapshot_url=body.get("snapshot_url"),
        extra=body.get("extra"),
    )

    if not result.get("success"):
        return result, 404

    return result, 200


def _check_monitoring_api_key():
    """Xác thực node detect_person bằng API key nếu server đã cấu hình key."""
    expected = Config.OCCUPANCY_API_KEY

    # Không cấu hình key => giữ tương thích với triển khai hiện tại.
    if not expected:
        return None

    supplied = request.headers.get("X-Occupancy-API-Key", "").strip()
    if not supplied or supplied != expected:
        return jsonify({
            "success": False,
            "message": "Invalid or missing occupancy API key",
        }), 401

    return None


@occupancy_bp.route("/api/occupancy", methods=["GET"])
@require_landlord
def list_occupancy():
    """Tổng hợp occupancy toàn bộ phòng."""
    try:
        data = get_all_occupancy()

        return jsonify({
            "success": True,
            "data": data,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 500


@occupancy_bp.route("/api/occupancy/<room_id>", methods=["GET"])
@require_landlord
def room_occupancy(room_id):
    try:
        data = get_room_occupancy(room_id)

        if data is None:
            return jsonify({
                "success": False,
                "message": "Room not found",
            }), 404

        return jsonify({
            "success": True,
            "data": data,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 500


@occupancy_bp.route("/api/occupancy/<room_id>", methods=["POST"])
def post_occupancy(room_id):
    """Endpoint tương thích cũ; node mới nên dùng /api/monitoring/occupancy."""
    try:
        result, status = _update_from_request(room_id)
        return jsonify(result), status

    except ValueError as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 400

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 500


@occupancy_bp.route("/api/monitoring/occupancy", methods=["POST"])
def monitoring_occupancy():
    """
    API dành cho detect_person/Raspberry Pi.

    Header tùy chọn (bắt buộc nếu OCCUPANCY_API_KEY được cấu hình):
        X-Occupancy-API-Key: <key>

    JSON:
        {
          "room_id": "<firestore room document id>",
          "occupied": true,
          "person_count": 1,
          "confidence": 0.91,
          "source": "computer_vision"
        }
    """
    auth_error = _check_monitoring_api_key()
    if auth_error:
        return auth_error

    try:
        body = request.get_json(silent=True) or {}
        room_id = str(body.get("room_id") or "").strip()

        if not room_id:
            return jsonify({
                "success": False,
                "message": "Field 'room_id' is required",
            }), 400

        result, status = _update_from_request(room_id)
        return jsonify(result), status

    except ValueError as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 400

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 500


@occupancy_bp.route("/api/monitoring/occupancy/<room_id>", methods=["POST"])
def monitoring_occupancy_by_room(room_id):
    """Biến thể URL để node đã biết room_id có thể POST trực tiếp."""
    auth_error = _check_monitoring_api_key()
    if auth_error:
        return auth_error

    try:
        result, status = _update_from_request(room_id)
        return jsonify(result), status

    except ValueError as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 400

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 500


@occupancy_bp.route("/api/occupancy/<room_id>/history", methods=["GET"])
@require_landlord
def occupancy_history(room_id):
    try:
        limit = request.args.get("limit", 50)

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            return jsonify({
                "success": False,
                "message": "limit must be an integer",
            }), 400

        if limit <= 0:
            return jsonify({
                "success": False,
                "message": "limit must be greater than 0",
            }), 400

        history = get_occupancy_history(
            room_id,
            limit=limit
        )

        if history is None:
            return jsonify({
                "success": False,
                "message": "Room not found",
            }), 404

        return jsonify({
            "success": True,
            "count": len(history),
            "data": history,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 500
