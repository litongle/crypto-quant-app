"""
安全模块 - 认证、授权、加密

改动：不再模块级缓存 settings，改为函数内取 get_settings()
"""

import base64
import hashlib
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.config import get_settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    # P3-5: 安全截断，不丢弃字符 — 先按 UTF-8 字节截断再用 surrogateescape 防丢失
    raw = plain_password.encode("utf-8", errors="surrogateescape")[:72]
    return bcrypt.checkpw(raw, hashed_password.encode("utf-8"))


def hash_password(password: str) -> str:
    """哈希密码（bcrypt 限制 72 字节，按 UTF-8 字节截断）"""
    # P3-5: 安全截断，不丢弃字符
    raw = password.encode("utf-8", errors="surrogateescape")[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """创建访问令牌"""
    settings = get_settings()
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)

    to_encode.update(
        {
            "exp": expire,
            "type": "access",
        }
    )

    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """创建刷新令牌

    每次签发携带唯一 jti,refresh_tokens() 在 rotation 时把旧 jti 写入
    Redis revocation set,即便 refresh token 被偷,被偷的那枚也只能用一次。
    """
    settings = get_settings()
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)

    to_encode.update(
        {
            "exp": expire,
            "type": "refresh",
            "jti": uuid.uuid4().hex,
        }
    )

    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict[str, Any]:
    """解码令牌"""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e


def verify_token(token: str, token_type: str = "access") -> dict[str, Any]:
    """验证令牌"""
    payload = decode_token(token)

    if payload.get("type") != token_type:
        raise ValueError(f"Expected {token_type} token")

    return payload


# ============ API Key 加密存储 (AES-256) ============

_FERNET_V2_PREFIX = "v2:"


def _get_encryption_key() -> bytes:
    """从 SECRET_KEY + JWT_SECRET_KEY 派生带盐 Fernet 密钥。"""
    settings = get_settings()
    salt = hashlib.sha256(settings.jwt_secret_key.encode()).digest()
    key_material = hashlib.pbkdf2_hmac(
        "sha256",
        settings.secret_key.encode(),
        salt,
        200_000,
        dklen=32,
    )
    return base64.urlsafe_b64encode(key_material)


def _get_legacy_encryption_key() -> bytes:
    """兼容历史无盐密钥派生。"""
    settings = get_settings()
    key_material = hashlib.sha256(settings.secret_key.encode()).digest()
    return base64.urlsafe_b64encode(key_material)


def encrypt_api_key(plaintext: str) -> str:
    """加密 API Key/Secret

    使用 AES-256 (Fernet) 加密敏感字段，返回 base64 编码的密文。
    """
    if not plaintext:
        return ""
    f = Fernet(_get_encryption_key())
    ciphertext = f.encrypt(plaintext.encode()).decode()
    return f"{_FERNET_V2_PREFIX}{ciphertext}"


def decrypt_api_key(ciphertext: str) -> str:
    """解密 API Key/Secret

    解密 Fernet 加密的字段，返回明文。
    """
    if not ciphertext:
        return ""
    if ciphertext.startswith(_FERNET_V2_PREFIX):
        f = Fernet(_get_encryption_key())
        payload = ciphertext.removeprefix(_FERNET_V2_PREFIX)
        return f.decrypt(payload.encode()).decode()
    legacy = Fernet(_get_legacy_encryption_key())
    return legacy.decrypt(ciphertext.encode()).decode()


@contextmanager
def decrypted_api_keys(account: Any):
    """上下文管理器：解密 API Key 并确保使用后清理 (P1-12)

    虽然 Python 的内存管理无法保证绝对清理，但通过此模式可以最小化明文在变量作用域中的存活时间。
    """
    api_key = account.get_api_key()
    secret_key = account.get_secret_key()
    passphrase = (
        account.get_passphrase() if getattr(account, "encrypted_passphrase", None) else None
    )

    try:
        yield api_key, secret_key, passphrase
    finally:
        # 尝试显式清理明文（虽然对 Python 字符串效果有限，但作为防御性编程）
        del api_key
        del secret_key
        del passphrase
