from datetime import datetime, timezone

from services.firebase_service import get_firestore
from services.id_service import new_document_ref


firestore_db = get_firestore()


def get_active_contract_by_room(room_id):
    docs = (
        firestore_db
        .collection("contracts")
        .where("room_id", "==", room_id)
        .where("status", "==", "active")
        .limit(1)
        .stream()
    )

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        return data

    return None


def get_active_contract_by_tenant(tenant_id):
    docs = (
        firestore_db
        .collection("contracts")
        .where("tenant_id", "==", tenant_id)
        .where("status", "==", "active")
        .limit(1)
        .stream()
    )

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        return data

    return None


def build_tenant_snapshot(tenant_doc):
    tenant = tenant_doc.to_dict() or {}
    return {
        "id": tenant_doc.id,
        "name": tenant.get("name"),
        "email": tenant.get("email"),
        "phone": tenant.get("phone"),
        "identity_number": tenant.get("identity_number"),
        "address": tenant.get("address"),
    }


def get_tenant_snapshot(contract_data):
    """Return historical tenant data, falling back to the live tenant for legacy contracts."""
    snapshot = contract_data.get("tenant_snapshot")
    if isinstance(snapshot, dict) and snapshot.get("name"):
        return snapshot

    tenant_id = contract_data.get("tenant_id")
    if tenant_id:
        doc = firestore_db.collection("tenants").document(str(tenant_id)).get()
        if doc.exists:
            return build_tenant_snapshot(doc)

    return None


def create_contract(data):
    room_id = str(data.get("room_id") or "").strip()
    tenant_id = str(data.get("tenant_id") or "").strip()
    monthly_rent = data.get("monthly_rent", data.get("rent_amount", 0))

    if not room_id:
        raise ValueError("room_id is required")
    if not tenant_id:
        raise ValueError("tenant_id is required")
    if not data.get("start_date"):
        raise ValueError("start_date is required")

    try:
        monthly_rent = float(monthly_rent)
    except (TypeError, ValueError):
        raise ValueError("monthly_rent must be a number")
    if monthly_rent < 0:
        raise ValueError("monthly_rent cannot be negative")

    room_doc = firestore_db.collection("rooms").document(room_id).get()
    if not room_doc.exists:
        raise ValueError("Room not found")

    tenant_doc = firestore_db.collection("tenants").document(tenant_id).get()
    if not tenant_doc.exists:
        raise ValueError("Tenant not found")

    if get_active_contract_by_room(room_id):
        raise ValueError("Room already has an active contract")

    now = datetime.now(timezone.utc)
    tenant_snapshot = build_tenant_snapshot(tenant_doc)

    contract_data = {
        "room_id": room_id,
        "tenant_id": tenant_id,
        "tenant_snapshot": tenant_snapshot,
        "start_date": data.get("start_date"),
        "end_date": data.get("end_date"),
        "monthly_rent": monthly_rent,
        "deposit": float(data.get("deposit", 0) or 0),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }

    # Firestore generates the contract ID.
    contract_ref = new_document_ref("contracts")
    contract_ref.set(contract_data)

    contract_data["id"] = contract_ref.id
    update_room_status(room_id, tenant_id)
    return contract_data


def update_contract(contract_id, data):
    contract_ref = firestore_db.collection("contracts").document(str(contract_id))
    contract_doc = contract_ref.get()

    if not contract_doc.exists:
        return None

    current = contract_doc.to_dict() or {}
    old_room_id = current.get("room_id")
    update_data = {}

    if "room_id" in data:
        room_id = str(data.get("room_id") or "").strip()
        if not room_id:
            raise ValueError("room_id cannot be empty")
        if not firestore_db.collection("rooms").document(room_id).get().exists:
            raise ValueError("Room not found")
        if room_id != current.get("room_id") and current.get("status") == "active":
            existing = get_active_contract_by_room(room_id)
            if existing and existing.get("id") != str(contract_id):
                raise ValueError("Room already has an active contract")
        update_data["room_id"] = room_id

    if "tenant_id" in data:
        tenant_id = str(data.get("tenant_id") or "").strip()
        if not tenant_id:
            raise ValueError("tenant_id cannot be empty")
        new_tenant_doc = firestore_db.collection("tenants").document(tenant_id).get()
        if not new_tenant_doc.exists:
            raise ValueError("Tenant not found")
        update_data["tenant_id"] = tenant_id
        update_data["tenant_snapshot"] = build_tenant_snapshot(new_tenant_doc)

    if "monthly_rent" in data or "rent_amount" in data:
        value = data.get("monthly_rent", data.get("rent_amount"))
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError("monthly_rent must be a number")
        if value < 0:
            raise ValueError("monthly_rent cannot be negative")
        update_data["monthly_rent"] = value

    if "deposit" in data:
        try:
            update_data["deposit"] = float(data.get("deposit") or 0)
        except (TypeError, ValueError):
            raise ValueError("deposit must be a number")

    for field in ("start_date", "end_date"):
        if field in data:
            update_data[field] = data.get(field)

    if "status" in data:
        status = data.get("status")
        if status not in ("active", "ended", "cancelled"):
            raise ValueError("status must be active, ended or cancelled")
        update_data["status"] = status

    update_data.pop("id", None)
    update_data.pop("contract_id", None)
    update_data["updated_at"] = datetime.now(timezone.utc)
    contract_ref.update(update_data)

    updated = contract_ref.get().to_dict() or {}
    updated["id"] = contract_ref.id

    # Keep room occupancy synchronized when room/tenant/status changes.
    room_id = updated.get("room_id")
    tenant_id = updated.get("tenant_id")
    if updated.get("status") == "active" and room_id and tenant_id:
        if old_room_id and old_room_id != room_id:
            clear_room_status(old_room_id)
        update_room_status(room_id, tenant_id)
    elif room_id:
        clear_room_status(room_id)

    return updated


def update_room_status(room_id, tenant_id):
    room_ref = (
        firestore_db
        .collection("rooms")
        .document(room_id)
    )

    room_ref.update({
        "tenant_id": tenant_id,
        "status": "occupied",
        "updated_at": datetime.now(timezone.utc)
    })


def clear_room_status(room_id):
    room_ref = (
        firestore_db
        .collection("rooms")
        .document(room_id)
    )

    room_ref.update({
        "tenant_id": None,
        "status": "available",
        "updated_at": datetime.now(timezone.utc)
    })


def get_all_contracts(status=None):
    query = firestore_db.collection("contracts")

    if status:
        query = query.where("status", "==", status)

    docs = (
        query
        .order_by("created_at", direction="DESCENDING")
        .stream()
    )

    contracts = []

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id

        # Keep contract history readable even after the tenant document is deleted.
        snapshot = get_tenant_snapshot(data)
        if snapshot:
            data["tenant_snapshot"] = snapshot
            data["tenant_name"] = snapshot.get("name")
            data["tenant_email"] = snapshot.get("email")

        contracts.append(data)

    return contracts


def get_contract_by_id(contract_id):
    doc = (
        firestore_db
        .collection("contracts")
        .document(contract_id)
        .get()
    )

    if not doc.exists:
        return None

    data = doc.to_dict()
    data["id"] = doc.id

    return data


def end_contract(contract_id):
    contract_ref = (
        firestore_db
        .collection("contracts")
        .document(contract_id)
    )

    contract_doc = contract_ref.get()

    if not contract_doc.exists:
        return None

    contract_data = contract_doc.to_dict()

    if contract_data.get("status") != "active":
        raise ValueError("Contract is not active")

    # A contract may only end after every invoice belonging to it has been paid
    # (cancelled invoices are not outstanding).
    room_id = contract_data.get("room_id")
    outstanding_bills = []
    if room_id:
        bills = (
            firestore_db.collection("rooms")
            .document(str(room_id))
            .collection("bills")
            .stream()
        )
        for bill_doc in bills:
            bill = bill_doc.to_dict() or {}
            if bill.get("contract_id") != str(contract_id):
                continue
            if bill.get("status", "unpaid") == "unpaid":
                outstanding_bills.append(bill_doc.id)

    if outstanding_bills:
        raise ValueError(
            f"Không thể kết thúc hợp đồng vì còn {len(outstanding_bills)} hóa đơn chưa thanh toán."
        )

    contract_ref.update({
        "status": "ended",
        "updated_at": datetime.now(timezone.utc)
    })

    clear_room_status(
        contract_data.get("room_id")
    )

    updated_doc = contract_ref.get()

    result = updated_doc.to_dict()
    result["id"] = updated_doc.id

    return result


def cancel_contract(contract_id):
    contract_ref = (
        firestore_db
        .collection("contracts")
        .document(contract_id)
    )

    contract_doc = contract_ref.get()

    if not contract_doc.exists:
        return None

    contract_data = contract_doc.to_dict()

    if contract_data.get("status") != "active":
        raise ValueError("Contract is not active")

    contract_ref.update({
        "status": "cancelled",
        "updated_at": datetime.now(timezone.utc)
    })

    clear_room_status(
        contract_data.get("room_id")
    )

    updated_doc = contract_ref.get()

    result = updated_doc.to_dict()
    result["id"] = updated_doc.id

    return result