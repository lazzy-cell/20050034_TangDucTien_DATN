"""Firebase Cloud Messaging and tenant notification inbox service."""
from datetime import datetime, timezone
from typing import List, Optional

from firebase_admin import messaging

from services.firebase_service import get_firestore


firestore_db = get_firestore()
TOKENS_COL = "push_tokens"


def _utc_now():
    return datetime.now(timezone.utc)


def _serialize_ts(data: dict):
    for key in ("created_at", "updated_at", "last_sent_at"):
        if data.get(key) and hasattr(data[key], "isoformat"):
            data[key] = data[key].isoformat()
    return data


def register_push_token(
    token: str,
    role: str,
    user_id: str,
    platform: str = "android",
    device_name: str = None,
    token_type: str = "fcm",
):
    if not token:
        raise ValueError("Invalid push token")
    if role not in ("landlord", "tenant"):
        raise ValueError("role must be landlord or tenant")
    if not user_id:
        raise ValueError("user_id is required")
    if token_type != "fcm":
        raise ValueError("Only native FCM tokens are supported")

    safe_id = token.replace("/", "_").replace("[", "_").replace("]", "_").replace(" ", "")
    now = _utc_now()
    payload = {
        "token": token,
        "token_type": "fcm",
        "role": role,
        # For tenants this is the Firebase Auth UID. This is intentional:
        # /register receives the UID from the verified Firebase ID token.
        "user_id": str(user_id),
        "platform": platform or "android",
        "device_name": device_name,
        "active": True,
        "updated_at": now,
    }

    ref = firestore_db.collection(TOKENS_COL).document(safe_id)
    existing = ref.get()
    if existing.exists:
        ref.update(payload)
    else:
        payload["created_at"] = now
        ref.set(payload)

    return {"success": True, "message": "FCM token registered", "token_id": safe_id}


def unregister_push_token(token: str):
    safe_id = token.replace("/", "_").replace("[", "_").replace("]", "_").replace(" ", "")
    ref = firestore_db.collection(TOKENS_COL).document(safe_id)
    if ref.get().exists:
        ref.update({"active": False, "updated_at": _utc_now()})
        return True
    return False


def get_tokens_for_user(role: str, user_id: str) -> List[str]:
    docs = (
        firestore_db.collection(TOKENS_COL)
        .where("role", "==", role)
        .where("user_id", "==", str(user_id))
        .where("active", "==", True)
        .stream()
    )
    return [
        d.to_dict().get("token")
        for d in docs
        if d.to_dict().get("token") and d.to_dict().get("token_type", "fcm") == "fcm"
    ]


def get_tenant_auth_uid(tenant_id: str) -> Optional[str]:
    """Resolve Firestore tenant document ID -> Firebase Auth UID."""
    if not tenant_id:
        return None
    doc = firestore_db.collection("tenants").document(str(tenant_id)).get()
    if not doc.exists:
        # Backward-compatible case where caller already supplied an Auth UID.
        return str(tenant_id)
    return str((doc.to_dict() or {}).get("auth_uid") or tenant_id)


def get_tokens_for_tenant(tenant_id: str) -> List[str]:
    """Return active FCM tokens for a tenant document ID.

    Token registration stores Firebase Auth UID, while contracts/tenant inbox
    use the Firestore tenant document ID. Resolving that mismatch fixes all
    targeted tenant pushes (admin messages, bills, room alerts/power).
    """
    auth_uid = get_tenant_auth_uid(tenant_id)
    if not auth_uid:
        return []
    return get_tokens_for_user("tenant", auth_uid)


def get_all_landlord_tokens() -> List[str]:
    docs = (
        firestore_db.collection(TOKENS_COL)
        .where("role", "==", "landlord")
        .where("active", "==", True)
        .stream()
    )
    return [
        d.to_dict().get("token")
        for d in docs
        if d.to_dict().get("token") and d.to_dict().get("token_type", "fcm") == "fcm"
    ]


def get_all_tenant_tokens() -> List[str]:
    docs = (
        firestore_db.collection(TOKENS_COL)
        .where("role", "==", "tenant")
        .where("active", "==", True)
        .stream()
    )
    return [
        d.to_dict().get("token")
        for d in docs
        if d.to_dict().get("token") and d.to_dict().get("token_type", "fcm") == "fcm"
    ]


def _save_notification_log(entry: dict):
    try:
        entry = dict(entry)
        entry["created_at"] = _utc_now()
        firestore_db.collection("notification_logs").add(entry)
    except Exception as e:
        print(f"[notify] log failed: {e}")


def _stringify_data(data: Optional[dict]) -> dict:
    result = {}
    for key, value in (data or {}).items():
        if value is None:
            continue
        if isinstance(value, bool):
            result[str(key)] = "true" if value else "false"
        elif isinstance(value, (dict, list)):
            import json
            result[str(key)] = json.dumps(value, ensure_ascii=False)
        else:
            result[str(key)] = str(value)
    return result


def _channel_for(data: Optional[dict], channel_id: str) -> str:
    kind = str((data or {}).get("type") or "")
    if kind in ("alert", "occupancy", "incident"):
        return "alerts"
    if kind == "power":
        return "power"
    if kind == "bill":
        return "bills"
    if kind == "admin_message":
        return "admin"
    return channel_id or "default"


def send_expo_push(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[dict] = None,
    priority: str = "high",
    channel_id: str = "default",
):
    """Send native FCM messages and persist an admin delivery log."""
    tokens = list(dict.fromkeys([t for t in (tokens or []) if t]))
    if not tokens:
        _save_notification_log({
            "provider": "fcm",
            "title": title,
            "body": body,
            "data": data or {},
            "token_count": 0,
            "sent_count": 0,
            "errors": [],
            "status": "no_tokens",
        })
        return {"success": False, "sent": 0, "attempted": 0, "message": "No tokens", "tickets": []}

    android_channel = _channel_for(data, channel_id)
    string_data = _stringify_data(data)
    tickets = []
    errors = []
    success_count = 0

    for token in tokens:
        message = messaging.Message(
            token=token,
            notification=messaging.Notification(title=title, body=body),
            data=string_data,
            android=messaging.AndroidConfig(
                priority="high" if priority == "high" else "normal",
                notification=messaging.AndroidNotification(
                    channel_id=android_channel,
                    sound="default",
                    default_sound=True,
                    default_vibrate_timings=True,
                ),
            ),
        )
        try:
            message_id = messaging.send(message)
            success_count += 1
            tickets.append({"token": token, "message_id": message_id, "status": "ok"})
        except Exception as e:
            error_text = str(e)
            errors.append({"token": token, "error": error_text})
            lowered = error_text.lower()
            if any(x in lowered for x in ("unregistered", "registration-token-not-registered", "not found")):
                try:
                    unregister_push_token(token)
                except Exception:
                    pass

    _save_notification_log({
        "provider": "fcm",
        "title": title,
        "body": body,
        "data": data or {},
        "token_count": len(tokens),
        "sent_count": success_count,
        "errors": errors,
        "status": "sent" if success_count else "failed",
    })

    return {
        "success": len(errors) == 0,
        "sent": success_count,
        "attempted": len(tokens),
        "tickets": tickets,
        "errors": errors,
    }


def _tenant_inbox(tenant_id: str, title: str, body: str, data: Optional[dict], scope: str):
    payload_data = dict(data or {})
    payload_data.setdefault("scope", scope)
    payload_data.setdefault("target", "tenant" if scope == "private" else "all_tenants")
    try:
        firestore_db.collection("tenant_notifications").add({
            "tenant_id": str(tenant_id),
            "title": title,
            "body": body,
            "data": payload_data,
            "scope": scope,
            "read": False,
            "created_at": _utc_now(),
        })
    except Exception as e:
        print(f"[notify] tenant inbox save failed for {tenant_id}: {e}")


def _get_room_context(room_id: str):
    room_doc = firestore_db.collection("rooms").document(str(room_id)).get()
    room = room_doc.to_dict() if room_doc.exists else {}
    room = room or {}
    room_name = room.get("room_name") or str(room_id)
    tenant_id = room.get("tenant_id")
    if not tenant_id:
        contracts = (
            firestore_db.collection("contracts")
            .where("room_id", "==", str(room_id))
            .where("status", "==", "active")
            .limit(1)
            .stream()
        )
        for contract in contracts:
            tenant_id = (contract.to_dict() or {}).get("tenant_id")
            break
    return room_name, str(tenant_id) if tenant_id else None


def notify_landlords(title: str, body: str, data: Optional[dict] = None):
    payload = {"scope": "global", "target": "landlords", **(data or {})}
    return send_expo_push(get_all_landlord_tokens(), title, body, data=payload, channel_id="alerts")


def notify_tenant(tenant_id: str, title: str, body: str, data: Optional[dict] = None):
    if not tenant_id:
        return {"success": False, "message": "No tenant_id"}
    payload = {"scope": "private", "target": "tenant", "tenant_id": str(tenant_id), **(data or {})}
    _tenant_inbox(str(tenant_id), title, body, payload, "private")
    return send_expo_push(get_tokens_for_tenant(str(tenant_id)), title, body, data=payload, channel_id="admin")


def notify_all_tenants(title: str, body: str, data: Optional[dict] = None):
    """Push to all active tenant devices and save a history item for every active tenant."""
    payload = {"scope": "global", "target": "all_tenants", **(data or {})}
    tenant_ids = []
    try:
        for doc in firestore_db.collection("tenants").where("status", "==", "active").stream():
            tenant_ids.append(str(doc.id))
    except Exception as e:
        print(f"[notify] tenant list lookup failed: {e}")

    for tenant_id in tenant_ids:
        _tenant_inbox(tenant_id, title, body, payload, "global")

    return send_expo_push(get_all_tenant_tokens(), title, body, data=payload, channel_id="admin")


def notify_alert(room_id: str, alert_type: str, message: str, value=None):
    room_name, tenant_id = _get_room_context(room_id)
    title = f"Cảnh báo {alert_type}"
    body = f"Phòng {room_name}: {message}"
    if value is not None:
        body += f" ({value})"
    base = {
        "type": "alert",
        "alert_type": alert_type,
        "room_id": str(room_id),
        "room_name": room_name,
        "value": value,
    }
    landlord_result = notify_landlords(title, body, data=base)
    tenant_result = None
    if tenant_id:
        tenant_result = notify_tenant(tenant_id, title, body, data={**base, "scope": "private", "target": "room_tenant"})
    return {"landlords": landlord_result, "tenant": tenant_result, "room_id": str(room_id), "room_name": room_name}


def notify_power_change(room_id: str, switch_on: bool, reason: str = None):
    room_name, tenant_id = _get_room_context(room_id)
    action = "BẬT" if switch_on else "NGẮT"
    verb = "bật" if switch_on else "ngắt"
    title = f"Nguồn điện {action}"
    body = f"Phòng {room_name} đã được {verb} nguồn"
    if reason:
        body += f" — {reason}"
    base = {
        "type": "power",
        "room_id": str(room_id),
        "room_name": room_name,
        "switch": switch_on,
        "reason": reason,
    }
    landlord_result = notify_landlords(title, body, data=base)
    tenant_result = None
    if tenant_id:
        tenant_result = notify_tenant(tenant_id, title, body, data={**base, "scope": "private", "target": "room_tenant"})
    return {"landlords": landlord_result, "tenant": tenant_result, "room_id": str(room_id), "room_name": room_name}


def notify_bill_generated(tenant_id: str, room_id: str, period: str, total_cost):
    if not tenant_id:
        return {"success": False, "message": "No tenant_id"}
    room_name, _ = _get_room_context(room_id)
    title = "Hóa đơn mới"
    body = f"Phòng {room_name} kỳ {period}: {int(total_cost):,} ₫".replace(",", ".")
    return notify_tenant(
        tenant_id,
        title,
        body,
        data={"type": "bill", "room_id": str(room_id), "room_name": room_name, "period": period, "total_cost": total_cost},
    )
