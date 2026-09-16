from datetime import datetime, timezone

from services.access_token import get_access_token
from services.device import get_device_info, send_device_command
from services.firebase_service import get_firestore


VOLTAGE_SCALE = 10
CURRENT_SCALE = 100
POWER_SCALE = 1


def get_room_electric_data(device_id):
    """Đọc dữ liệu điện năng realtime từ thiết bị Tuya."""
    access_token = get_access_token()
    device_data = get_device_info(access_token, device_id)

    if not device_data.get("success"):
        return None

    result = device_data.get("result", {})
    status_list = result.get("status", [])

    status = {
        item["code"]: item["value"]
        for item in status_list
    }

    raw_voltage = status.get("cur_voltage", 0) or 0
    raw_current = status.get("cur_current", 0) or 0
    raw_power = status.get("cur_power", 0) or 0

    voltage = raw_voltage / VOLTAGE_SCALE
    current = raw_current / CURRENT_SCALE
    power = raw_power / POWER_SCALE

    return {
        "voltage": voltage,
        "current": current,
        "power": power,
        "switch": status.get("switch", False),
        "online": result.get("online", False),
    }


def set_device_switch(device_id, switch_on: bool):
    """
    Đóng/ngắt nguồn điện thiết bị Tuya.
    switch_on=True  -> bật
    switch_on=False -> tắt
    """
    access_token = get_access_token()
    body = {
        "commands": [
            {
                "code": "switch",
                "value": bool(switch_on),
            }
        ]
    }
    result = send_device_command(access_token, device_id, body)
    return result


def control_room_power(room_id, switch_on: bool, triggered_by="manual", reason=None):
    """
    Điều khiển nguồn điện theo room_id.
    Lấy device_id từ Firestore, gửi lệnh Tuya, ghi lịch sử điều khiển.
    """
    firestore_db = get_firestore()
    room_doc = firestore_db.collection("rooms").document(room_id).get()

    if not room_doc.exists:
        return {
            "success": False,
            "message": "Room not found",
        }

    room = room_doc.to_dict()
    device_id = room.get("device_id")

    if not device_id:
        return {
            "success": False,
            "message": "Room has no device_id",
        }

    try:
        tuya_result = set_device_switch(device_id, switch_on)
    except Exception as e:
        return {
            "success": False,
            "message": f"Tuya command failed: {str(e)}",
        }

    success = bool(tuya_result.get("success"))

    history_data = {
        "room_id": room_id,
        "device_id": device_id,
        "switch": bool(switch_on),
        "action": "ON" if switch_on else "OFF",
        "triggered_by": triggered_by,
        "reason": reason,
        "tuya_success": success,
        "tuya_response": tuya_result,
        "timestamp": datetime.now(timezone.utc),
    }

    firestore_db.collection("control_history").add(history_data)

    try:
        from services.firebase_service import get_realtime_db
        realtime_db = get_realtime_db()
        realtime_db.child("rooms").child(room_id).child("switch").set(bool(switch_on))
    except Exception:
        pass

    if not success:
        return {
            "success": False,
            "message": "Tuya API returned failure",
            "tuya_response": tuya_result,
        }

    
    try:
        from services.notification_service import notify_power_change
        notify_power_change(room_id, switch_on, reason)
    except Exception as e:
        print(f"Power push notify failed: {e}")

    return {
        "success": True,
        "message": f"Power {'ON' if switch_on else 'OFF'} successfully",
        "room_id": room_id,
        "device_id": device_id,
        "switch": bool(switch_on),
        "triggered_by": triggered_by,
    }
