"""
安全模块 - 认证、授权、加密

改动：不再模块级缓存 settings，改为函数内取 get_settings()
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

# 密码加密上下文（不依赖 settings，可以模块级缓存）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    # P3-5: 安全截断，不丢弃字符 — 先按 UTF-8 字节截断再用 surrogateescape 防丢失
    raw = plain_password.encode("utf-8", errors="surrogateescape")[:72]
    return pwd_context.verify(raw.decode("utf-8", errors="surrogateescape"), hashed_password)


def hash_password(password: str) -> str:
    """哈希密码（bcrypt 限制 72 字节，按 UTF-8 字节截断）"""
    # P3-5: 安全截断，不丢弃字符
    raw = password.encode("utf-8", errors="surrogateescape")[:72]
    return pwd_context.hash(raw.decode("utf-8", errors="surrogateescape"))


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """创建访问令牌"""
    settings = get_settings()
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode.update({
        "exp": expire,
        "type": "access",
    })

    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """创建刷新令牌"""
    settings = get_settings()
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.refresh_token_expire_days
        )

    to_encode.update({
        "exp": expire,
        "type": "refresh",
    })

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
        raise ValueError(f"Invalid token: {e}")


def verify_token(token: str, token_type: str = "access") -> dict[str, Any]:
    """验证令牌"""
    payload = decode_token(token)

    if payload.get("type") != token_type:
        raise ValueError(f"Expected {token_type} token")

    return payload


# ============ API Key 加密存储 (AES-256) ============

import base64
import hashlib

from cryptography.fernet import Fernet


def _get_encryption_key() -> bytes:
    """从 SECRET_KEY 派生 Fernet 加密密钥"""
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
    return f.encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    """解密 API Key/Secret

    解密 Fernet 加密的字段，返回明文。
    """
    if not ciphertext:
        return ""
    f = Fernet(_get_encryption_key())
    return f.decrypt(ciphertext.encode()).decode()
