"""
Occupancy service — nhận dữ liệu Computer Vision từ Raspberry Pi / Edge node
và đồng bộ trạng thái có người / không có người theo từng phòng.

Quan trọng: occupancy là dữ liệu "có thời hạn". Nếu detect_person không gửi
heartbeat/update trong OCCUPANCY_STALE_SECONDS, trạng thái được coi là
UNKNOWN thay vì giữ lại giá trị có/không có người cuối cùng.
"""
from datetime import datetime, timezone

from services.firebase_service import get_firestore, get_realtime_db


firestore_db = get_firestore()
realtime_db = get_realtime_db()

# detect_person khuyến nghị heartbeat mỗi 60s, vì vậy 120s cho phép một
# vài lần retry mạng nhưng không giữ trạng thái cũ quá lâu.
OCCUPANCY_STALE_SECONDS = 120

# Chỉ heartbeat do SERVER ghi nhận mới được dùng để quyết định freshness.
# Các timestamp do detect_person gửi lên không được dùng làm mốc sống/chết.
OCCUPANCY_HEARTBEAT_FIELD = "occupancy_heartbeat_at"


def _timestamp(value):
    """Chuẩn hóa Firestore Timestamp/datetime/seconds/milliseconds/ISO về Unix seconds."""
    if value is None:
        return None

    # Firestore Timestamp có .timestamp(), nhưng không nên gọi datetime.timestamp
    # trực tiếp vì kiểu này có thể không phải datetime chuẩn.
    if hasattr(value, "timestamp") and callable(value.timestamp):
        try:
            return float(value.timestamp())
        except (TypeError, ValueError, OverflowError):
            pass

    if isinstance(value, datetime):
        try:
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.timestamp()
        except (TypeError, ValueError, OverflowError):
            return None

    if isinstance(value, (int, float)):
        number = float(value)
        # Unix milliseconds hiện nay có 13 chữ số; seconds có khoảng 10 chữ số.
        if abs(number) >= 100_000_000_000:
            number /= 1000.0
        return number

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
            if abs(number) >= 100_000_000_000:
                number /= 1000.0
            return number
        except (TypeError, ValueError):
            pass

        try:
            value = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.timestamp()
        except (TypeError, ValueError, OverflowError):
            return None

    return None


def _resolve_occupancy(room: dict, realtime: dict, now_ts=None):
    """
    Resolve occupancy ONLY from the latest SERVER-SIDE heartbeat.

    Legacy fields such as room['occupied'], occupancy_updated_at and the old
    RTDB room-level 'occupied' value are intentionally ignored as freshness
    sources. This prevents an old CV result from remaining authoritative after
    the detector stops sending data.
    """
    now_ts = datetime.now(timezone.utc).timestamp() if now_ts is None else now_ts
    occ = realtime.get("occupancy") or {}

    # The only freshness marker is written by update_occupancy() at receipt time.
    rt_hb = _timestamp(occ.get(OCCUPANCY_HEARTBEAT_FIELD))
    fs_hb = _timestamp(room.get(OCCUPANCY_HEARTBEAT_FIELD))

    candidates = []
    if rt_hb is not None and occ.get("occupied") is not None:
        candidates.append((rt_hb, occ, "realtime"))

    # Firestore stores the same server receipt time as a second durable source.
    if fs_hb is not None and room.get("occupied") is not None:
        candidates.append((fs_hb, {
            "occupied": room.get("occupied"),
            "person_count": room.get("person_count", 0),
            "confidence": room.get("occupancy_confidence"),
            "source": room.get("occupancy_source"),
            "snapshot_url": room.get("occupancy_snapshot_url"),
            OCCUPANCY_HEARTBEAT_FIELD: room.get(OCCUPANCY_HEARTBEAT_FIELD),
        }, "firestore"))

    if not candidates:
        return {
            "occupied": None,
            "person_count": 0,
            "confidence": None,
            "source": "unknown",
            "snapshot_url": None,
            "heartbeat_at": None,
            "timestamp": None,
            "is_stale": True,
            "status": "unknown",
        }

    heartbeat_ts, data, _backend = max(candidates, key=lambda item: item[0])
    age_seconds = max(0.0, now_ts - heartbeat_ts)
    is_stale = age_seconds > OCCUPANCY_STALE_SECONDS

    if is_stale:
        return {
            "occupied": None,
            "person_count": 0,
            "confidence": None,
            "source": data.get("source") or "computer_vision",
            "snapshot_url": None,
            "heartbeat_at": heartbeat_ts,
            "timestamp": heartbeat_ts,
            "age_seconds": round(age_seconds, 3),
            "is_stale": True,
            "status": "unknown",
        }

    occupied = data.get("occupied")
    if not isinstance(occupied, bool):
        return {
            "occupied": None,
            "person_count": 0,
            "confidence": None,
            "source": data.get("source") or "unknown",
            "snapshot_url": None,
            "heartbeat_at": heartbeat_ts,
            "timestamp": heartbeat_ts,
            "age_seconds": round(age_seconds, 3),
            "is_stale": True,
            "status": "unknown",
        }

    try:
        count = max(0, int(data.get("person_count") or 0))
    except (TypeError, ValueError):
        count = 0

    return {
        "occupied": occupied,
        "person_count": count,
        "confidence": data.get("confidence"),
        "source": data.get("source") or "computer_vision",
        "snapshot_url": data.get("snapshot_url"),
        "heartbeat_at": heartbeat_ts,
        "timestamp": heartbeat_ts,
        "age_seconds": round(age_seconds, 3),
        "is_stale": False,
        "status": "occupied" if occupied else "vacant",
    }


def update_occupancy(
    room_id: str,
    occupied: bool,
    person_count: int = 0,
    confidence: float = None,
    source: str = "computer_vision",
    snapshot_url: str = None,
    extra: dict = None,
):
    """Cập nhật trạng thái occupancy từ node Computer Vision."""
    room_ref = firestore_db.collection("rooms").document(room_id)
    room_doc = room_ref.get()

    if not room_doc.exists:
        return {
            "success": False,
            "message": "Room not found",
        }

    # Server-side receipt time. Client-provided timestamps are never used for
    # freshness, preventing a stale detector from faking a live heartbeat.
    now = datetime.now(timezone.utc)
    server_heartbeat_ts = now.timestamp()
    occupied = bool(occupied)
    person_count = max(0, int(person_count or 0))
    if occupied and person_count == 0:
        person_count = 1

    occupancy_data = {
        "occupied": occupied,
        "person_count": person_count,
        "confidence": confidence,
        "source": source,
        "snapshot_url": snapshot_url,
        "updated_at": now.isoformat(),
        "timestamp": server_heartbeat_ts,
        OCCUPANCY_HEARTBEAT_FIELD: now.isoformat(),
        "server_heartbeat_ts": server_heartbeat_ts,
    }

    if extra and isinstance(extra, dict):
        occupancy_data["extra"] = extra

    # 1) Realtime Database — dashboard đọc nhanh.
    try:
        realtime_db.child("rooms").child(room_id).child("occupancy").set(occupancy_data)
        realtime_db.child("rooms").child(room_id).update({
            # Legacy fields are kept for other consumers, but occupancy reads
            # never use them as the freshness source.
            "occupied": occupied,
            "person_count": person_count,
        })
    except Exception as e:
        print(f"RTDB occupancy update failed for {room_id}: {e}")

    # 2) Firestore room document.
    try:
        room_ref.update({
            # Legacy values remain for history/compatibility only.
            "occupied": occupied,
            "person_count": person_count,
            "occupancy_updated_at": now,
            "occupancy_source": source,
            OCCUPANCY_HEARTBEAT_FIELD: now,
        })
    except Exception as e:
        print(f"Firestore room occupancy update failed for {room_id}: {e}")

    # 3) Lịch sử occupancy.
    history_entry = {
        "occupied": occupied,
        "person_count": person_count,
        "confidence": confidence,
        "source": source,
        "snapshot_url": snapshot_url,
        "timestamp": now,
        OCCUPANCY_HEARTBEAT_FIELD: now,
    }
    try:
        room_ref.collection("occupancy_history").add(history_entry)
    except Exception as e:
        print(f"Occupancy history write failed for {room_id}: {e}")

    return {
        "success": True,
        "message": "Occupancy updated",
        "room_id": room_id,
        "data": occupancy_data,
    }


def get_room_occupancy(room_id: str):
    """Lấy occupancy hiện tại; dữ liệu stale/missing luôn được trả về UNKNOWN."""
    room_doc = firestore_db.collection("rooms").document(room_id).get()
    if not room_doc.exists:
        return None

    room = room_doc.to_dict() or {}
    realtime = realtime_db.child("rooms").child(room_id).get() or {}
    state = _resolve_occupancy(room, realtime)

    return {
        "room_id": room_id,
        "room_name": room.get("room_name"),
        "occupied": state["occupied"],
        "status": state["status"],
        "person_count": state["person_count"],
        "confidence": state["confidence"],
        "source": state["source"],
        "snapshot_url": state["snapshot_url"],
        "updated_at": (
            state["heartbeat_at"]
            if isinstance(state["heartbeat_at"], (int, float))
            else state["heartbeat_at"]
        ),
        "heartbeat_at": state["heartbeat_at"],
        "age_seconds": state.get("age_seconds"),
        "stale_after_seconds": OCCUPANCY_STALE_SECONDS,
        "is_stale": state["is_stale"],
    }


def get_all_occupancy():
    """Tổng hợp occupancy toàn bộ phòng, phân biệt rõ occupied/vacant/unknown."""
    rooms = firestore_db.collection("rooms").stream()
    realtime_rooms = realtime_db.child("rooms").get() or {}

    result = []
    occupied_count = 0
    vacant_count = 0
    unknown_count = 0
    stale_count = 0
    now_ts = datetime.now(timezone.utc).timestamp()

    for room_doc in rooms:
        room_id = room_doc.id
        room = room_doc.to_dict() or {}
        realtime = realtime_rooms.get(room_id, {}) or {}
        state = _resolve_occupancy(room, realtime, now_ts)

        if state["status"] == "occupied":
            occupied_count += 1
        elif state["status"] == "vacant":
            vacant_count += 1
        else:
            unknown_count += 1

        if state["is_stale"]:
            stale_count += 1

        heartbeat_at = state.get("heartbeat_at")

        result.append({
            "room_id": room_id,
            "room_name": room.get("room_name"),
            "occupied": state["occupied"],
            "status": state["status"],
            "person_count": state["person_count"],
            "confidence": state["confidence"],
            "source": state["source"],
            "updated_at": heartbeat_at,
            "heartbeat_at": heartbeat_at,
            "age_seconds": state.get("age_seconds"),
            "stale_after_seconds": OCCUPANCY_STALE_SECONDS,
            "is_stale": state["is_stale"],
        })

    summary = {
        "total": len(result),
        "occupied": occupied_count,
        "vacant": vacant_count,
        "unknown": unknown_count,
        "stale": stale_count,
    }

    return {
        "summary": summary,
        # Giữ các field top-level để client cũ vẫn tương thích.
        "occupied": occupied_count,
        "vacant": vacant_count,
        "unknown": unknown_count,
        "total": len(result),
        "rooms": result,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_occupancy_history(room_id: str, limit: int = 50):
    """Lịch sử occupancy của phòng."""
    room_ref = firestore_db.collection("rooms").document(room_id)
    if not room_ref.get().exists:
        return None

    limit = min(max(1, int(limit)), 200)
    docs = (
        room_ref
        .collection("occupancy_history")
        .order_by("timestamp", direction="DESCENDING")
        .limit(limit)
        .stream()
    )

    history = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        if data.get("timestamp"):
            data["timestamp"] = data["timestamp"].isoformat()
        history.append(data)

    return history
