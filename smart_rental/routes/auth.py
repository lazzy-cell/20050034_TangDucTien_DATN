from flask import Blueprint, request, jsonify

from firebase_admin import auth

from services.auth_service import require_auth, require_landlord
from services.user_service import get_all_users, create_user


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/auth/me", methods=["GET"])
@require_auth
def me():
    """
    Trả thông tin user hiện đang đăng nhập.

    Identity lấy từ Firebase ID Token.
    """

    user = request.current_user

    return jsonify({
        "success": True,
        "data": {
            "uid": user.get("uid"),
            "email": user.get("email"),
            "display_name": user.get("name"),
            "role": user.get("role"),
        },
    })


@auth_bp.route("/api/auth/users", methods=["GET"])
@require_landlord
def api_list_users():

    return jsonify({
        "success": True,
        "data": get_all_users()
    })


@auth_bp.route("/api/auth/users", methods=["POST"])
@require_landlord
def api_create_user():

    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    display_name = (
        data.get("display_name")
        or "Chủ trọ"
    )

    if not email:
        return jsonify({
            "success": False,
            "message": "email is required"
        }), 400

    if not password:
        return jsonify({
            "success": False,
            "message": "password is required"
        }), 400

    try:

        user = create_user({
            "email": email,
            "password": password,
            "display_name": display_name,
        })

        return jsonify({
            "success": True,
            "data": user
        }), 201

    except ValueError as e:

        return jsonify({
            "success": False,
            "message": str(e)
        }), 400


@auth_bp.route("/api/auth/logout", methods=["POST"])

def logout():

    # Firebase logout thực hiện ở client.
    # Backend không cần tạo/xóa session.

    return jsonify({
        "success": True,
        "message": "Logout handled by Firebase client"
    })