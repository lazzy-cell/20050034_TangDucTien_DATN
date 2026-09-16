from datetime import datetime, timezone

from google.cloud.firestore_v1.base_query import FieldFilter

from config import Config
from services.firebase_service import get_firestore
from services.id_service import new_document_ref


firestore_db = get_firestore()

alert_counters = {}


def get_active_alert(room_id, alert_type):
    docs = (
        firestore_db
        .collection("alerts")
        .where(filter=FieldFilter("room_id", "==", room_id))
        .where(filter=FieldFilter("type", "==", alert_type))
        .where(filter=FieldFilter("status", "==", "active"))
        .limit(1)
        .stream()
    )

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        return data

    return None


def create_alert(room_id, alert_type, message, value=None, threshold=None):
    existing_alert = get_active_alert(room_id, alert_type)

    if existing_alert:
        return None

    now = datetime.now(timezone.utc)

    alert_data = {
        "room_id": room_id,
        "type": alert_type,
        "message": message,
        "value": value,
        "threshold": threshold,
        "status": "active",
        "created_at": now,
        "updated_at": now
    }

    alert_ref = new_document_ref("alerts")
    alert_ref.set(alert_data)

    alert_data["id"] = alert_ref.id

    print(f"NEW ALERT [{alert_type}] {room_id}: {message}")

    try:
        from services.notification_service import notify_alert
        notify_alert(room_id, alert_type, message, value)
    except Exception as e:
        print(f"Push notify failed: {e}")

    return alert_data


def resolve_alert(room_id, alert_type):
    docs = (
        firestore_db
        .collection("alerts")
        .where(filter=FieldFilter("room_id", "==", room_id))
        .where(filter=FieldFilter("type", "==", alert_type))
        .where(filter=FieldFilter("status", "==", "active"))
        .stream()
    )

    resolved_count = 0

    for doc in docs:
        doc.reference.update({
            "status": "resolved",
            "updated_at": datetime.now(timezone.utc)
        })

        resolved_count += 1

    if resolved_count > 0:
        print(f"RESOLVED [{alert_type}] {room_id}")


def get_counter_key(room_id, alert_type):
    return f"{room_id}:{alert_type}"


def increase_counter(room_id, alert_type):
    key = get_counter_key(room_id, alert_type)

    current_count = alert_counters.get(key, 0)
    current_count += 1

    alert_counters[key] = current_count

    return current_count


def reset_counter(room_id, alert_type):
    key = get_counter_key(room_id, alert_type)

    if key in alert_counters:
        alert_counters[key] = 0


def check_debounce(room_id, alert_type, is_violation):
    if is_violation:
        count = increase_counter(room_id, alert_type)

        print(
            f"ALERT CHECK [{alert_type}] "
            f"{room_id}: "
            f"{count}/{Config.ALERT_DEBOUNCE_COUNT}"
        )

        return count >= Config.ALERT_DEBOUNCE_COUNT

    reset_counter(room_id, alert_type)

    return False


def _try_auto_cut_power(room_id, alert_type, value=None):
    """
    Automation Rule: tự động ngắt nguồn khi quá tải / dòng cao.
    Chỉ chạy khi Config.AUTO_CUT_POWER = True.
    """
    if not getattr(Config, "AUTO_CUT_POWER", False):
        return

    if alert_type not in ("HIGH_POWER", "HIGH_CURRENT"):
        return

    try:
        from services.tuya_service import control_room_power

        reason = (
            f"Auto cut by {alert_type}"
            + (f" (value={value})" if value is not None else "")
        )
        result = control_room_power(
            room_id=room_id,
            switch_on=False,
            triggered_by="automation",
            reason=reason,
        )
        if result.get("success"):
            print(f"AUTO CUT POWER [{alert_type}] {room_id}: OK")
        else:
            print(
                f"AUTO CUT POWER [{alert_type}] {room_id}: FAILED - "
                f"{result.get('message')}"
            )
    except Exception as e:
        print(f"AUTO CUT POWER error [{room_id}]: {e}")


def check_room_alerts(room_id, electrical_data):
    new_alerts = []

    online = electrical_data.get("online", False)
    power = electrical_data.get("power", 0) or 0
    current = electrical_data.get("current", 0) or 0
    voltage = electrical_data.get("voltage", 0) or 0

    offline_violation = not online

    if check_debounce(room_id, "DEVICE_OFFLINE", offline_violation):
        alert = create_alert(
            room_id,
            "DEVICE_OFFLINE",
            "Thiết bị điện đang offline"
        )

        if alert:
            new_alerts.append(alert)

    elif not offline_violation:
        resolve_alert(room_id, "DEVICE_OFFLINE")

    high_power_violation = (
        online
        and power > Config.ALERT_HIGH_POWER
    )

    if check_debounce(room_id, "HIGH_POWER", high_power_violation):
        alert = create_alert(
            room_id,
            "HIGH_POWER",
            "Công suất vượt ngưỡng cho phép",
            power,
            Config.ALERT_HIGH_POWER
        )

        if alert:
            new_alerts.append(alert)
            _try_auto_cut_power(room_id, "HIGH_POWER", power)

    elif not high_power_violation:
        resolve_alert(room_id, "HIGH_POWER")

    high_current_violation = (
        online
        and current > Config.ALERT_HIGH_CURRENT
    )

    if check_debounce(room_id, "HIGH_CURRENT", high_current_violation):
        alert = create_alert(
            room_id,
            "HIGH_CURRENT",
            "Dòng điện vượt ngưỡng cho phép",
            current,
            Config.ALERT_HIGH_CURRENT
        )

        if alert:
            new_alerts.append(alert)
            _try_auto_cut_power(room_id, "HIGH_CURRENT", current)

    elif not high_current_violation:
        resolve_alert(room_id, "HIGH_CURRENT")

    low_voltage_violation = (
        online
        and voltage < Config.ALERT_LOW_VOLTAGE
    )

    if check_debounce(room_id, "LOW_VOLTAGE", low_voltage_violation):
        alert = create_alert(
            room_id,
            "LOW_VOLTAGE",
            "Điện áp thấp hơn ngưỡng cho phép",
            voltage,
            Config.ALERT_LOW_VOLTAGE
        )

        if alert:
            new_alerts.append(alert)

    elif not low_voltage_violation:
        resolve_alert(room_id, "LOW_VOLTAGE")

    high_voltage_violation = (
        online
        and voltage > Config.ALERT_HIGH_VOLTAGE
    )

    if check_debounce(room_id, "HIGH_VOLTAGE", high_voltage_violation):
        alert = create_alert(
            room_id,
            "HIGH_VOLTAGE",
            "Điện áp cao hơn ngưỡng cho phép",
            voltage,
            Config.ALERT_HIGH_VOLTAGE
        )

        if alert:
            new_alerts.append(alert)

    elif not high_voltage_violation:
        resolve_alert(room_id, "HIGH_VOLTAGE")

    return new_alerts
