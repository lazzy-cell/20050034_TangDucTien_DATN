from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from google.cloud.firestore_v1.base_query import FieldFilter

from services.firebase_service import get_firestore
from services.auth_service import require_landlord

alerts_bp = Blueprint("alerts", __name__)

firestore_db = get_firestore()


def serialize_alert(data):
    if data.get("created_at"):
        data["created_at"] = data["created_at"].isoformat()

    if data.get("updated_at"):
        data["updated_at"] = data["updated_at"].isoformat()

    return data


@alerts_bp.route("/api/alerts", methods=["GET"])
@require_landlord
def get_alerts():
    try:
        status = request.args.get("status")
        room_id = request.args.get("room_id")

        query = firestore_db.collection("alerts")

        if status:
            query = query.where(
                filter=FieldFilter("status", "==", status)
            )

        if room_id:
            query = query.where(
                filter=FieldFilter("room_id", "==", room_id)
            )

        docs = query.order_by(
            "created_at",
            direction="DESCENDING"
        ).stream()

        alerts = []

        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id

            alerts.append(
                serialize_alert(data)
            )

        return jsonify({
            "success": True,
            "count": len(alerts),
            "data": alerts
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@alerts_bp.route(
    "/api/alerts/<alert_id>/resolve",
    methods=["PATCH"]
)
@require_landlord
def resolve_alert_by_id(alert_id):
    try:
        alert_ref = (
            firestore_db
            .collection("alerts")
            .document(alert_id)
        )

        alert_doc = alert_ref.get()

        if not alert_doc.exists:
            return jsonify({
                "success": False,
                "message": "Alert not found"
            }), 404

        alert_ref.update({
            "status": "resolved",
            "updated_at": datetime.now(timezone.utc)
        })

        return jsonify({
            "success": True,
            "message": "Alert resolved"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@alerts_bp.route("/api/alerts/<alert_id>", methods=["GET"])
@require_landlord
def get_alert_detail(alert_id):
    try:
        ref = firestore_db.collection("alerts").document(str(alert_id))
        doc = ref.get()
        if not doc.exists:
            return jsonify({"success": False, "message": "Alert not found"}), 404
        data = doc.to_dict() or {}
        data["id"] = doc.id
        room = None
        tenant = None
        rid = data.get("room_id")
        if rid:
            rd = firestore_db.collection("rooms").document(str(rid)).get()
            if rd.exists:
                room = rd.to_dict() or {}
                room["room_id"] = rd.id
                tid = room.get("tenant_id")
                if tid:
                    td = firestore_db.collection("tenants").document(str(tid)).get()
                    if td.exists:
                        tenant = td.to_dict() or {}
                        tenant["id"] = td.id
        data["room"] = {"room_id": room["room_id"], "room_name": room.get("room_name")} if room else None
        data["tenant"] = {"id": tenant["id"], "name": tenant.get("name")} if tenant else None
        return jsonify({"success": True, "data": serialize_alert(data)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
