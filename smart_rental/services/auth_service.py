from functools import wraps

from flask import request, jsonify
from firebase_admin import auth


def require_auth(func):
    """
    Xác thực Firebase ID Token.

    Client phải gửi:
        Authorization: Bearer <firebase_id_token>

    Sau khi verify thành công:
        request.current_user = decoded Firebase token
    """

    @wraps(func)
    def wrapper(*args, **kwargs):

        auth_header = request.headers.get("Authorization", "")

        if not auth_header:
            return jsonify({
                "success": False,
                "message": "Missing Authorization header"
            }), 401

        if not auth_header.startswith("Bearer "):
            return jsonify({
                "success": False,
                "message": "Invalid Authorization header"
            }), 401

        id_token = auth_header[len("Bearer "):].strip()

        if not id_token:
            return jsonify({
                "success": False,
                "message": "Missing Firebase ID token"
            }), 401

        try:
            decoded_token = auth.verify_id_token(id_token)

            # Firebase UID
            request.current_user = decoded_token

            return func(*args, **kwargs)

        except auth.ExpiredIdTokenError:
            return jsonify({
                "success": False,
                "message": "Firebase ID token has expired"
            }), 401

        except auth.InvalidIdTokenError:
            return jsonify({
                "success": False,
                "message": "Invalid Firebase ID token"
            }), 401

        except Exception as e:
            print("[AUTH ERROR]", e)

            return jsonify({
                "success": False,
                "message": "Authentication failed"
            }), 401

    return wrapper


def require_landlord(func):
    """
    Chỉ cho phép Firebase user có:
        role = landlord
    """

    @wraps(func)
    @require_auth
    def wrapper(*args, **kwargs):

        user = request.current_user

        role = user.get("role")

        if role != "landlord":
            return jsonify({
                "success": False,
                "message": "Admin permission required"
            }), 403

        return func(*args, **kwargs)

    return wrapper


def require_tenant(func):
    """
    Chỉ cho phép Firebase user có:
        role = tenant
    """

    @wraps(func)
    @require_auth
    def wrapper(*args, **kwargs):

        user = request.current_user

        role = user.get("role")

        if role != "tenant":
            return jsonify({
                "success": False,
                "message": "Tenant permission required"
            }), 403

        return func(*args, **kwargs)

    return wrapper