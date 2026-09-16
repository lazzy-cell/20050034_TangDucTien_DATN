from datetime import datetime, timezone

from services.time_service import vn_now

from services.occupancy_service import _resolve_occupancy

from services.firebase_service import get_firestore, get_realtime_db


firestore_db = get_firestore()
realtime_db = get_realtime_db()


def get_rooms_overview():
    rooms = firestore_db.collection("rooms").stream()

    total_rooms = 0
    online_rooms = 0
    offline_rooms = 0
    active_rooms = 0

    try:
        realtime_rooms = realtime_db.child("rooms").get() or {}
    except Exception:
        realtime_rooms = {}

    for room_doc in rooms:
        total_rooms += 1

        room_id = room_doc.id
        realtime_data = realtime_rooms.get(room_id, {})

        online = realtime_data.get("online", False)
        is_active = realtime_data.get("is_active", False)

        if online:
            online_rooms += 1
        else:
            offline_rooms += 1

        if is_active:
            active_rooms += 1

    return {
        "total": total_rooms,
        "online": online_rooms,
        "offline": offline_rooms,
        "active": active_rooms
    }


def get_current_power_overview():
    try:
        realtime_rooms = realtime_db.child("rooms").get() or {}
    except Exception:
        realtime_rooms = {}

    total_power = 0

    for room_id, room_data in realtime_rooms.items():
        power = room_data.get("power", 0) or 0
        total_power += float(power)

    return {
        "current_power": round(total_power, 2)
    }


def get_today_energy_overview():
    today = vn_now().strftime("%Y-%m-%d")

    rooms = firestore_db.collection("rooms").stream()

    total_consumption = 0

    for room_doc in rooms:
        room_id = room_doc.id

        daily_doc = (
            firestore_db
            .collection("rooms")
            .document(room_id)
            .collection("energy_daily")
            .document(today)
            .get()
        )

        if not daily_doc.exists:
            continue

        data = daily_doc.to_dict()

        consumption = data.get("consumption", 0) or 0

        total_consumption += float(consumption)

    return round(total_consumption, 6)


def get_month_energy_overview():
    current_month = vn_now().strftime("%Y-%m")

    rooms = firestore_db.collection("rooms").stream()

    total_consumption = 0

    for room_doc in rooms:
        room_id = room_doc.id

        daily_docs = (
            firestore_db
            .collection("rooms")
            .document(room_id)
            .collection("energy_daily")
            .stream()
        )

        for daily_doc in daily_docs:
            data = daily_doc.to_dict()

            date = data.get("date", "")

            if not date.startswith(current_month):
                continue

            consumption = data.get("consumption", 0) or 0

            total_consumption += float(consumption)

    return round(total_consumption, 6)


def get_billing_overview():
    """Billing KPIs include both active bills and durable terminal history."""
    current_period = vn_now().strftime("%Y-%m")
    bills = []

    for room_doc in firestore_db.collection("rooms").stream():
        bill_doc = (
            room_doc.reference.collection("bills")
            .document(current_period)
            .get()
        )
        if bill_doc.exists:
            bills.append(bill_doc.to_dict() or {})

    for history_doc in firestore_db.collection("bill_history").stream():
        bill = history_doc.to_dict() or {}
        if bill.get("period") == current_period:
            bills.append(bill)

    unpaid_bills = 0
    paid_bills = 0
    cancelled_bills = 0
    unpaid_amount = 0
    estimated_revenue = 0
    cancelled_amount = 0

    for bill in bills:
        total_cost = float(bill.get("total_cost", 0) or 0)
        status = bill.get("status", "unpaid")

        if status == "paid":
            paid_bills += 1
            estimated_revenue += total_cost
        elif status == "unpaid":
            unpaid_bills += 1
            unpaid_amount += total_cost
        elif status == "cancelled":
            cancelled_bills += 1
            cancelled_amount += total_cost

    return {
        "unpaid_bills": unpaid_bills,
        "paid_bills": paid_bills,
        "cancelled_bills": cancelled_bills,
        "estimated_revenue": round(estimated_revenue),
        "unpaid_amount": round(unpaid_amount),
        "cancelled_amount": round(cancelled_amount),
    }


def get_occupancy_overview():
    """Tóm tắt occupancy CV; dữ liệu stale được tính là UNKNOWN."""
    rooms = firestore_db.collection("rooms").stream()
    try:
        realtime_rooms = realtime_db.child("rooms").get() or {}
    except Exception:
        realtime_rooms = {}

    occupied = 0
    vacant = 0
    unknown = 0
    stale = 0
    total = 0
    now_ts = datetime.now(timezone.utc).timestamp()

    for room_doc in rooms:
        total += 1
        room_id = room_doc.id
        room = room_doc.to_dict() or {}
        realtime = realtime_rooms.get(room_id, {}) or {}
        state = _resolve_occupancy(room, realtime, now_ts)

        if state["status"] == "occupied":
            occupied += 1
        elif state["status"] == "vacant":
            vacant += 1
        else:
            unknown += 1

        if state["is_stale"]:
            stale += 1

    return {
        "occupied": occupied,
        "vacant": vacant,
        "unknown": unknown,
        "stale": stale,
        "total": total,
    }

def get_dashboard_overview():
    rooms = get_rooms_overview()
    power = get_current_power_overview()

    today_consumption = get_today_energy_overview()
    month_consumption = get_month_energy_overview()

    billing = get_billing_overview()
    occupancy = get_occupancy_overview()

    room_cards = []
    fs_rooms = firestore_db.collection("rooms").stream()
    try:
        realtime_rooms = realtime_db.child("rooms").get() or {}
    except Exception:
        realtime_rooms = {}

    for room_doc in fs_rooms:
        room_id = room_doc.id
        room = room_doc.to_dict() or {}
        rt = realtime_rooms.get(room_id, {}) or {}
        occ = rt.get("occupancy") or {}

        occupancy_state = _resolve_occupancy(
            room,
            rt,
            datetime.now(timezone.utc).timestamp(),
        )

        room_cards.append({
            "room_id": room_id,
            "room_name": room.get("room_name") or room_id,
            "device_id": room.get("device_id"),
            "online": bool(rt.get("online")),
            "switch": rt.get("switch"),
            "power": rt.get("power", 0),
            "voltage": rt.get("voltage"),
            "current": rt.get("current"),
            "is_active": rt.get("is_active"),
            "occupied": occupancy_state["occupied"],
            "occupancy_status": occupancy_state["status"],
            "person_count": occupancy_state["person_count"],
            "occupancy_updated_at": occupancy_state.get("heartbeat_at"),
            "occupancy_heartbeat_at": occupancy_state.get("heartbeat_at"),
            "occupancy_age_seconds": occupancy_state.get("age_seconds"),
            "occupancy_stale_after_seconds": 120,
            "occupancy_is_stale": occupancy_state["is_stale"],
        })

    return {
        "rooms": rooms,
        "power": power,
        "energy": {
            "today_consumption": today_consumption,
            "month_consumption": month_consumption
        },
        "billing": billing,
        "occupancy": occupancy,
        "room_cards": room_cards,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
