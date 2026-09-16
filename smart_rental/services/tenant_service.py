from datetime import datetime, timezone
import secrets
import string

from firebase_admin import auth

from services.firebase_service import get_firestore
from services.id_service import new_document_ref


firestore_db = get_firestore()


def generate_temporary_password(length: int = 12) -> str:
    """Generate a strong temporary password; never persist it in Firestore."""
    if length < 8:
        length = 8
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    # Guarantee at least one character from each useful class.
    password = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%"),
    ]
    password.extend(secrets.choice(alphabet) for _ in range(length - 4))
    secrets.SystemRandom().shuffle(password)
    return "".join(password)


def _serialize_tenant(doc):
    data = doc.to_dict() or {}
    data["id"] = doc.id
    for field in ("created_at", "updated_at"):
        if hasattr(data.get(field), "isoformat"):
            data[field] = data[field].isoformat()
    data.pop("password", None)
    data.pop("password_hash", None)
    return data


def create_tenant(data):
    """Create tenant profile + Firebase account using a server-generated password."""
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()

    if not name:
        raise ValueError("Name is required")
    if not email:
        raise ValueError("Email is required")

    # Firebase Auth is the source of truth for credentials.
    try:
        auth.get_user_by_email(email)
        raise ValueError("Email is already registered")
    except auth.UserNotFoundError:
        pass

    temporary_password = generate_temporary_password()
    firebase_user = None

    try:
        firebase_user = auth.create_user(
            email=email,
            password=temporary_password,
            display_name=name,
        )

        auth.set_custom_user_claims(
            firebase_user.uid,
            {
                "role": "tenant",
                "must_change_password": True,
            },
        )

        status = data.get("status", "active")
        if status not in ("active", "inactive"):
            raise ValueError("status must be active or inactive")
        if status == "inactive":
            auth.update_user(firebase_user.uid, disabled=True)

        now = datetime.now(timezone.utc)
        tenant_data = {
            "name": name,
            "phone": data.get("phone"),
            "email": email,
            "identity_number": data.get("identity_number"),
            "address": data.get("address"),
            "status": status,
            "auth_uid": firebase_user.uid,
            "must_change_password": True,
            "created_at": now,
            "updated_at": now,
        }

        # Firestore generates the tenant ID; the client never supplies it.
        tenant_ref = new_document_ref("tenants")
        tenant_ref.set(tenant_data)

        # Never expose the generated bootstrap password. The tenant receives
        # a Firebase password-reset email from the dashboard immediately after creation.
        return _serialize_tenant(tenant_ref.get())

    except ValueError:
        if firebase_user:
            try:
                auth.delete_user(firebase_user.uid)
            except Exception:
                pass
        raise
    except auth.EmailAlreadyExistsError:
        if firebase_user:
            try:
                auth.delete_user(firebase_user.uid)
            except Exception:
                pass
        raise ValueError("Email is already registered")
    except Exception:
        if firebase_user:
            try:
                auth.delete_user(firebase_user.uid)
            except Exception:
                pass
        raise


def get_all_tenants():
    return [_serialize_tenant(doc) for doc in firestore_db.collection("tenants").order_by("created_at", direction="DESCENDING").stream()]


def get_tenant_by_id(tenant_id):
    if not tenant_id:
        return None
    doc = firestore_db.collection("tenants").document(str(tenant_id)).get()
    return _serialize_tenant(doc) if doc.exists else None


def get_tenant_by_auth_uid(auth_uid):
    if not auth_uid:
        return None
    docs = firestore_db.collection("tenants").where("auth_uid", "==", auth_uid).limit(1).stream()
    for doc in docs:
        return _serialize_tenant(doc)
    return None


def update_tenant(tenant_id, data):
    tenant_ref = firestore_db.collection("tenants").document(str(tenant_id))
    tenant_doc = tenant_ref.get()
    if not tenant_doc.exists:
        return None

    tenant = tenant_doc.to_dict() or {}
    auth_uid = tenant.get("auth_uid")
    update_data = {}

    for field in ("name", "phone", "identity_number", "address"):
        if field in data:
            update_data[field] = data[field]

    if "name" in data:
        update_data["name"] = (data.get("name") or "").strip()
        if not update_data["name"]:
            raise ValueError("Name cannot be empty")

    if "email" in data:
        email = (data.get("email") or "").strip().lower()
        if not email:
            raise ValueError("Email cannot be empty")
        if not auth_uid:
            raise ValueError("Tenant does not have Firebase auth UID")
        old_email = (tenant.get("email") or "").strip().lower()
        if email != old_email:
            try:
                existing = auth.get_user_by_email(email)
                if existing.uid != auth_uid:
                    raise ValueError("Email is already registered")
            except auth.UserNotFoundError:
                pass
            auth.update_user(auth_uid, email=email)
        update_data["email"] = email

    if "status" in data:
        status = data.get("status")
        if status not in ("active", "inactive"):
            raise ValueError("status must be active or inactive")
        update_data["status"] = status
        if auth_uid:
            auth.update_user(auth_uid, disabled=(status == "inactive"))

    update_data.pop("password", None)
    update_data.pop("password_hash", None)
    update_data["updated_at"] = datetime.now(timezone.utc)
    tenant_ref.update(update_data)
    return _serialize_tenant(tenant_ref.get())


def reset_tenant_password(tenant_id, new_password):
    if not new_password or len(new_password) < 6:
        raise ValueError("Password must be at least 6 characters")

    tenant_ref = firestore_db.collection("tenants").document(str(tenant_id))
    tenant_doc = tenant_ref.get()
    if not tenant_doc.exists:
        raise ValueError("Tenant not found")

    auth_uid = (tenant_doc.to_dict() or {}).get("auth_uid")
    if not auth_uid:
        raise ValueError("Tenant does not have Firebase auth UID")

    auth.update_user(auth_uid, password=new_password)
    auth.set_custom_user_claims(auth_uid, {"role": "tenant", "must_change_password": False})
    tenant_ref.update({"must_change_password": False, "updated_at": datetime.now(timezone.utc)})
    return True


def complete_tenant_password_setup(auth_uid):
    tenant = get_tenant_by_auth_uid(auth_uid)
    if not tenant:
        raise ValueError("Tenant not found")

    firestore_db.collection("tenants").document(tenant["id"]).update({
        "must_change_password": False,
        "updated_at": datetime.now(timezone.utc),
    })
    auth.set_custom_user_claims(
        auth_uid,
        {"role": "tenant", "must_change_password": False},
    )
    return get_tenant_by_id(tenant["id"])


def delete_tenant(tenant_id):
    tenant_ref = firestore_db.collection("tenants").document(str(tenant_id))
    tenant_doc = tenant_ref.get()
    if not tenant_doc.exists:
        return False

    tenant = tenant_doc.to_dict() or {}

    # A tenant can only be physically deleted after every active contract
    # referencing this tenant has ended/cancelled. Historical contracts keep
    # their own tenant snapshot, so deleting an inactive tenant does not erase
    # the tenant information displayed by those contracts.
    active_contracts = list(
        firestore_db.collection("contracts")
        .where("tenant_id", "==", str(tenant_id))
        .where("status", "==", "active")
        .limit(1)
        .stream()
    )
    if active_contracts:
        raise ValueError(
            "Không thể xóa khách thuê vì khách vẫn đang gắn với hợp đồng còn hiệu lực."
        )

    # Freeze the tenant's data into every historical contract before removing
    # the tenant master record. This also migrates older contracts that did not
    # have tenant_snapshot yet.
    tenant_snapshot = {
        "id": str(tenant_id),
        "name": tenant.get("name"),
        "email": tenant.get("email"),
        "phone": tenant.get("phone"),
        "identity_number": tenant.get("identity_number"),
        "address": tenant.get("address"),
    }
    for contract_doc in (
        firestore_db.collection("contracts")
        .where("tenant_id", "==", str(tenant_id))
        .stream()
    ):
        contract_data = contract_doc.to_dict() or {}
        if not contract_data.get("tenant_snapshot"):
            contract_doc.reference.update({
                "tenant_snapshot": tenant_snapshot,
                "updated_at": datetime.now(timezone.utc),
            })

    auth_uid = tenant.get("auth_uid")
    if auth_uid:
        try:
            auth.delete_user(auth_uid)
        except auth.UserNotFoundError:
            pass

    tenant_ref.delete()
    return True
