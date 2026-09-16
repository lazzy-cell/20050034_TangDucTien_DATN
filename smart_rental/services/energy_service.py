import time
from datetime import datetime, timezone

from services.firebase_service import get_realtime_db


realtime_db = get_realtime_db()

# Công suất nhỏ hơn ngưỡng này được xem là 0W
POWER_THRESHOLD = 1


def process_energy_data(room_id, voltage, current, power, switch, online):
    now = time.time()

    # Chuẩn hóa dữ liệu
    voltage = voltage or 0
    current = current or 0
    power = power or 0

    # Chỉ xem thiết bị đang tiêu thụ điện khi:
    # - Thiết bị online
    # - Breaker đang bật
    # - Công suất lớn hơn ngưỡng nhiễu
    is_active = (
        online is True
        and switch is True
        and power > POWER_THRESHOLD
    )

    # Công suất thực tế dùng để tính điện năng
    effective_power = power if is_active else 0

    # Đọc trạng thái năng lượng trước đó
    state_ref = realtime_db.child("energy_state").child(room_id)
    previous_state = state_ref.get()

    # Khởi tạo nếu chưa có dữ liệu
    if previous_state is None:
        previous_state = {
            "total_energy": 0,
            "last_power": effective_power,
            "last_timestamp": now,
            "last_active": is_active
        }

    total_energy = previous_state.get("total_energy", 0)
    last_power = previous_state.get("last_power", 0)
    last_timestamp = previous_state.get("last_timestamp", now)
    last_active = previous_state.get("last_active", False)

    # Tính khoảng thời gian giữa hai lần đo
    delta_time = now - last_timestamp
    delta_hour = delta_time / 3600

    energy_delta = 0

    # Chỉ tính điện năng khi cả lần đo trước và hiện tại đều đang hoạt động.
    # Điều này tránh trường hợp breaker vừa chuyển từ ON sang OFF
    # nhưng vẫn bị cộng điện năng từ dữ liệu cũ.
    if last_active and is_active:
        average_power = (last_power + effective_power) / 2
        energy_delta = average_power * delta_hour / 1000
        total_energy += energy_delta

    # Lưu trạng thái để dùng cho lần đo tiếp theo
    state_data = {
        "total_energy": round(total_energy, 6),
        "last_power": effective_power,
        "last_timestamp": now,
        "last_active": is_active
    }

    state_ref.set(state_data)

    # Dữ liệu realtime cho frontend
    realtime_data = {
        "voltage": voltage,
        "current": current,
        "raw_power": power,
        "power": effective_power,
        "switch": switch,
        "online": online,
        "is_active": is_active,
        "energy_delta": round(energy_delta, 8),
        "total_energy": round(total_energy, 6),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    # Lưu dữ liệu realtime
    realtime_ref = realtime_db.child("rooms").child(room_id)
    realtime_ref.set(realtime_data)

    return realtime_data


def save_energy_history(room_id, electrical_data):
    from services.firebase_service import get_firestore

    firestore_db = get_firestore()

    history_data = {
        "voltage": electrical_data.get("voltage"),
        "current": electrical_data.get("current"),
        "power": electrical_data.get("power"),
        "raw_power": electrical_data.get("raw_power"),
        "total_energy": electrical_data.get("total_energy"),
        "switch": electrical_data.get("switch"),
        "online": electrical_data.get("online"),
        "is_active": electrical_data.get("is_active"),
        "timestamp": datetime.now(timezone.utc)
    }

    firestore_db.collection("rooms") \
        .document(room_id) \
        .collection("energy_history") \
        .add(history_data)

    print(f"Saved energy history: {room_id}")