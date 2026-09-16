from datetime import datetime, timezone

from services.time_service import vn_now
from calendar import monthrange

from services.firebase_service import get_firestore
from services.settings_service import get_electricity_price
from services.id_service import new_document_ref


firestore_db = get_firestore()

# Active/unpaid bills live under the room. Once a bill reaches a terminal
# state (paid/cancelled), a complete immutable snapshot is copied here.
BILL_HISTORY_COLLECTION = "bill_history"


def get_month_date_range(period=None):
    if period is None:
        now = vn_now()
        year = now.year
        month = now.month
    else:
        try:
            year, month = map(int, period.split("-"))
            if month < 1 or month > 12:
                raise ValueError
        except ValueError:
            raise ValueError("Period must have format YYYY-MM")

    last_day = monthrange(year, month)[1]
    start_date = datetime(year, month, 1, 0, 0, 0)
    end_date = datetime(year, month, last_day, 23, 59, 59)

    return {
        "period": f"{year:04d}-{month:02d}",
        "start_date": start_date,
        "end_date": end_date
    }


def get_active_contract(room_id):
    docs = (
        firestore_db.collection("contracts")
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


def get_month_consumption(room_id, period=None):
    date_range = get_month_date_range(period)
    target_period = date_range["period"]

    daily_docs = (
        firestore_db.collection("rooms")
        .document(room_id)
        .collection("energy_daily")
        .stream()
    )

    total_consumption = 0
    total_days = 0

    for doc in daily_docs:
        data = doc.to_dict()
        date = data.get("date", "")
        if not date.startswith(target_period):
            continue
        consumption = data.get("consumption", 0) or 0
        total_consumption += float(consumption)
        total_days += 1

    return {
        "period": target_period,
        "start_date": date_range["start_date"].strftime("%Y-%m-%d"),
        "end_date": date_range["end_date"].strftime("%Y-%m-%d"),
        "consumption": round(total_consumption, 6),
        "days_recorded": total_days
    }


def calculate_current_bill(room_id, period=None):
    contract = get_active_contract(room_id)
    if contract is None:
        raise ValueError("Room does not have an active contract")

    consumption_data = get_month_consumption(room_id, period)
    monthly_rent = float(contract.get("monthly_rent", 0) or 0)
    electricity_price = float(get_electricity_price())
    consumption = consumption_data["consumption"]
    electricity_cost = consumption * electricity_price
    total_cost = monthly_rent + electricity_cost

    return {
        "room_id": room_id,
        "contract_id": contract["id"],
        "tenant_id": contract.get("tenant_id"),
        "tenant_snapshot": contract.get("tenant_snapshot"),
        "period": consumption_data["period"],
        "start_date": consumption_data["start_date"],
        "end_date": consumption_data["end_date"],
        "days_recorded": consumption_data["days_recorded"],
        "monthly_rent": round(monthly_rent),
        "consumption": consumption,
        "electricity_price": electricity_price,
        "electricity_cost": round(electricity_cost),
        "total_cost": round(total_cost)
    }


def _room_name(room_id):
    room_doc = firestore_db.collection("rooms").document(room_id).get()
    if not room_doc.exists:
        return room_id
    return (room_doc.to_dict() or {}).get("room_name") or room_id


def _archive_bill(room_id, bill_data, terminal_status, *, payment_id=None):
    """Persist a self-contained historical invoice before removing its room copy."""
    now = datetime.now(timezone.utc)
    history_ref = new_document_ref(BILL_HISTORY_COLLECTION)

    snapshot = dict(bill_data)
    snapshot.update({
        "original_bill_id": bill_data.get("period"),
        "room_id": room_id,
        "room_name": _room_name(room_id),
        "status": terminal_status,
        "status_changed_at": now,
        "archived_at": now,
        "archive_reason": terminal_status,
    })

    if payment_id:
        snapshot["payment_id"] = payment_id

    history_ref.set(snapshot)
    return history_ref.id


def generate_month_bill(room_id, period=None):
    bill_data = calculate_current_bill(room_id, period)

    bill_ref = (
        firestore_db.collection("rooms")
        .document(room_id)
        .collection("bills")
        .document(bill_data["period"])
    )

    existing_bill = bill_ref.get()
    if existing_bill.exists:
        existing_data = existing_bill.to_dict()
        if existing_data.get("status") == "paid":
            raise ValueError("Cannot regenerate a paid bill")
        if existing_data.get("status") == "cancelled":
            raise ValueError("Cannot regenerate a cancelled bill")
        return serialize_bill(existing_data)

    now = datetime.now(timezone.utc)
    bill_data["status"] = "unpaid"
    bill_data["generated_at"] = now
    bill_data["updated_at"] = now
    bill_data["status_changed_at"] = now
    bill_data["room_name"] = _room_name(room_id)

    bill_ref.set(bill_data)

    try:
        from services.notification_service import notify_bill_generated
        notify_bill_generated(
            tenant_id=bill_data.get("tenant_id"),
            room_id=room_id,
            period=bill_data.get("period"),
            total_cost=bill_data.get("total_cost"),
        )
    except Exception as e:
        print(f"Bill push notify failed: {e}")

    return serialize_bill(bill_data)


def get_bill(room_id, period):
    bill_doc = (
        firestore_db.collection("rooms")
        .document(room_id)
        .collection("bills")
        .document(period)
        .get()
    )

    if bill_doc.exists:
        bill_data = bill_doc.to_dict()
        bill_data["id"] = bill_doc.id
        return serialize_bill(bill_data)

    # Terminal invoices are intentionally independent of the room document.
    # Scan the history collection instead of requiring a Firestore composite
    # index for room_id + period.
    for doc in firestore_db.collection(BILL_HISTORY_COLLECTION).stream():
        bill_data = doc.to_dict() or {}
        if bill_data.get("room_id") != room_id or bill_data.get("period") != period:
            continue
        bill_data["id"] = doc.id
        bill_data["archived"] = True
        return serialize_bill(bill_data)

    return None


def update_bill_status(room_id, period, status):
    allowed_statuses = ["unpaid", "paid", "cancelled"]
    if status not in allowed_statuses:
        raise ValueError(f"Status must be one of: {allowed_statuses}")

    bill_ref = (
        firestore_db.collection("rooms")
        .document(room_id)
        .collection("bills")
        .document(period)
    )
    bill_doc = bill_ref.get()

    if not bill_doc.exists:
        # A terminal bill is already archived and cannot be changed again.
        return None

    bill_data = bill_doc.to_dict()
    current_status = bill_data.get("status", "unpaid")

    if current_status in ("paid", "cancelled"):
        raise ValueError(f"Bill is already {current_status} and is immutable")

    if status == "unpaid":
        return serialize_bill(bill_data)

    now = datetime.now(timezone.utc)
    update_data = {
        "status": status,
        "updated_at": now,
        "status_changed_at": now,
    }
    if status == "paid":
        update_data["paid_at"] = now

    bill_ref.update(update_data)

    # Read the final state so the archive is a faithful snapshot.
    final_data = bill_ref.get().to_dict() or bill_data
    payment_id = final_data.get("payment_id")
    _archive_bill(
        room_id,
        final_data,
        status,
        payment_id=payment_id,
    )

    # The active-room copy is no longer the source of truth after a terminal
    # state. The history document is the durable source of truth.
    bill_ref.delete()

    return get_bill(room_id, period)


def serialize_bill(data):
    result = data.copy()
    datetime_fields = [
        "generated_at",
        "updated_at",
        "paid_at",
        "status_changed_at",
        "archived_at",
    ]
    for field in datetime_fields:
        if result.get(field) and hasattr(result[field], "isoformat"):
            result[field] = result[field].isoformat()
    return result
