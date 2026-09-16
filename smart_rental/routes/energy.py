from flask import Blueprint, jsonify
from services.auth_service import require_landlord
from services.firebase_service import (
    get_firestore,
    get_realtime_db
)


energy_bp = Blueprint(
    "energy",
    __name__
)


firestore_db = get_firestore()

realtime_db = get_realtime_db()


# ==========================================
# LẤY DỮ LIỆU REALTIME CỦA 1 PHÒNG
# ==========================================

@energy_bp.route(
    "/api/energy/<room_id>/realtime",
    methods=["GET"]
)
@require_landlord
def get_realtime_energy(room_id):

    data = (
        realtime_db
        .child("rooms")
        .child(room_id)
        .get()
    )


    if not data:

        return jsonify({

            "success": False,

            "message":
            "No realtime data found"

        }), 404


    return jsonify({

        "success": True,

        "room_id": room_id,

        "data": data
    })


# ==========================================
# LẤY LỊCH SỬ ĐIỆN NĂNG
# ==========================================

@energy_bp.route(
    "/api/energy/<room_id>/history",
    methods=["GET"]
)
@require_landlord
def get_energy_history(room_id):

    docs = (

        firestore_db
        .collection("rooms")
        .document(room_id)
        .collection("energy_history")
        .order_by(
            "timestamp"
        )
        .stream()
    )


    history = []


    for doc in docs:

        data = doc.to_dict()

        data["id"] = doc.id


        if "timestamp" in data:

            data["timestamp"] = (
                data["timestamp"]
                .isoformat()
            )


        history.append(
            data
        )


    return jsonify({

        "success": True,

        "room_id": room_id,

        "data": history
    })