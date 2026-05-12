"""加密工具测试 — Fernet+HKDF。"""

from unittest.mock import MagicMock

import pytest
from cryptography.fernet import InvalidToken

from app.core.encryption import decrypt_secret, encrypt_secret


@pytest.fixture
def fake_settings(monkeypatch):
    """让 encryption 模块拿到可控的 jwt_secret_key。"""

    def _set(secret: str):
        monkeypatch.setattr(
            "app.core.encryption.get_settings",
            lambda: MagicMock(jwt_secret_key=secret),
        )

    return _set


def test_encrypt_decrypt_round_trip(fake_settings):
    fake_settings("a" * 64)
    cipher = encrypt_secret("hello world")
    assert cipher != "hello world"
    assert decrypt_secret(cipher) == "hello world"


def test_encrypt_unicode(fake_settings):
    fake_settings("b" * 64)
    assert decrypt_secret(encrypt_secret("中文密钥 🔐")) == "中文密钥 🔐"


def test_decrypt_with_wrong_key_raises(fake_settings):
    fake_settings("k1" * 32)
    cipher = encrypt_secret("secret")
    fake_settings("k2" * 32)
    with pytest.raises(InvalidToken):
        decrypt_secret(cipher)


def test_encrypt_empty_string(fake_settings):
    fake_settings("x" * 64)
    assert decrypt_secret(encrypt_secret("")) == ""


def test_encryption_is_deterministic_with_same_key_different_calls(fake_settings):
    """Fernet 用随机 IV，密文每次不同，但都能解回原文。"""
    fake_settings("same-secret-key-1234567890" * 2)
    c1 = encrypt_secret("payload")
    c2 = encrypt_secret("payload")
    assert c1 != c2  # IV 随机
    assert decrypt_secret(c1) == "payload"
    assert decrypt_secret(c2) == "payload"
