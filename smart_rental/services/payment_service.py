from datetime import datetime, timezone

from services.firebase_service import get_firestore
from services.id_service import new_document_ref
from services.billing_service import update_bill_status


firestore_db = get_firestore()


def serialize_payment(data):
    result = data.copy()

    datetime_fields = [
        "paid_at",
        "created_at",
        "updated_at"
    ]

    for field in datetime_fields:
        if result.get(field):
            result[field] = result[field].isoformat()

    return result


def get_bill_reference(room_id, period):
    return (
        firestore_db
        .collection("rooms")
        .document(room_id)
        .collection("bills")
        .document(period)
    )


def create_payment(room_id, period, payment_method):
    allowed_methods = [
        "cash",
        "bank_transfer",
        "other"
    ]

    if payment_method not in allowed_methods:
        raise ValueError(
            f"Payment method must be one of: {allowed_methods}"
        )

    bill_ref = get_bill_reference(room_id, period)
    bill_doc = bill_ref.get()

    if not bill_doc.exists:
        raise ValueError("Bill not found")

    bill_data = bill_doc.to_dict()

    bill_status = bill_data.get("status")

    if bill_status == "paid":
        raise ValueError("Bill has already been paid")

    if bill_status == "cancelled":
        raise ValueError("Cannot pay a cancelled bill")

    now = datetime.now(timezone.utc)

    room_doc = firestore_db.collection("rooms").document(room_id).get()
    room_name = (
        (room_doc.to_dict() or {}).get("room_name")
        if room_doc.exists else None
    ) or bill_data.get("room_name") or room_id

    payment_data = {
        "room_id": room_id,
        "room_name": room_name,
        "period": period,

        "contract_id": bill_data.get("contract_id"),
        "tenant_id": bill_data.get("tenant_id"),

        "amount": bill_data.get("total_cost", 0),

        "payment_method": payment_method,
        "status": "completed",

        "paid_at": now,
        "created_at": now,
        "updated_at": now
    }

    payment_ref = new_document_ref("payments")
    payment_ref.set(payment_data)

    # Attach the payment to the bill first, then let billing_service perform
    # the terminal-state transition and durable archival.
    bill_ref.update({
        "payment_id": payment_ref.id
    })
    update_bill_status(room_id, period, "paid")

    payment_data["id"] = payment_ref.id

    print(
        f"Payment completed: "
        f"{room_id} - {period} - "
        f"{payment_data['amount']}"
    )

    return serialize_payment(payment_data)


def get_payment(payment_id):
    payment_doc = (
        firestore_db
        .collection("payments")
        .document(payment_id)
        .get()
    )

    if not payment_doc.exists:
        return None

    payment_data = payment_doc.to_dict()
    payment_data["id"] = payment_doc.id

    return serialize_payment(payment_data)


def get_all_payments(room_id=None, tenant_id=None):
    query = firestore_db.collection("payments")

    if room_id:
        query = query.where(
            "room_id",
            "==",
            room_id
        )

    if tenant_id:
        query = query.where(
            "tenant_id",
            "==",
            tenant_id
        )

    docs = (
        query
        .order_by(
            "paid_at",
            direction="DESCENDING"
        )
        .stream()
    )

    payments = []

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id

        payments.append(
            serialize_payment(data)
        )

    return payments


def get_room_payments(room_id):
    return get_all_payments(room_id=room_id)