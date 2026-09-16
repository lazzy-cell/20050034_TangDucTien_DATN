import json
import time
import requests

from env import ACCESS_ID, ACCESS_KEY, ENDPOINT
from services.hmac_sha256 import sha256, hmac_sha256_upper


def get_device_info(access_token, device_id):
    """Lấy thông tin và trạng thái thiết bị Tuya theo device_id."""
    path = f"/v1.0/devices/{device_id}"
    method = "GET"
    body = ""
    timestamp = str(int(time.time() * 1000))
    body_hash = sha256(body)
    headers_str = ""

    sign_url = (
        f"{method}\n"
        f"{body_hash}\n"
        f"{headers_str}\n"
        f"{path}"
    )
    sign_str = (
        f"{ACCESS_ID}"
        f"{access_token}"
        f"{timestamp}"
        f"{sign_url}"
    )
    sign = hmac_sha256_upper(sign_str, ACCESS_KEY)

    headers = {
        "client_id": ACCESS_ID,
        "access_token": access_token,
        "t": timestamp,
        "sign": sign,
        "sign_method": "HMAC-SHA256",
    }

    response = requests.get(ENDPOINT + path, headers=headers)
    return response.json()


def send_device_command(access_token, device_id, body):
    """
    Gửi lệnh điều khiển tới thiết bị Tuya theo device_id.
    body ví dụ: {"commands": [{"code": "switch", "value": True}]}
    """
    if not device_id:
        raise ValueError("device_id is required")

    path = f"/v1.0/devices/{device_id}/commands"
    body_json = json.dumps(body, separators=(",", ":"))
    timestamp = str(int(time.time() * 1000))

    sign_url = (
        f"POST\n"
        f"{sha256(body_json)}\n"
        f"\n"
        f"{path}"
    )
    sign_str = (
        f"{ACCESS_ID}"
        f"{access_token}"
        f"{timestamp}"
        f"{sign_url}"
    )

    headers = {
        "client_id": ACCESS_ID,
        "access_token": access_token,
        "t": timestamp,
        "sign": hmac_sha256_upper(sign_str, ACCESS_KEY),
        "sign_method": "HMAC-SHA256",
        "Content-Type": "application/json",
    }

    response = requests.post(
        ENDPOINT + path,
        headers=headers,
        data=body_json,
        timeout=15,
    )
    return response.json()
