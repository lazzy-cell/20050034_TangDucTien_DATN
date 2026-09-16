from flask import Blueprint, jsonify, request

from services.auth_service import require_landlord
from services.payment_service import (
    create_payment,
    get_all_payments,
    get_payment,
    get_room_payments
)


payments_bp = Blueprint(
    "payments",
    __name__
)


@payments_bp.route(
    "/api/payments",
    methods=["POST"]
)
@require_landlord
def create_new_payment():
    try:
        data = request.get_json(silent=True) or {}

        room_id = data.get("room_id")
        period = data.get("period")
        payment_method = data.get("payment_method")

        if not room_id:
            return jsonify({
                "success": False,
                "message": "room_id is required"
            }), 400

        if not period:
            return jsonify({
                "success": False,
                "message": "period is required"
            }), 400

        if not payment_method:
            return jsonify({
                "success": False,
                "message": "payment_method is required"
            }), 400

        result = create_payment(
            room_id,
            period,
            payment_method
        )

        return jsonify({
            "success": True,
            "message": "Payment completed successfully",
            "data": result
        }), 201

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


@payments_bp.route(
    "/api/payments",
    methods=["GET"]
)
@require_landlord
def get_payments():
    try:
        room_id = request.args.get("room_id")
        tenant_id = request.args.get("tenant_id")

        result = get_all_payments(
            room_id=room_id,
            tenant_id=tenant_id
        )

        return jsonify({
            "success": True,
            "count": len(result),
            "data": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@payments_bp.route(
    "/api/payments/<payment_id>",
    methods=["GET"]
)
@require_landlord
def get_payment_by_id(payment_id):
    try:
        result = get_payment(payment_id)

        if result is None:
            return jsonify({
                "success": False,
                "message": "Payment not found"
            }), 404

        return jsonify({
            "success": True,
            "data": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@payments_bp.route(
    "/api/payments/room/<room_id>",
    methods=["GET"]
)
@require_landlord
def get_payments_by_room(room_id):
    try:
        result = get_room_payments(room_id)

        return jsonify({
            "success": True,
            "count": len(result),
            "data": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500