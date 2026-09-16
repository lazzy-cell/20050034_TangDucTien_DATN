from datetime import datetime, timezone

from firebase_admin import auth

from services.firebase_service import get_firestore
from services.id_service import new_document_ref


firestore_db = get_firestore()


def create_user(data):
    """
    Tạo landlord/user mới bằng Firebase Authentication.

    Không lưu password hoặc password_hash vào Firestore.

    Firestore collection:
        users/{document_id}

    Firebase Authentication:
        email
        password
        display_name

    Custom claims:
        role = landlord
    """

    name = (data.get("name") or data.get("display_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name:
        raise ValueError("Name is required")

    if not email:
        raise ValueError("Email is required")

    if not password:
        raise ValueError("Password is required")

    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")

    firebase_user = None

    try:
        # Kiểm tra email đã tồn tại hay chưa.
        try:
            existing_user = auth.get_user_by_email(email)

            if existing_user:
                raise ValueError("Email is already registered")

        except auth.UserNotFoundError:
            pass

        # Tạo user trong Firebase Authentication.
        firebase_user = auth.create_user(
            email=email,
            password=password,
            display_name=name,
        )

        # Gán role landlord.
        auth.set_custom_user_claims(
            firebase_user.uid,
            {
                "role": "landlord",
            },
        )

        now = datetime.now(timezone.utc)

        user_data = {
            "auth_uid": firebase_user.uid,
            "name": name,
            "display_name": name,
            "email": email,
            "role": "landlord",
            "status": data.get("status", "active"),
            "phone": data.get("phone"),
            "created_at": now,
            "updated_at": now,
        }

        # Không lưu password/password_hash.
        user_data.pop("password", None)
        user_data.pop("password_hash", None)

        user_ref = new_document_ref("users")
        user_ref.set(user_data)

        user_data["id"] = user_ref.id

        return user_data

    except ValueError:
        if firebase_user:
            try:
                auth.delete_user(firebase_user.uid)
            except Exception:
                pass

        raise

    except auth.EmailAlreadyExistsError:
        raise ValueError("Email is already registered")

    except Exception:
        # Nếu Firebase Auth tạo thành công nhưng Firestore thất bại,
        # xóa Firebase user để tránh tạo user mồ côi.
        if firebase_user:
            try:
                auth.delete_user(firebase_user.uid)
            except Exception:
                pass

        raise


def get_all_users():
    """
    Lấy toàn bộ landlord/user từ Firestore.
    """

    docs = (
        firestore_db
        .collection("users")
        .order_by(
            "created_at",
            direction="DESCENDING",
        )
        .stream()
    )

    users = []

    for doc in docs:
        data = doc.to_dict() or {}

        data["id"] = doc.id

        if data.get("created_at"):
            data["created_at"] = (
                data["created_at"].isoformat()
            )

        if data.get("updated_at"):
            data["updated_at"] = (
                data["updated_at"].isoformat()
            )

        # Đảm bảo không bao giờ trả password
        # hoặc password_hash về frontend.
        data.pop("password", None)
        data.pop("password_hash", None)

        users.append(data)

    return users


def get_user_by_id(user_id):
    """
    Lấy user theo Firestore document ID.
    """

    if not user_id:
        return None

    user_ref = (
        firestore_db
        .collection("users")
        .document(user_id)
    )

    user_doc = user_ref.get()

    if not user_doc.exists:
        return None

    data = user_doc.to_dict() or {}

    data["id"] = user_doc.id

    if data.get("created_at"):
        data["created_at"] = (
            data["created_at"].isoformat()
        )

    if data.get("updated_at"):
        data["updated_at"] = (
            data["updated_at"].isoformat()
        )

    data.pop("password", None)
    data.pop("password_hash", None)

    return data


def get_user_by_auth_uid(auth_uid):
    """
    Lấy user theo Firebase Authentication UID.
    """

    if not auth_uid:
        return None

    docs = (
        firestore_db
        .collection("users")
        .where(
            "auth_uid",
            "==",
            auth_uid,
        )
        .limit(1)
        .stream()
    )

    for doc in docs:
        data = doc.to_dict() or {}

        data["id"] = doc.id

        if data.get("created_at"):
            data["created_at"] = (
                data["created_at"].isoformat()
            )

        if data.get("updated_at"):
            data["updated_at"] = (
                data["updated_at"].isoformat()
            )

        data.pop("password", None)
        data.pop("password_hash", None)

        return data

    return None


def get_user_by_email(email):
    """
    Lấy user theo email trong Firestore.
    """

    email = (email or "").strip().lower()

    if not email:
        return None

    docs = (
        firestore_db
        .collection("users")
        .where(
            "email",
            "==",
            email,
        )
        .limit(1)
        .stream()
    )

    for doc in docs:
        data = doc.to_dict() or {}

        data["id"] = doc.id

        if data.get("created_at"):
            data["created_at"] = (
                data["created_at"].isoformat()
            )

        if data.get("updated_at"):
            data["updated_at"] = (
                data["updated_at"].isoformat()
            )

        data.pop("password", None)
        data.pop("password_hash", None)

        return data

    return None


def update_user(user_id, data):
    """
    Cập nhật thông tin landlord/user.

    Các trường được phép cập nhật:
        name
        display_name
        email
        phone
        status

    Email được cập nhật đồng thời trong:
        Firebase Authentication
        Firestore

    Không cho phép cập nhật password trực tiếp ở đây.
    """

    if not user_id:
        raise ValueError("User ID is required")

    user_ref = (
        firestore_db
        .collection("users")
        .document(user_id)
    )

    user_doc = user_ref.get()

    if not user_doc.exists:
        raise ValueError("User not found")

    current_data = user_doc.to_dict() or {}

    auth_uid = current_data.get("auth_uid")

    if not auth_uid:
        raise ValueError(
            "User does not have Firebase Authentication UID"
        )

    update_data = {}

    if "name" in data:
        name = (data.get("name") or "").strip()

        if not name:
            raise ValueError("Name cannot be empty")

        update_data["name"] = name
        update_data["display_name"] = name

    elif "display_name" in data:
        display_name = (
            data.get("display_name") or ""
        ).strip()

        if not display_name:
            raise ValueError(
                "Display name cannot be empty"
            )

        update_data["display_name"] = display_name

    if "email" in data:
        email = (
            data.get("email") or ""
        ).strip().lower()

        if not email:
            raise ValueError("Email cannot be empty")

        old_email = (
            current_data.get("email") or ""
        ).strip().lower()

        if email != old_email:
            try:
                auth.update_user(
                    auth_uid,
                    email=email,
                )
            except auth.EmailAlreadyExistsError:
                raise ValueError(
                    "Email is already registered"
                )

            update_data["email"] = email

    if "phone" in data:
        update_data["phone"] = data.get("phone")

    if "status" in data:
        status = data.get("status")

        if status not in (
            "active",
            "inactive",
        ):
            raise ValueError(
                "status must be active or inactive"
            )

        update_data["status"] = status

    if not update_data:
        return get_user_by_id(user_id)

    update_data["updated_at"] = datetime.now(timezone.utc)

    # Tuyệt đối không lưu password.
    update_data.pop("password", None)
    update_data.pop("password_hash", None)

    user_ref.update(update_data)

    # Đồng bộ display name với Firebase Authentication.
    firebase_update = {}

    if "name" in update_data:
        firebase_update["display_name"] = (
            update_data["name"]
        )
    elif "display_name" in update_data:
        firebase_update["display_name"] = (
            update_data["display_name"]
        )

    if firebase_update:
        auth.update_user(
            auth_uid,
            **firebase_update,
        )

    return get_user_by_id(user_id)


def update_user_status(user_id, status):
    """
    Bật/tắt tài khoản landlord.

    status:
        active
        inactive

    Khi inactive:
        Firebase Authentication user sẽ bị disabled.

    Khi active:
        Firebase Authentication user sẽ được enable lại.
    """

    if status not in (
        "active",
        "inactive",
    ):
        raise ValueError(
            "status must be active or inactive"
        )

    user_ref = (
        firestore_db
        .collection("users")
        .document(user_id)
    )

    user_doc = user_ref.get()

    if not user_doc.exists:
        raise ValueError("User not found")

    user_data = user_doc.to_dict() or {}

    auth_uid = user_data.get("auth_uid")

    if not auth_uid:
        raise ValueError(
            "User does not have Firebase Authentication UID"
        )

    disabled = status == "inactive"

    auth.update_user(
        auth_uid,
        disabled=disabled,
    )

    user_ref.update({
        "status": status,
        "updated_at": datetime.now(timezone.utc),
    })

    return get_user_by_id(user_id)


def reset_user_password(user_id, new_password):
    """
    Reset password cho landlord/user thông qua Firebase Authentication.

    Password không được lưu vào Firestore.
    """

    if not user_id:
        raise ValueError("User ID is required")

    if not new_password:
        raise ValueError("New password is required")

    if len(new_password) < 6:
        raise ValueError(
            "Password must be at least 6 characters"
        )

    user_ref = (
        firestore_db
        .collection("users")
        .document(user_id)
    )

    user_doc = user_ref.get()

    if not user_doc.exists:
        raise ValueError("User not found")

    user_data = user_doc.to_dict() or {}

    auth_uid = user_data.get("auth_uid")

    if not auth_uid:
        raise ValueError(
            "User does not have Firebase Authentication UID"
        )

    auth.update_user(
        auth_uid,
        password=new_password,
    )

    user_ref.update({
        "updated_at": datetime.now(timezone.utc),
    })

    return {
        "success": True,
        "message": "Password updated successfully",
    }


def delete_user(user_id):
    """
    Xóa landlord/user khỏi:

    1. Firebase Authentication
    2. Firestore users collection
    """

    if not user_id:
        raise ValueError("User ID is required")

    user_ref = (
        firestore_db
        .collection("users")
        .document(user_id)
    )

    user_doc = user_ref.get()

    if not user_doc.exists:
        raise ValueError("User not found")

    user_data = user_doc.to_dict() or {}

    auth_uid = user_data.get("auth_uid")

    # Xóa Firebase Authentication user trước.
    if auth_uid:
        try:
            auth.delete_user(auth_uid)
        except auth.UserNotFoundError:
            # Firebase user đã bị xóa trước đó,
            # vẫn tiếp tục xóa Firestore document.
            pass

    # Xóa Firestore document.
    user_ref.delete()

    return {
        "success": True,
        "message": "User deleted successfully",
    }


def get_firebase_user(auth_uid):
    """
    Lấy trực tiếp Firebase Authentication user
    theo Firebase UID.
    """

    if not auth_uid:
        return None

    try:
        return auth.get_user(auth_uid)
    except auth.UserNotFoundError:
        return None


def set_user_role(user_id, role):
    """
    Thay đổi Firebase custom claim role.

    Hiện tại hệ thống chỉ cho phép:
        landlord
        tenant

    user_service chủ yếu quản lý landlord,
    nhưng function này cho phép đồng bộ role
    với Firebase Authentication.
    """

    allowed_roles = (
        "landlord",
        "tenant",
    )

    if role not in allowed_roles:
        raise ValueError(
            "role must be landlord or tenant"
        )

    user_ref = (
        firestore_db
        .collection("users")
        .document(user_id)
    )

    user_doc = user_ref.get()

    if not user_doc.exists:
        raise ValueError("User not found")

    user_data = user_doc.to_dict() or {}

    auth_uid = user_data.get("auth_uid")

    if not auth_uid:
        raise ValueError(
            "User does not have Firebase Authentication UID"
        )

    auth.set_custom_user_claims(
        auth_uid,
        {
            "role": role,
        },
    )

    user_ref.update({
        "role": role,
        "updated_at": datetime.now(timezone.utc),
    })

    return get_user_by_id(user_id)