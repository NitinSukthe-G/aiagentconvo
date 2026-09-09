import hashlib
import hmac

from app.whatsapp.client import verify_signature

APP_SECRET = "test-app-secret"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_accepted():
    body = b'{"hello": "world"}'
    assert verify_signature(APP_SECRET, body, _sign(body)) is True


def test_tampered_body_rejected():
    body = b'{"hello": "world"}'
    signature = _sign(body)
    tampered = b'{"hello": "mallory"}'
    assert verify_signature(APP_SECRET, tampered, signature) is False


def test_missing_header_rejected():
    assert verify_signature(APP_SECRET, b"{}", None) is False


def test_malformed_header_rejected():
    assert verify_signature(APP_SECRET, b"{}", "not-a-real-signature") is False
