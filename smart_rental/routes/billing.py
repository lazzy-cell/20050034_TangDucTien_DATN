from flask import Blueprint, jsonify, request
from services.firebase_service import get_firestore

from services.auth_service import require_landlord
from services.billing_service import (
    calculate_current_bill,
    generate_month_bill,
    get_bill,
    update_bill_status
)


billing_bp = Blueprint("billing", __name__)
firestore_db = get_firestore()


@billing_bp.route(
    "/api/billing/room/<room_id>/current",
    methods=["GET"]
)
@require_landlord
def get_current_bill(room_id):
    try:
        period = request.args.get("period")

        result = calculate_current_bill(room_id, period)

        return jsonify({
            "success": True,
            "data": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400


@billing_bp.route(
    "/api/billing/room/<room_id>/generate",
    methods=["POST"]
)
@require_landlord
def generate_bill(room_id):
    try:
        data = request.get_json(silent=True) or {}

        period = data.get("period")

        result = generate_month_bill(room_id, period)

        return jsonify({
            "success": True,
            "message": "Bill generated successfully",
            "data": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400


@billing_bp.route(
    "/api/billing/room/<room_id>/<period>",
    methods=["GET"]
)
@require_landlord
def get_room_bill(room_id, period):
    try:
        result = get_bill(room_id, period)

        if result is None:
            return jsonify({
                "success": False,
                "message": "Bill not found"
            }), 404

        return jsonify({
            "success": True,
            "data": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400


@billing_bp.route(
    "/api/billing/room/<room_id>/<period>/status",
    methods=["PATCH"]
)
@require_landlord
def change_bill_status(room_id, period):
    try:
        data = request.get_json(silent=True) or {}

        status = data.get("status")

        if not status:
            return jsonify({
                "success": False,
                "message": "Status is required"
            }), 400

        result = update_bill_status(
            room_id,
            period,
            status
        )

        if result is None:
            return jsonify({
                "success": False,
                "message": "Bill not found"
            }), 404

        return jsonify({
            "success": True,
            "message": "Bill status updated",
            "data": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400


@billing_bp.route(
    "/api/billing/room/<room_id>/<period>/cancel",
    methods=["POST"]
)
@require_landlord
def cancel_bill(room_id, period):
    """Admin action: cancel a specific unpaid invoice and archive it."""
    try:
        result = update_bill_status(room_id, period, "cancelled")

        if result is None:
            return jsonify({
                "success": False,
                "message": "Bill not found"
            }), 404

        return jsonify({
            "success": True,
            "message": "Bill cancelled and archived",
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@billing_bp.route("/api/billing", methods=["GET"])
@require_landlord
def list_bills():
    """List active/unpaid bills and immutable historical paid/cancelled bills."""
    try:
        room_id = (request.args.get("room_id") or "").strip()
        period = (request.args.get("period") or "").strip()

        rooms = {}
        tenants = {}
        contracts = {}

        for rd in firestore_db.collection("rooms").stream():
            rooms[rd.id] = (rd.to_dict() or {}).get("room_name") or rd.id
        for td in firestore_db.collection("tenants").stream():
            tenants[td.id] = (td.to_dict() or {}).get("name") or td.id
        for cd in firestore_db.collection("contracts").stream():
            contracts[cd.id] = cd.to_dict() or {}

        bills = []

        # Unpaid/current invoices remain attached to their room.
        for rd in firestore_db.collection("rooms").stream():
            if room_id and rd.id != room_id:
                continue

            room_data = rd.to_dict() or {}
            sub = rd.reference.collection("bills").stream()

            for bd in sub:
                data = bd.to_dict() or {}
                if period and data.get("period") != period:
                    continue

                data["id"] = bd.id
                data["room_id"] = rd.id
                data["room_name"] = data.get("room_name") or rooms.get(rd.id, rd.id)

                snapshot = data.get("tenant_snapshot") or {}
                data["tenant_name"] = (
                    snapshot.get("name")
                    or tenants.get(data.get("tenant_id"), "—")
                )
                c = contracts.get(data.get("contract_id"), {})
                data["contract_start_date"] = c.get("start_date")
                data["archived"] = False
                bills.append(data)

        # Paid/cancelled invoices are independent of rooms and survive room deletion.
        history_docs = firestore_db.collection("bill_history").stream()
        for hd in history_docs:
            data = hd.to_dict() or {}
            if room_id and data.get("room_id") != room_id:
                continue
            if period and data.get("period") != period:
                continue

            data["id"] = hd.id
            data["room_name"] = (
                data.get("room_name")
                or rooms.get(data.get("room_id"), data.get("room_id", "—"))
            )
            snapshot = data.get("tenant_snapshot") or {}
            data["tenant_name"] = (
                snapshot.get("name")
                or tenants.get(data.get("tenant_id"), "—")
            )
            c = contracts.get(data.get("contract_id"), {})
            data["contract_start_date"] = c.get("start_date")
            data["archived"] = True
            bills.append(data)

        bills.sort(
            key=lambda x: str(
                x.get("status_changed_at")
                or x.get("generated_at")
                or x.get("archived_at")
                or ""
            ),
            reverse=True,
        )

        for b in bills:
            for field in (
                "generated_at",
                "updated_at",
                "paid_at",
                "status_changed_at",
                "archived_at",
            ):
                if hasattr(b.get(field), "isoformat"):
                    b[field] = b[field].isoformat()

        return jsonify({
            "success": True,
            "count": len(bills),
            "data": bills
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
