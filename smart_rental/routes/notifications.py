from datetime import datetime

from flask import Blueprint, request, jsonify

from services.auth_service import require_auth, require_landlord
from services.notification_service import (
    register_push_token,
    unregister_push_token,
    notify_landlords,
    notify_tenant,
    send_expo_push,
    notify_all_tenants,
    get_all_landlord_tokens,
    get_tokens_for_user,
    get_all_tenant_tokens,
)
from services.firebase_service import get_firestore


notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/api/notifications/register", methods=["POST"])
@require_auth
def api_register_token():
    data = request.get_json(silent=True) or {}

    token = (data.get("token") or "").strip()

    if not token:
        return jsonify({
            "success": False,
            "message": "token is required",
        }), 400

    user = getattr(request, "current_user", {}) or {}

    # Firebase ID token:
    # uid    = Firebase Authentication UID
    # email  = email của user
    # role   = custom claim
    role = user.get("role")
    uid = user.get("uid")
    email = user.get("email")

    if role not in ("landlord", "tenant"):
        return jsonify({
            "success": False,
            "message": "Invalid user role",
        }), 403

    if not uid:
        return jsonify({
            "success": False,
            "message": "User UID not found in authentication token",
        }), 401

    try:
        result = register_push_token(
            token=token,
            role=role,
            user_id=uid,
            platform=data.get("platform", "unknown"),
            device_name=data.get("device_name"),
            token_type=data.get("token_type", "fcm"),
        )

        return jsonify({
            "success": True,
            "message": "Push token registered successfully",
            "data": result,
        }), 200

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


@notifications_bp.route("/api/notifications/unregister", methods=["POST"])
@require_auth
def api_unregister_token():
    data = request.get_json(silent=True) or {}

    token = (data.get("token") or "").strip()

    if not token:
        return jsonify({
            "success": False,
            "message": "token is required",
        }), 400

    try:
        ok = unregister_push_token(token)

        return jsonify({
            "success": ok,
            "message": (
                "Unregistered"
                if ok
                else "Token not found"
            ),
        }), 200 if ok else 404

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 500


@notifications_bp.route("/api/notifications/test", methods=["POST"])
@require_landlord
def api_test_push():
    """
    Gửi thử FCM notification tới:
    - body.token nếu được truyền vào
    - tất cả landlord token nếu không truyền token
    """
    data = request.get_json(silent=True) or {}

    title = (
        data.get("title")
        or "Smart Rental"
    ).strip()

    body = (
        data.get("body")
        or "Đây là thông báo thử nghiệm từ Dashboard"
    ).strip()

    token = (data.get("token") or "").strip()

    if token:
        result = send_expo_push(
            [token],
            title,
            body,
            data={
                "type": "test",
            },
        )
    else:
        result = notify_landlords(
            title,
            body,
            data={
                "type": "test",
            },
        )

    return jsonify({
        "success": True,
        "data": result,
    }), 200


@notifications_bp.route("/api/notifications/tokens", methods=["GET"])
@require_landlord
def api_list_tokens_meta():
    """
    Đếm số push token landlord đang active.

    Không trả full token list về frontend vì token là
    thông tin kỹ thuật nhạy cảm.
    """
    try:
        landlords = get_all_landlord_tokens()

        return jsonify({
            "success": True,
            "data": {
                "landlord_token_count": len(landlords),
            },
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 500


@notifications_bp.route("/api/notifications/send", methods=["POST"])
@require_landlord
def api_send_custom_notification():
    data = request.get_json(silent=True) or {}

    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    target = (
        data.get("target")
        or "all_tenants"
    ).strip()

    tenant_id = data.get("tenant_id")

    if not title or not body:
        return jsonify({
            "success": False,
            "message": "title và body là bắt buộc",
        }), 400

    allowed_targets = (
        "landlords",
        "tenant",
        "all_tenants",
    )

    if target not in allowed_targets:
        return jsonify({
            "success": False,
            "message": (
                "target không hợp lệ. "
                "Cho phép: landlords, tenant, all_tenants"
            ),
        }), 400

    payload_data = {
        "type": "admin_message",
        "target": target,
    }

    try:
        if target == "landlords":
            result = notify_landlords(
                title,
                body,
                data=payload_data,
            )

        elif target == "tenant":
            if not tenant_id:
                return jsonify({
                    "success": False,
                    "message": (
                        "tenant_id is required "
                        "when target=tenant"
                    ),
                }), 400

            tenant_id = str(tenant_id)

            result = notify_tenant(
                tenant_id,
                title,
                body,
                data={
                    **payload_data,
                    "tenant_id": tenant_id,
                },
            )

        else:
            # all_tenants: push + lưu inbox để app có thể xem lại.
            result = notify_all_tenants(
                title,
                body,
                data=payload_data,
            )

        return jsonify({
            "success": True,
            "message": "Đã gửi thông báo",
            "data": result,
        }), 200

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


@notifications_bp.route("/api/notifications/logs", methods=["GET"])
@require_landlord
def api_notification_logs():
    try:
        db = get_firestore()

        try:
            limit = int(
                request.args.get(
                    "limit",
                    30,
                )
            )
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

        limit = min(limit, 100)

        docs = (
            db.collection("notification_logs")
            .order_by(
                "created_at",
                direction="DESCENDING",
            )
            .limit(limit)
            .stream()
        )

        logs = []

        for doc in docs:
            data = doc.to_dict() or {}

            data["id"] = doc.id

            if (
                data.get("created_at")
                and hasattr(
                    data["created_at"],
                    "isoformat",
                )
            ):
                data["created_at"] = (
                    data["created_at"].isoformat()
                )

            logs.append(data)

        return jsonify({
            "success": True,
            "count": len(logs),
            "data": logs,
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 500