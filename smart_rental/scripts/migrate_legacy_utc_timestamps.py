"""One-time migration for timestamps written with naive UTC datetimes.

The previous backend used datetime.now() on a UTC host and persisted the
result as a naive datetime/string. In the affected installation that made
Vietnam UI times appear about 7 hours ahead. New code writes UTC-aware
timestamps and the dashboard/app render them in the device/browser timezone.

Default is DRY RUN. After reviewing the output and taking a Firestore/RTDB
backup, run with APPLY=1:
    APPLY=1 python scripts/migrate_legacy_utc_timestamps.py
"""
import os
from datetime import datetime, timedelta, timezone

from services.firebase_service import get_firestore, get_realtime_db

APPLY = os.getenv("APPLY", "0").lower() in {"1", "true", "yes"}
FIRESTORE_COLLECTIONS = (
    "notification_logs",
    "tenant_notifications",
    "alerts",
    "control_history",
)


def shift_firestore(value):
    if not isinstance(value, datetime):
        return None
    # Old values were naive UTC. Firestore normally returns Timestamp as aware
    # UTC, but the correction is the same: move the stored instant back 7h.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value - timedelta(hours=7)


def shift_iso(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (parsed - timedelta(hours=7)).astimezone(timezone.utc).isoformat()


def migrate_firestore():
    db = get_firestore()
    count = 0
    for collection in FIRESTORE_COLLECTIONS:
        for doc in db.collection(collection).stream():
            data = doc.to_dict() or {}
            updates = {}
            for field in ("created_at", "updated_at", "timestamp"):
                corrected = shift_firestore(data.get(field))
                if corrected is None:
                    continue
                updates[field] = corrected
                count += 1
                print(f"Firestore {collection}/{doc.id}.{field}: {data[field]} -> {corrected}")
            if APPLY and updates:
                doc.reference.update(updates)
    return count


def migrate_rtdb():
    db = get_realtime_db()
    rooms = db.child("rooms").get() or {}
    count = 0
    for room_id, room in rooms.items():
        if not isinstance(room, dict):
            continue
        old = room.get("updated_at")
        corrected = shift_iso(old)
        if corrected is None:
            continue
        count += 1
        print(f"RTDB rooms/{room_id}.updated_at: {old} -> {corrected}")
        if APPLY:
            db.child("rooms").child(room_id).child("updated_at").set(corrected)
    return count


def main():
    firestore_count = migrate_firestore()
    rtdb_count = migrate_rtdb()
    print(f"Found {firestore_count} Firestore + {rtdb_count} RTDB timestamps. APPLY={APPLY}")


if __name__ == "__main__":
    main()
