import hmac
import hashlib

def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def hmac_sha256_upper(text, secret):
    encode = hmac.new(
        secret.encode("utf-8"),
        text.encode("utf-8"),
        hashlib.sha256
    )
    return encode.hexdigest().upper()