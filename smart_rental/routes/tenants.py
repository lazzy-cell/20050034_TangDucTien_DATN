from flask import Blueprint, jsonify, request

from services.auth_service import require_landlord, require_tenant
from services.tenant_service import (
    create_tenant,
    get_all_tenants,
    get_tenant_by_id,
    update_tenant,
    delete_tenant,
    get_tenant_by_auth_uid,
    complete_tenant_password_setup,
    reset_tenant_password
)




def enrich_tenant_with_relationships(tenant):
    """Expose human-readable linked room/contract summaries without internal IDs."""
    result = dict(tenant or {})
    db = __import__("services.firebase_service", fromlist=["get_firestore"]).get_firestore()
    contracts = []
    for doc in db.collection("contracts").where("tenant_id", "==", result.get("id")).stream():
        c = doc.to_dict() or {}
        if c.get("status") != "active":
            continue
        room_id = c.get("room_id")
        room_name = None
        if room_id:
            rd = db.collection("rooms").document(str(room_id)).get()
            if rd.exists:
                room_name = (rd.to_dict() or {}).get("room_name")
        contracts.append({
            "id": doc.id,
            "room_id": room_id,
            "room_name": room_name or room_id
        })
    result["active_contracts"] = contracts
    result["linked_rooms"] = [{"room_id": x["room_id"], "room_name": x["room_name"]} for x in contracts]
    return result

tenants_bp = Blueprint("tenants", __name__)


def serialize_tenant(data):
    result = dict(data or {})
    for field in ("created_at", "updated_at"):
        value = result.get(field)
        if hasattr(value, "isoformat"):
            result[field] = value.isoformat()
    result.pop("password", None)
    result.pop("password_hash", None)
    return result


@tenants_bp.route("/api/tenants", methods=["POST"])
@require_landlord
def create_new_tenant():
    try:
        data = request.get_json(silent=True) or {}

        if not data:
            return jsonify({
                "success": False,
                "message": "Request body is required"
            }), 400

        if not data.get("name"):
            return jsonify({
                "success": False,
                "message": "Tenant name is required"
            }), 400

        if not data.get("phone"):
            return jsonify({
                "success": False,
                "message": "Phone number is required"
            }), 400

        if not data.get("email"):
            return jsonify({
                "success": False,
                "message": "Email is required"
            }), 400

        tenant = create_tenant(data)

        return jsonify({
            "success": True,
            "message": "Tenant created successfully. The dashboard will send a password-reset email to the tenant.",
            "data": serialize_tenant(tenant)
        }), 201

    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@tenants_bp.route("/api/tenants", methods=["GET"])
@require_landlord
def get_tenants():
    try:
        tenants = get_all_tenants()

        result = [
            enrich_tenant_with_relationships(serialize_tenant(tenant))
            for tenant in tenants
        ]

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


@tenants_bp.route("/api/tenants/<tenant_id>", methods=["GET"])
@require_landlord
def get_tenant(tenant_id):
    try:
        tenant = get_tenant_by_id(tenant_id)

        if not tenant:
            return jsonify({
                "success": False,
                "message": "Tenant not found"
            }), 404

        return jsonify({
            "success": True,
            "data": enrich_tenant_with_relationships(serialize_tenant(tenant))
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@tenants_bp.route("/api/tenant/me", methods=["GET"])
@require_tenant
def tenant_me():
    tenant = get_tenant_by_auth_uid(request.current_user.get("uid"))
    if not tenant:
        return jsonify({"success": False, "message": "Tenant profile not found"}), 404
    return jsonify({"success": True, "data": tenant})


@tenants_bp.route("/api/tenant/me/password-setup-complete", methods=["POST"])
@require_tenant
def tenant_password_setup_complete():
    tenant = complete_tenant_password_setup(request.current_user.get("uid"))
    return jsonify({
        "success": True,
        "message": "Password setup completed",
        "data": tenant,
    })


@tenants_bp.route("/api/tenants/<tenant_id>", methods=["PUT"])
@require_landlord
def update_existing_tenant(tenant_id):
    try:
        data = request.get_json(silent=True) or {}

        if not data:
            return jsonify({
                "success": False,
                "message": "Request body is required"
            }), 400

        tenant = update_tenant(tenant_id, data)

        if not tenant:
            return jsonify({
                "success": False,
                "message": "Tenant not found"
            }), 404

        return jsonify({
            "success": True,
            "message": "Tenant updated successfully",
            "data": serialize_tenant(tenant)
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@tenants_bp.route("/api/tenants/<tenant_id>/reset-password", methods=["POST"])
@require_landlord
def reset_password(tenant_id):
    """Admin fallback reset: generate a temporary password server-side."""
    try:
        import secrets, string
        password = "".join(secrets.choice(string.ascii_letters + string.digits + "!@#$%") for _ in range(12))
        reset_tenant_password(tenant_id, password)
        return jsonify({"success": True, "message": "Đã đặt lại mật khẩu tạm thời.", "data": {"temporary_password": password}})
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@tenants_bp.route("/api/tenants/<tenant_id>", methods=["DELETE"])
@require_landlord
def delete_existing_tenant(tenant_id):
    try:
        success = delete_tenant(tenant_id)

        if not success:
            return jsonify({
                "success": False,
                "message": "Tenant not found"
            }), 404

        return jsonify({
            "success": True,
            "message": "Tenant deleted successfully"
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
