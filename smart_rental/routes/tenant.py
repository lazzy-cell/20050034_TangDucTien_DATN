from flask import Blueprint, jsonify, request

from services.auth_service import require_tenant
from services.firebase_service import get_firestore, get_realtime_db
from services.tenant_service import get_tenant_by_auth_uid, update_tenant
from services.contract_service import get_active_contract_by_tenant
from services.billing_service import get_bill
from services.payment_service import get_all_payments
from services.tuya_service import control_room_power

tenant_bp = Blueprint("tenant", __name__)
db = get_firestore()


def _tenant_context():
    uid = (request.current_user or {}).get("uid")
    tenant = get_tenant_by_auth_uid(uid)
    if not tenant:
        return None, None
    contract = get_active_contract_by_tenant(tenant["id"])
    return tenant, contract


def _serialize(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value


def _tenant_required_context():
    tenant, contract = _tenant_context()
    if not tenant:
        return None, None, (jsonify({
            "success": False,
            "message": "Tenant profile not found"
        }), 404)
    if not contract:
        return tenant, None, (jsonify({
            "success": False,
            "message": "Bạn chưa có hợp đồng đang hoạt động."
        }), 404)
    return tenant, contract, None


@tenant_bp.route("/api/tenant/me", methods=["GET"])
@require_tenant
def get_my_profile():
    tenant, _ = _tenant_context()
    if not tenant:
        return jsonify({"success": False, "message": "Tenant profile not found"}), 404
    return jsonify({"success": True, "data": tenant})


@tenant_bp.route("/api/tenant/me", methods=["PUT"])
@require_tenant
def update_my_profile():
    tenant, _ = _tenant_context()
    if not tenant:
        return jsonify({"success": False, "message": "Tenant profile not found"}), 404

    data = request.get_json(silent=True) or {}
    # Tenant chỉ được sửa thông tin liên hệ; không được tự đổi email/status/identity.
    allowed = {k: data[k] for k in ("name", "phone", "address") if k in data}
    if not allowed:
        return jsonify({
            "success": False,
            "message": "Chỉ hỗ trợ cập nhật name, phone, address"
        }), 400

    try:
        result = update_tenant(tenant["id"], allowed)
        return jsonify({"success": True, "message": "Cập nhật thông tin thành công", "data": result})
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@tenant_bp.route("/api/tenant/room", methods=["GET"])
@require_tenant
def get_my_room():
    tenant, contract, error = _tenant_required_context()
    if error:
        return error

    room_id = str(contract["room_id"])
    room_doc = db.collection("rooms").document(room_id).get()
    if not room_doc.exists:
        return jsonify({"success": False, "message": "Room not found"}), 404

    room = room_doc.to_dict() or {}
    room["id"] = room_doc.id
    # Không expose device_id cho tenant.
    room.pop("device_id", None)

    realtime = get_realtime_db().child("rooms").child(room_id).get() or {}
    return jsonify({
        "success": True,
        "data": {
            "room": _serialize(room),
            "contract": _serialize(contract),
            "realtime": _serialize({
                "online": realtime.get("online"),
                "switch": realtime.get("switch"),
                "power": realtime.get("power"),
                "voltage": realtime.get("voltage"),
                "current": realtime.get("current"),
                "updated_at": realtime.get("updated_at"),
            }),
        },
    })


@tenant_bp.route("/api/tenant/room/power", methods=["POST"])
@require_tenant
def control_my_room_power():
    tenant, contract, error = _tenant_required_context()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    if not isinstance(data.get("switch"), bool):
        return jsonify({
            "success": False,
            "message": "Field 'switch' (boolean) is required"
        }), 400

    room_id = str(contract["room_id"])
    reason = (data.get("reason") or "Tenant điều khiển điện").strip()
    triggered_by = tenant.get("email") or request.current_user.get("uid")

    try:
        result = control_room_power(
            room_id=room_id,
            switch_on=data["switch"],
            triggered_by=triggered_by,
            reason=reason,
        )
        return jsonify(result), 200 if result.get("success") else 400
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@tenant_bp.route("/api/tenant/power-history", methods=["GET"])
@require_tenant
def get_my_power_history():
    tenant, contract, error = _tenant_required_context()
    if error:
        return error

    try:
        limit = min(max(int(request.args.get("limit", 100)), 1), 200)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "limit must be an integer"}), 400

    room_id = str(contract["room_id"])
    result = []
    for doc in db.collection("control_history").stream():
        item = doc.to_dict() or {}
        if str(item.get("room_id")) != room_id:
            continue
        item["id"] = doc.id
        item.pop("tuya_response", None)
        result.append(_serialize(item))

    result.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
    result = result[:limit]
    return jsonify({"success": True, "count": len(result), "data": result})


@tenant_bp.route("/api/tenant/energy-history", methods=["GET"])
@require_tenant
def get_my_energy_history():
    tenant, contract, error = _tenant_required_context()
    if error:
        return error

    try:
        limit = min(max(int(request.args.get("limit", 100)), 1), 200)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "limit must be an integer"}), 400

    room_id = str(contract["room_id"])
    result = []
    for doc in db.collection("rooms").document(room_id).collection("energy_history").stream():
        item = doc.to_dict() or {}
        item["id"] = doc.id
        result.append(_serialize(item))
    result.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
    result = result[:limit]
    return jsonify({"success": True, "count": len(result), "data": result})


@tenant_bp.route("/api/tenant/contracts", methods=["GET"])
@require_tenant
def get_my_contracts():
    tenant, _ = _tenant_context()
    if not tenant:
        return jsonify({"success": False, "message": "Tenant profile not found"}), 404

    docs = (
        db.collection("contracts")
        .where("tenant_id", "==", str(tenant["id"]))
        .stream()
    )
    result = []
    for doc in docs:
        item = doc.to_dict() or {}
        item["id"] = doc.id
        room_id = item.get("room_id")
        room_doc = db.collection("rooms").document(str(room_id)).get() if room_id else None
        item["room"] = {
            "id": room_id,
            "room_name": (room_doc.to_dict() or {}).get("room_name") if room_doc and room_doc.exists else room_id
        }
        result.append(_serialize(item))

    result.sort(key=lambda x: str(x.get("start_date") or ""), reverse=True)
    return jsonify({"success": True, "count": len(result), "data": result})


@tenant_bp.route("/api/tenant/contract", methods=["GET"])
@require_tenant
def get_my_contract():
    tenant, contract = _tenant_context()
    if not tenant:
        return jsonify({"success": False, "message": "Tenant profile not found"}), 404
    if not contract:
        return jsonify({"success": False, "message": "Bạn chưa có hợp đồng đang hoạt động."}), 404

    result = dict(contract)
    result["tenant"] = {
        "id": tenant.get("id"),
        "name": tenant.get("name"),
        "email": tenant.get("email"),
        "phone": tenant.get("phone"),
    }
    room_doc = db.collection("rooms").document(str(contract["room_id"])).get()
    if room_doc.exists:
        result["room"] = {"id": room_doc.id, "room_name": (room_doc.to_dict() or {}).get("room_name")}
    return jsonify({"success": True, "data": _serialize(result)})


@tenant_bp.route("/api/tenant/bills", methods=["GET"])
@require_tenant
def get_my_bills():
    tenant, _ = _tenant_context()
    if not tenant:
        return jsonify({"success": False, "message": "Tenant profile not found"}), 404

    period = (request.args.get("period") or "").strip()

    # Active invoices remain under each room.
    bills = []
    for room_doc in db.collection("rooms").stream():
        for doc in room_doc.reference.collection("bills").stream():
            item = doc.to_dict() or {}
            if str(item.get("tenant_id")) != str(tenant["id"]):
                continue
            if period and item.get("period") != period:
                continue
            item["id"] = doc.id
            bills.append(_serialize(item))

    for doc in db.collection("bill_history").stream():
        item = doc.to_dict() or {}
        if str(item.get("tenant_id")) != str(tenant["id"]):
            continue
        if period and item.get("period") != period:
            continue
        item["id"] = doc.id
        item["archived"] = True
        bills.append(_serialize(item))

    bills.sort(
        key=lambda x: str(x.get("status_changed_at") or x.get("generated_at") or x.get("archived_at") or ""),
        reverse=True,
    )
    return jsonify({"success": True, "count": len(bills), "data": bills})


@tenant_bp.route("/api/tenant/bills/<period>", methods=["GET"])
@require_tenant
def get_my_bill(period):
    tenant, _ = _tenant_context()
    if not tenant:
        return jsonify({"success": False, "message": "Tenant profile not found"}), 404

    for room_doc in db.collection("rooms").stream():
        bill = get_bill(room_doc.id, period)
        if bill and str(bill.get("tenant_id")) == str(tenant["id"]):
            return jsonify({"success": True, "data": bill})
    return jsonify({"success": False, "message": "Bill not found"}), 404


@tenant_bp.route("/api/tenant/payments", methods=["GET"])
@require_tenant
def get_my_payments():
    tenant, _ = _tenant_context()
    if not tenant:
        return jsonify({"success": False, "message": "Tenant profile not found"}), 404

    result = []
    for doc in db.collection("payments").stream():
        item = doc.to_dict() or {}
        if str(item.get("tenant_id")) != str(tenant["id"]):
            continue
        item["id"] = doc.id
        result.append(_serialize(item))
    result.sort(key=lambda x: str(x.get("paid_at") or x.get("created_at") or ""), reverse=True)
    return jsonify({"success": True, "count": len(result), "data": result})


@tenant_bp.route("/api/tenant/notifications", methods=["GET"])
@require_tenant
def get_my_notifications():
    tenant, _ = _tenant_context()
    if not tenant:
        return jsonify({"success": False, "message": "Tenant profile not found"}), 404

    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "limit must be an integer"}), 400

    items = []
    for doc in db.collection("tenant_notifications").stream():
        item = doc.to_dict() or {}
        if str(item.get("tenant_id")) != str(tenant["id"]):
            continue
        item["id"] = doc.id
        items.append(_serialize(item))
    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    items = items[:limit]
    return jsonify({"success": True, "count": len(items), "data": items})
