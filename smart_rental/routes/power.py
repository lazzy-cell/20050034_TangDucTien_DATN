from flask import Blueprint, request, jsonify

from services.auth_service import require_landlord
from services.tuya_service import control_room_power
from services.firebase_service import get_firestore, get_realtime_db


power_bp = Blueprint("power", __name__)


@power_bp.route("/api/rooms/<room_id>/power", methods=["POST"])
@require_landlord
def set_room_power(room_id):
    try:
        data = request.get_json(silent=True) or {}

        if "switch" not in data:
            return jsonify({
                "success": False,
                "message": "Field 'switch' (boolean) is required",
            }), 400

        if not isinstance(data.get("switch"), bool):
            return jsonify({
                "success": False,
                "message": "Field 'switch' must be a boolean",
            }), 400

        switch_on = data["switch"]
        reason = data.get("reason") or "Manual control from API"

        user = getattr(request, "current_user", {})

        # Firebase ID token không còn username như JWT cũ.
        # Ưu tiên email, nếu không có thì dùng uid.
        triggered_by = (
            user.get("email")
            or user.get("uid")
            or "manual"
        )

        result = control_room_power(
            room_id=room_id,
            switch_on=switch_on,
            triggered_by=triggered_by,
            reason=reason,
        )

        status_code = 200 if result.get("success") else 400

        return jsonify(result), status_code

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


@power_bp.route("/api/rooms/<room_id>/power", methods=["GET"])
@require_landlord
def get_room_power_status(room_id):
    try:
        firestore_db = get_firestore()

        room_doc = (
            firestore_db
            .collection("rooms")
            .document(room_id)
            .get()
        )

        if not room_doc.exists:
            return jsonify({
                "success": False,
                "message": "Room not found",
            }), 404

        room = room_doc.to_dict() or {}

        realtime_db = get_realtime_db()

        realtime = (
            realtime_db
            .child("rooms")
            .child(room_id)
            .get()
            or {}
        )

        return jsonify({
            "success": True,
            "data": {
                "room_id": room_id,
                "device_id": room.get("device_id"),
                "switch": realtime.get("switch"),
                "online": realtime.get("online"),
                "power": realtime.get("power"),
                "voltage": realtime.get("voltage"),
                "current": realtime.get("current"),
                "updated_at": realtime.get("updated_at"),
            },
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 500


@power_bp.route("/api/control-history", methods=["GET"])
@require_landlord
def get_control_history():
    try:
        firestore_db = get_firestore()

        room_id = request.args.get("room_id")

        try:
            limit = int(request.args.get("limit", 50))
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

        limit = min(limit, 200)

        query = firestore_db.collection("control_history")

        if room_id:
            query = query.where(
                "room_id",
                "==",
                room_id
            )

        docs = (
            query
            .order_by(
                "timestamp",
                direction="DESCENDING"
            )
            .limit(limit)
            .stream()
        )

        history = []

        for doc in docs:
            data = doc.to_dict() or {}
            data["id"] = doc.id

            if data.get("timestamp"):
                data["timestamp"] = data["timestamp"].isoformat()

            # Không trả raw Tuya response về frontend.
            data.pop("tuya_response", None)

            history.append(data)

        return jsonify({
            "success": True,
            "count": len(history),
            "data": history,
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 500


@power_bp.route("/api/rooms/power/batch", methods=["POST"])
@require_landlord
def set_batch_room_power():
    try:
        data = request.get_json(silent=True) or {}

        room_ids = data.get("room_ids") or []

        if not isinstance(room_ids, list) or not room_ids:
            return jsonify({
                "success": False,
                "message": "room_ids (array) is required",
            }), 400

        if "switch" not in data:
            return jsonify({
                "success": False,
                "message": "Field 'switch' (boolean) is required",
            }), 400

        if not isinstance(data.get("switch"), bool):
            return jsonify({
                "success": False,
                "message": "Field 'switch' must be a boolean",
            }), 400

        switch_on = data["switch"]

        reason = data.get("reason")

        if not reason:
            reason = (
                "Bật điện hàng loạt từ Dashboard"
                if switch_on
                else "Ngắt điện hàng loạt từ Dashboard"
            )

        user = getattr(request, "current_user", {})

        # Firebase ID token không có username.
        # Ưu tiên email, nếu không có thì dùng uid.
        triggered_by = (
            user.get("email")
            or user.get("uid")
            or "manual"
        )

        results = []
        ok_count = 0

        for room_id in room_ids:
            room_id = str(room_id).strip()

            if not room_id:
                continue

            try:
                result = control_room_power(
                    room_id=room_id,
                    switch_on=switch_on,
                    triggered_by=triggered_by,
                    reason=reason,
                )

                if result.get("success"):
                    ok_count += 1

                results.append({
                    "room_id": room_id,
                    **result,
                })

            except Exception as e:
                results.append({
                    "room_id": room_id,
                    "success": False,
                    "message": str(e),
                })

        total = len(results)

        return jsonify({
            "success": ok_count > 0,
            "message": f"Đã xử lý {ok_count}/{total} phòng",
            "ok_count": ok_count,
            "total": total,
            "data": results,
        }), 200 if ok_count > 0 else 400

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 500