import json
import time
import requests
from services.hmac_sha256 import sha256, hmac_sha256_upper
from env import ENDPOINT, ACCESS_ID, ACCESS_KEY

def get_access_token():
    path = "/v1.0/token?grant_type=1"
    timestamp = str(int(time.time() * 1000))

    sign_url = f"GET\n{sha256('')}\n\n{path}"
    sign_str = f"{ACCESS_ID}{timestamp}{sign_url}"

    headers = {
        "client_id": ACCESS_ID,
        "t": timestamp,
        "sign": hmac_sha256_upper(sign_str, ACCESS_KEY),
        "sign_method": "HMAC-SHA256",
    }

    response = requests.get(
        ENDPOINT + path,
        headers=headers
    )

    data = response.json()

    # print("Token response:")
    # print(data)

    if not data.get("success"):
        raise Exception(f"Không lấy được token: {data}")

    return data["result"]["access_token"]