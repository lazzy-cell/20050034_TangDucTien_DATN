"""
Cài đặt hệ thống toàn cục (giá điện thống nhất, ngưỡng cảnh báo...).
Lưu tại Firestore: settings/global
"""
from datetime import datetime, timezone

from config import Config
from services.firebase_service import get_firestore


firestore_db = get_firestore()
SETTINGS_DOC = "global"


def _defaults():
    return {
        "electricity_price": Config.DEFAULT_ELECTRICITY_PRICE,
        "alert_high_power": Config.ALERT_HIGH_POWER,
        "alert_high_current": Config.ALERT_HIGH_CURRENT,
        "alert_low_voltage": Config.ALERT_LOW_VOLTAGE,
        "alert_high_voltage": Config.ALERT_HIGH_VOLTAGE,
        "auto_cut_power": Config.AUTO_CUT_POWER,
        "updated_at": None,
    }


def get_settings():
    doc = firestore_db.collection("settings").document(SETTINGS_DOC).get()
    if not doc.exists:
        data = _defaults()
        firestore_db.collection("settings").document(SETTINGS_DOC).set({
            **{k: v for k, v in data.items() if k != "updated_at"},
            "updated_at": datetime.now(timezone.utc),
        })
        return data

    data = doc.to_dict() or {}
    base = _defaults()
    base.update({k: v for k, v in data.items() if v is not None})
    if hasattr(base.get("updated_at"), "isoformat"):
        base["updated_at"] = base["updated_at"].isoformat()
    return base


def get_electricity_price():
    """Giá điện thống nhất (VND/kWh) cho toàn bộ nhà trọ."""
    settings = get_settings()
    try:
        return float(settings.get("electricity_price") or Config.DEFAULT_ELECTRICITY_PRICE)
    except (TypeError, ValueError):
        return float(Config.DEFAULT_ELECTRICITY_PRICE)


def update_settings(payload: dict):
    allowed = {
        "electricity_price",
        "alert_high_power",
        "alert_high_current",
        "alert_low_voltage",
        "alert_high_voltage",
        "auto_cut_power",
    }
    update = {"updated_at": datetime.now(timezone.utc)}

    for key in allowed:
        if key not in payload:
            continue
        val = payload[key]
        if key == "auto_cut_power":
            update[key] = bool(val)
        else:
            try:
                update[key] = float(val)
            except (TypeError, ValueError):
                continue

    if "electricity_price" in update and update["electricity_price"] < 0:
        raise ValueError("electricity_price must be >= 0")

    ref = firestore_db.collection("settings").document(SETTINGS_DOC)
    if not ref.get().exists:
        ref.set({**_defaults(), **update})
    else:
        ref.update(update)

    # Đồng bộ giá điện lên mọi phòng (field mirror, để UI/legacy không lệch)
    if "electricity_price" in update:
        price = update["electricity_price"]
        for room in firestore_db.collection("rooms").stream():
            try:
                room.reference.update({"electricity_price": price})
            except Exception:
                pass
        # Đồng bộ lên hợp đồng đang active
        for c in firestore_db.collection("contracts").where("status", "==", "active").stream():
            try:
                c.reference.update({"electricity_price": price})
            except Exception:
                pass

    return get_settings()
