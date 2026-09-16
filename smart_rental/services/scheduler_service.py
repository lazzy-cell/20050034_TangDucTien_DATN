from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone

from config import Config
from services.firebase_service import get_firestore
from services.tuya_service import get_room_electric_data
from services.energy_service import process_energy_data, save_energy_history
from services.daily_energy_service import update_daily_energy
from services.alert_service import check_room_alerts
from services.occupancy_service import _resolve_occupancy
from services.tuya_service import control_room_power


firestore_db = get_firestore()
scheduler = BackgroundScheduler()

latest_data = {}


def collect_all_rooms_data():
    print("Collecting electrical data...")

    rooms = firestore_db.collection("rooms").stream()

    for room_doc in rooms:
        room_id = room_doc.id
        room = room_doc.to_dict()

        device_id = room.get("device_id")

        if not device_id:
            print(f"{room_id}: No device_id")
            continue

        try:
            electrical_data = get_room_electric_data(device_id)

            if not electrical_data:
                print(f"{room_id}: Cannot get data")
                continue

            processed_data = process_energy_data(
                room_id=room_id,
                voltage=electrical_data.get("voltage"),
                current=electrical_data.get("current"),
                power=electrical_data.get("power"),
                switch=electrical_data.get("switch"),
                online=electrical_data.get("online")
            )

            alerts = check_room_alerts(room_id, processed_data)

            if alerts:
                print(f"Alerts for {room_id}: {len(alerts)}")

            latest_data[room_id] = processed_data

            print(f"{room_id}: {processed_data}")

        except Exception as e:
            print(f"Error collecting {room_id}: {e}")


def _timestamp_to_seconds(value):
    """Chuẩn hóa timestamp Firestore/datetime/ISO về Unix seconds."""
    if value is None:
        return None

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

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except (TypeError, ValueError, OverflowError):
            return None

    return None


def auto_cut_power_for_vacant_rooms():
    """
    Tự động ngắt điện khi phòng ở trạng thái VACANT liên tục quá ngưỡng.

    Chỉ trạng thái "vacant" được tính. "unknown" không được tính và làm
    gián đoạn chuỗi vacant liên tục. Khi đã ngắt thành công, scheduler
    không gửi lại lệnh cho tới khi phòng có người hoặc điện được bật lại.
    """
    if not getattr(Config, "AUTO_CUT_POWER", False):
        return

    threshold = max(
        0,
        int(getattr(Config, "AUTO_CUT_EMPTY_ROOM_SECONDS", 1800))
    )

    rooms = firestore_db.collection("rooms").stream()

    from services.firebase_service import get_realtime_db
    realtime_rooms = get_realtime_db().child("rooms").get() or {}

    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()

    for room_doc in rooms:
        room_id = room_doc.id
        room = room_doc.to_dict() or {}
        realtime = realtime_rooms.get(room_id, {}) or {}
        state = _resolve_occupancy(room, realtime, now_ts)
        room_ref = room_doc.reference

        # UNKNOWN/OCCUPIED đều làm gián đoạn chuỗi VACANT.
        if state["status"] != "vacant":
            updates = {}

            if room.get("vacant_since") is not None:
                updates["vacant_since"] = None

            if room.get("vacant_auto_cut_done"):
                updates["vacant_auto_cut_done"] = False

            if updates:
                try:
                    room_ref.update(updates)
                except Exception as e:
                    print(
                        f"Failed resetting vacant automation state "
                        f"[{room_id}]: {e}"
                    )
            continue

        # Bắt đầu chuỗi VACANT mới.
        vacant_since = room.get("vacant_since")
        if vacant_since is None:
            try:
                room_ref.update({
                    "vacant_since": now,
                    "vacant_auto_cut_done": False,
                })
            except Exception as e:
                print(f"Failed starting vacant timer [{room_id}]: {e}")
            continue

        # Đã cắt thành công trong chu kỳ VACANT hiện tại thì không lặp.
        # Nếu điện được bật lại thủ công, cho phép automation cắt lại sau
        # khi xác nhận phòng vẫn VACANT quá ngưỡng.
        if room.get("vacant_auto_cut_done"):
            if realtime.get("switch") is not True:
                continue

            try:
                room_ref.update({"vacant_auto_cut_done": False})
            except Exception as e:
                print(f"Failed resetting auto-cut flag [{room_id}]: {e}")

        vacant_since_ts = _timestamp_to_seconds(vacant_since)

        if vacant_since_ts is None:
            try:
                room_ref.update({
                    "vacant_since": now,
                    "vacant_auto_cut_done": False,
                })
            except Exception as e:
                print(f"Failed repairing vacant timer [{room_id}]: {e}")
            continue

        vacant_seconds = max(0.0, now_ts - vacant_since_ts)

        if vacant_seconds <= threshold:
            continue

        # Thiết bị đã OFF thì không cần gửi lại lệnh.
        if realtime.get("switch") is False:
            try:
                room_ref.update({"vacant_auto_cut_done": True})
            except Exception as e:
                print(f"Failed marking already-off room [{room_id}]: {e}")
            continue

        reason = (
            "Tự động ngắt điện vì phòng không có người liên tục "
            f"{int(vacant_seconds)} giây, vượt ngưỡng {threshold} giây"
        )

        try:
            result = control_room_power(
                room_id=room_id,
                switch_on=False,
                triggered_by="automation",
                reason=reason,
            )

            if result.get("success"):
                room_ref.update({
                    "vacant_auto_cut_done": True,
                    "vacant_auto_cut_at": now,
                    "vacant_auto_cut_threshold_seconds": threshold,
                })
                print(
                    f"AUTO CUT VACANT ROOM [{room_id}]: "
                    f"{int(vacant_seconds)}s > {threshold}s"
                )
            else:
                print(
                    f"AUTO CUT VACANT ROOM FAILED [{room_id}]: "
                    f"{result.get('message')}"
                )
        except Exception as e:
            print(f"AUTO CUT VACANT ROOM ERROR [{room_id}]: {e}")



def check_vacant_power_alerts():
    """
    Cảnh báo: phòng không có người liên tục quá ngưỡng nhưng vẫn tiêu thụ điện.
    Alert có debounce thông qua create_alert/get_active_alert.
    """
    threshold = max(60, int(getattr(Config, "AUTO_CUT_EMPTY_ROOM_SECONDS", 1800)))
    min_power = max(0.0, float(getattr(Config, "VACANT_POWER_ALERT_WATTS", 20)))
    rooms = firestore_db.collection("rooms").stream()

    from services.firebase_service import get_realtime_db
    realtime_rooms = get_realtime_db().child("rooms").get() or {}
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()

    from services.alert_service import create_alert, resolve_alert

    for room_doc in rooms:
        room_id = room_doc.id
        room = room_doc.to_dict() or {}
        realtime = realtime_rooms.get(room_id, {}) or {}
        state = _resolve_occupancy(room, realtime, now_ts)

        power = float(realtime.get("power") or latest_data.get(room_id, {}).get("power") or 0)
        if state["status"] == "vacant" and power > min_power:
            vacant_since = room.get("vacant_since")
            vacant_since_ts = _timestamp_to_seconds(vacant_since)
            if vacant_since_ts is not None and now_ts - vacant_since_ts >= threshold:
                alert = create_alert(
                    room_id,
                    "OCCUPANCY_POWER",
                    "Phòng không có người trong thời gian dài nhưng vẫn đang sử dụng điện",
                    round(power, 2),
                    min_power,
                )
                if alert:
                    print(
                        f"OCCUPANCY POWER ALERT [{room_id}]: "
                        f"vacant={int(now_ts-vacant_since_ts)}s power={power}W"
                    )
        else:
            resolve_alert(room_id, "OCCUPANCY_POWER")


def save_all_rooms_history():
    print("Saving energy history...")

    for room_id, data in latest_data.items():
        try:
            save_energy_history(room_id, data)
            update_daily_energy(room_id, data)

        except Exception as e:
            print(f"Error saving history for {room_id}: {e}")


def start_scheduler():
    scheduler.add_job(
        collect_all_rooms_data,
        "interval",
        seconds=5,
        id="collect_energy",
        replace_existing=True
    )

    scheduler.add_job(
        save_all_rooms_history,
        "interval",
        seconds=60,
        id="save_energy_history",
        replace_existing=True
    )

    scheduler.add_job(
        auto_cut_power_for_vacant_rooms,
        "interval",
        seconds=5,
        id="auto_cut_vacant_rooms",
        replace_existing=True,
    )

    scheduler.add_job(
        check_vacant_power_alerts,
        "interval",
        seconds=5,
        id="vacant_power_alerts",
        replace_existing=True,
    )

    scheduler.start()

    print("Scheduler started successfully")