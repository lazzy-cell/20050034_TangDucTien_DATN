from datetime import datetime, timezone

from services.time_service import vn_now

from services.firebase_service import get_firestore


firestore_db = get_firestore()


def get_energy_history_by_range(room_id, start_time, end_time):
    docs = (
        firestore_db
        .collection("rooms")
        .document(room_id)
        .collection("energy_history")
        .where("timestamp", ">=", start_time)
        .where("timestamp", "<=", end_time)
        .order_by("timestamp")
        .stream()
    )

    history = []

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id

        if "timestamp" in data and data["timestamp"]:
            data["timestamp"] = data["timestamp"].isoformat()

        history.append(data)

    return history


def calculate_energy_consumption(history):
    if len(history) < 2:
        return {
            "start_energy": 0,
            "end_energy": 0,
            "consumption": 0
        }

    start_energy = history[0].get("total_energy", 0)
    end_energy = history[-1].get("total_energy", 0)

    consumption = end_energy - start_energy

    # Tránh trường hợp dữ liệu bị reset
    if consumption < 0:
        consumption = 0

    return {
        "start_energy": round(start_energy, 6),
        "end_energy": round(end_energy, 6),
        "consumption": round(consumption, 6)
    }


def get_today_analytics(room_id):
    now = vn_now()

    start_time = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    end_time = now

    history = get_energy_history_by_range(
        room_id,
        start_time,
        end_time
    )

    result = calculate_energy_consumption(history)

    return {
        "room_id": room_id,
        "date": now.strftime("%Y-%m-%d"),
        **result
    }


def get_month_analytics(room_id):
    now = vn_now()

    start_time = now.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    end_time = now

    history = get_energy_history_by_range(
        room_id,
        start_time,
        end_time
    )

    result = calculate_energy_consumption(history)

    return {
        "room_id": room_id,
        "month": now.strftime("%Y-%m"),
        **result
    }

# ---------------------------------------------------------------------------
# Dashboard analytics: day / week / month / year
# ---------------------------------------------------------------------------
from calendar import monthrange
from datetime import timedelta


def _dt(value):
    if hasattr(value, "year"):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _period_bounds(granularity, anchor=None):
    now = vn_now()
    anchor = anchor or now.strftime("%Y-%m-%d")
    try:
        if granularity == "day":
            start = datetime.strptime(anchor[:10], "%Y-%m-%d")
            end = start + timedelta(days=1) - timedelta(microseconds=1)
        elif granularity == "week":
            start_day = datetime.strptime(anchor[:10], "%Y-%m-%d")
            start = start_day - timedelta(days=start_day.weekday())
            end = start + timedelta(days=7) - timedelta(microseconds=1)
        elif granularity == "month":
            start = datetime.strptime(anchor[:7] + "-01", "%Y-%m-%d")
            end = start.replace(day=monthrange(start.year, start.month)[1], hour=23, minute=59, second=59)
        elif granularity == "year":
            start = datetime.strptime(anchor[:4] + "-01-01", "%Y-%m-%d")
            end = start.replace(year=start.year + 1) - timedelta(microseconds=1)
        else:
            raise ValueError("granularity must be day, week, month or year")
    except ValueError as exc:
        raise ValueError("Invalid analytics period") from exc
    return start, end


def _bucket_labels(granularity, start, end):
    labels = []
    if granularity == "day":
        for hour in range(24):
            labels.append(f"{hour:02d}:00")
    elif granularity in ("week", "month"):
        cursor = start.replace(hour=0, minute=0, second=0, microsecond=0)
        while cursor <= end:
            labels.append(cursor.strftime("%Y-%m-%d"))
            cursor += timedelta(days=1)
    else:
        for month in range(1, 13):
            labels.append(f"{start.year}-{month:02d}")
    return labels


def _energy_series(rooms, granularity, start, end, labels):
    values = {label: 0.0 for label in labels}
    room_totals = []
    for rd in rooms:
        room = rd.to_dict() or {}
        total = 0.0
        if granularity == "day":
            # Use cumulative energy history for an hourly curve.
            history_ref = rd.reference.collection("energy_history")
            docs = history_ref.order_by("timestamp").stream()
            previous = None
            for doc in docs:
                item = doc.to_dict() or {}
                ts = _dt(item.get("timestamp"))
                if not ts:
                    continue
                current = float(item.get("total_energy", 0) or 0)
                if previous is not None and start <= ts <= end:
                    delta = max(0.0, current - previous)
                    values[ts.strftime("%H:00")] += delta
                    total += delta
                previous = current
        else:
            for doc in rd.reference.collection("energy_daily").stream():
                item = doc.to_dict() or {}
                date = str(item.get("date", ""))
                try:
                    day = datetime.strptime(date[:10], "%Y-%m-%d")
                except ValueError:
                    continue
                if not (start <= day <= end):
                    continue
                consumption = float(item.get("consumption", 0) or 0)
                key = day.strftime("%Y-%m") if granularity == "year" else day.strftime("%Y-%m-%d")
                if key in values:
                    values[key] += consumption
                    total += consumption
        room_totals.append({
            "room_id": rd.id,
            "room_name": room.get("room_name") or rd.id,
            "consumption": round(total, 3),
        })
    return [round(values[label], 3) for label in labels], room_totals


def _collect_bills(rooms):
    bills = []
    seen = set()
    for rd in rooms:
        room = rd.to_dict() or {}
        for bd in rd.reference.collection("bills").stream():
            b = bd.to_dict() or {}
            b["id"] = bd.id
            b["room_id"] = rd.id
            b["room_name"] = b.get("room_name") or room.get("room_name") or rd.id
            key = (rd.id, b.get("period"), b.get("status"), b.get("paid_at"), False)
            if key not in seen:
                seen.add(key)
                b["archived"] = False
                bills.append(b)
    for hd in firestore_db.collection("bill_history").stream():
        b = hd.to_dict() or {}
        b["id"] = hd.id
        b["archived"] = True
        key = (b.get("room_id"), b.get("period"), b.get("status"), b.get("paid_at"), True)
        if key not in seen:
            seen.add(key)
            bills.append(b)
    return bills


def get_analytics_summary(granularity="month", anchor=None):
    granularity = (granularity or "month").lower()
    start, end = _period_bounds(granularity, anchor)
    labels = _bucket_labels(granularity, start, end)
    rooms = list(firestore_db.collection("rooms").stream())
    energy, by_room = _energy_series(rooms, granularity, start, end, labels)
    bills = _collect_bills(rooms)

    bill_count = {label: 0 for label in labels}
    revenue = {label: 0.0 for label in labels}
    outstanding = {label: 0.0 for label in labels}
    paid_count = {label: 0 for label in labels}
    cancelled_count = {label: 0 for label in labels}

    def bucket_for(ts):
        if not ts or ts < start or ts > end:
            return None
        if granularity == "day":
            return ts.strftime("%H:00")
        if granularity in ("week", "month"):
            return ts.strftime("%Y-%m-%d")
        return ts.strftime("%Y-%m")

    selected_bills = []
    for b in bills:
        status = b.get("status", "unpaid")
        generated = _dt(b.get("generated_at"))
        paid = _dt(b.get("paid_at"))
        changed = _dt(b.get("status_changed_at"))
        event_time = paid if status == "paid" and paid else (changed or generated)
        bucket = bucket_for(event_time)
        if bucket is None:
            continue
        total = float(b.get("total_cost", 0) or 0)
        bill_count[bucket] += 1
        selected_bills.append(b)
        if status == "paid":
            paid_count[bucket] += 1
            revenue[bucket] += total
        elif status == "cancelled":
            cancelled_count[bucket] += 1
        elif status == "unpaid":
            outstanding[bucket] += total

    total_energy = round(sum(energy), 3)
    total_revenue = round(sum(revenue.values()))
    total_outstanding = round(sum(outstanding.values()))
    return {
        "granularity": granularity,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "labels": labels,
        "energy": energy,
        "revenue": [round(x) for x in (revenue[label] for label in labels)],
        "bill_count_series": [bill_count[label] for label in labels],
        "paid_count_series": [paid_count[label] for label in labels],
        "cancelled_count_series": [cancelled_count[label] for label in labels],
        "outstanding_series": [round(outstanding[label]) for label in labels],
        "total_rooms": len(rooms),
        "total_energy": total_energy,
        "bill_count": len(selected_bills),
        "paid_bills": sum(paid_count.values()),
        "cancelled_bills": sum(cancelled_count.values()),
        "revenue_total": total_revenue,
        "outstanding_total": total_outstanding,
        "by_room": by_room,
    }
