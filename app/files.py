import time
import hmac
import hashlib
import base64
import json
from flask import current_app
from urllib.parse import quote_plus, unquote_plus

_SECRET_KEY_ENV = 'SECRET_KEY'

def _get_secret():
    # Prefer app config SECRET_KEY if available
    try:
        return current_app.config.get('SECRET_KEY') or current_app.secret_key
    except Exception:
        # Fallback to environment handling (should not normally be hit under app context)
        import os
        return os.environ.get(_SECRET_KEY_ENV, '')

def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')

def _b64_decode(s: str) -> bytes:
    # Add padding
    padding = '=' * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode((s + padding).encode('ascii'))

def create_signed_token(filename: str, ttl_seconds: int = 1800) -> str:
    """
    Create a signed token for `filename` valid for ttl_seconds.
    Token format: <b64(payload)>.<hex_hmac>
    payload = JSON bytes: {"filename": "<filename>", "exp": <unix_ts>}
    """
    secret = _get_secret().encode('utf-8')
    exp = int(time.time()) + int(ttl_seconds)
    payload = json.dumps({'filename': filename, 'exp': exp}, separators=(',', ':')).encode('utf-8')
    payload_b64 = _b64_encode(payload)
    sig = hmac.new(secret, payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
    token = f"{payload_b64}.{sig}"
    return token

def verify_signed_token(token: str) -> dict | None:
    """
    Verify the token. Returns payload dict if valid and not expired, otherwise None.
    """
    try:
        secret = _get_secret().encode('utf-8')
        parts = token.split('.')
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        expected_sig = hmac.new(secret, payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
        # Use constant-time comparison
        if not hmac.compare_digest(expected_sig, sig):
            return None
        payload_bytes = _b64_decode(payload_b64)
        payload = json.loads(payload_bytes.decode('utf-8'))
        if 'filename' not in payload or 'exp' not in payload:
            return None
        if int(time.time()) > int(payload['exp']):
            return None
        return payload
    except Exception:
        return None

def get_signed_url_for(filename: str, ttl_seconds: int = 1800, host_url: str | None = None) -> str:
    """
    Return a relative signed URL for the file. If host_url is provided, returns an absolute URL.
    """
    token = create_signed_token(filename, ttl_seconds=ttl_seconds)
    path = f"/files/{quote_plus(filename)}?token={token}"
    if host_url:
        return host_url.rstrip('/') + path
    return path
