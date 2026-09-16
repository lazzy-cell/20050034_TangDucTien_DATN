from datetime import datetime, timezone

from services.time_service import vn_now

from services.firebase_service import get_firestore


firestore_db = get_firestore()


def update_daily_energy(room_id, electrical_data):
    now = vn_now()
    date_str = now.strftime("%Y-%m-%d")

    total_energy = electrical_data.get("total_energy", 0) or 0
    power = electrical_data.get("power", 0) or 0

    daily_ref = (
        firestore_db
        .collection("rooms")
        .document(room_id)
        .collection("energy_daily")
        .document(date_str)
    )

    daily_doc = daily_ref.get()

    # Nếu đây là record đầu tiên trong ngày
    if not daily_doc.exists:
        daily_data = {
            "date": date_str,
            "start_energy": total_energy,
            "end_energy": total_energy,
            "consumption": 0,
            "peak_power": power,
            "power_sum": power,
            "sample_count": 1,
            "average_power": power,
            "updated_at": now
        }

        daily_ref.set(daily_data)

        return daily_data

    # Lấy dữ liệu ngày hiện tại
    data = daily_doc.to_dict()

    start_energy = data.get("start_energy", total_energy)
    peak_power = data.get("peak_power", 0)
    power_sum = data.get("power_sum", 0)
    sample_count = data.get("sample_count", 0)

    # Cập nhật dữ liệu
    peak_power = max(peak_power, power)
    power_sum += power
    sample_count += 1

    consumption = total_energy - start_energy

    # Tránh trường hợp total_energy bị reset
    if consumption < 0:
        consumption = 0

    average_power = power_sum / sample_count if sample_count > 0 else 0

    daily_data = {
        "date": date_str,
        "start_energy": round(start_energy, 6),
        "end_energy": round(total_energy, 6),
        "consumption": round(consumption, 6),
        "peak_power": round(peak_power, 2),
        "power_sum": round(power_sum, 2),
        "sample_count": sample_count,
        "average_power": round(average_power, 2),
        "updated_at": now
    }

    daily_ref.set(daily_data)

    return daily_data

def get_daily_energy(room_id, date=None):
    if date is None:
        date = vn_now().strftime("%Y-%m-%d")

    daily_doc = (
        firestore_db
        .collection("rooms")
        .document(room_id)
        .collection("energy_daily")
        .document(date)
        .get()
    )

    if not daily_doc.exists:
        return None

    data = daily_doc.to_dict()

    if data.get("updated_at"):
        data["updated_at"] = data["updated_at"].isoformat()

    return data