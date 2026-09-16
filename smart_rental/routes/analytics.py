from flask import Blueprint, jsonify, request
from services.auth_service import require_landlord
from services.firebase_service import get_firestore
from services.time_service import vn_now
from services.analytics_service import (
    get_today_analytics,
    get_month_analytics,
    get_energy_history_by_range,
    get_analytics_summary
)


analytics_bp = Blueprint(
    "analytics",
    __name__
)


@analytics_bp.route(
    "/api/analytics/room/<room_id>/today",
    methods=["GET"]
)
@require_landlord
def today_analytics(room_id):

    result = get_today_analytics(room_id)

    return jsonify({
        "success": True,
        "data": result
    })


@analytics_bp.route(
    "/api/analytics/room/<room_id>/month",
    methods=["GET"]
)
@require_landlord
def month_analytics(room_id):

    result = get_month_analytics(room_id)

    return jsonify({
        "success": True,
        "data": result
    })



@analytics_bp.route("/api/analytics/summary", methods=["GET"])
@require_landlord
def analytics_summary():
    try:
        granularity = request.args.get("granularity", "month")
        anchor = request.args.get("date") or request.args.get("period")
        result = get_analytics_summary(granularity, anchor)
        return jsonify({"success": True, "data": result})
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@analytics_bp.route("/api/analytics/overview", methods=["GET"])
@require_landlord
def analytics_overview():
    try:
        from datetime import datetime

        period = request.args.get("period") or vn_now().strftime("%Y-%m")
        db = get_firestore()
        rooms = list(db.collection("rooms").stream())

        total_energy = 0.0
        by_room = []

        for rd in rooms:
            rid = rd.id
            name = (rd.to_dict() or {}).get("room_name") or rid
            consumption = 0.0

            for ed in rd.reference.collection("energy_daily").stream():
                d = ed.to_dict() or {}
                if str(d.get("date", "")).startswith(period):
                    consumption += float(d.get("consumption", 0) or 0)

            total_energy += consumption
            by_room.append({
                "room_id": rid,
                "room_name": name,
                "consumption": round(consumption, 3)
            })

        # Current/unpaid bills are still under rooms.
        bills = []
        for rd in rooms:
            for bd in rd.reference.collection("bills").stream():
                b = bd.to_dict() or {}
                if b.get("period") == period:
                    b["id"] = bd.id
                    b["room_id"] = rd.id
                    b["room_name"] = b.get("room_name") or (
                        rd.to_dict() or {}
                    ).get("room_name") or rd.id
                    b["archived"] = False
                    bills.append(b)

        # Terminal invoices are read from the durable history collection,
        # so they remain visible even after their room is deleted.
        for hd in db.collection("bill_history").stream():
            b = hd.to_dict() or {}
            if b.get("period") == period:
                b["id"] = hd.id
                b["archived"] = True
                bills.append(b)

        paid_bills = [b for b in bills if b.get("status") == "paid"]
        unpaid_bills = [b for b in bills if b.get("status") == "unpaid"]
        cancelled_bills = [b for b in bills if b.get("status") == "cancelled"]

        revenue = sum(
            float(b.get("total_cost", 0) or 0) for b in paid_bills
        )
        outstanding = sum(
            float(b.get("total_cost", 0) or 0) for b in unpaid_bills
        )
        cancelled_amount = sum(
            float(b.get("total_cost", 0) or 0) for b in cancelled_bills
        )

        bill_history = []
        for b in sorted(
            bills,
            key=lambda x: str(
                x.get("status_changed_at")
                or x.get("generated_at")
                or x.get("archived_at")
                or ""
            ),
            reverse=True,
        ):
            snapshot = b.get("tenant_snapshot") or {}
            bill_history.append({
                "id": b.get("id"),
                "room_id": b.get("room_id"),
                "room_name": b.get("room_name") or b.get("room_id") or "—",
                "tenant_name": snapshot.get("name") or "—",
                "period": b.get("period"),
                "total_cost": round(float(b.get("total_cost", 0) or 0)),
                "status": b.get("status", "unpaid"),
                "archived": bool(b.get("archived")),
                "status_changed_at": (
                    b.get("status_changed_at")
                    or b.get("paid_at")
                    or b.get("updated_at")
                    or b.get("generated_at")
                ).isoformat()
                if hasattr(
                    b.get("status_changed_at")
                    or b.get("paid_at")
                    or b.get("updated_at")
                    or b.get("generated_at"),
                    "isoformat"
                ) else (
                    b.get("status_changed_at")
                    or b.get("paid_at")
                    or b.get("updated_at")
                    or b.get("generated_at")
                ),
            })

        return jsonify({
            "success": True,
            "data": {
                "period": period,
                "total_rooms": len(rooms),
                "total_energy": round(total_energy, 3),
                "bill_count": len(bills),
                "paid_bills": len(paid_bills),
                "unpaid_bills": len(unpaid_bills),
                "cancelled_bills": len(cancelled_bills),
                "revenue": round(revenue),
                "outstanding": round(outstanding),
                "cancelled_amount": round(cancelled_amount),
                "by_room": by_room,
                "bill_history": bill_history,
            }
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
