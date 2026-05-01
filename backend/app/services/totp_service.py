"""
TOTP 双因素认证服务 - P1-5

基于 pyotp 实现 TOTP 2FA:
- 生成密钥 + 二维码 URI
- 验证一次性密码
- 启用/禁用 2FA

用户模型新增字段:
- totp_secret: 加密存储的 TOTP 密钥
- totp_enabled: 是否启用 2FA
- totp_verified: 是否已验证 (防止设置一半)
"""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# AES 加密密钥缓存（从 settings.secret_key 派生，重启不变）
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """获取 Fernet 加密实例，密钥从 settings.secret_key 派生"""
    global _fernet
    if _fernet is not None:
        return _fernet
    from app.config import get_settings
    raw_key = get_settings().secret_key
    # 使用 sha256 将任意长度的 secret_key 转换为 32 字节密钥
    key_bytes = hashlib.sha256(raw_key.encode()).digest()
    _fernet = Fernet(base64.urlsafe_b64encode(key_bytes))
    return _fernet


def encrypt_totp_secret(plaintext: str) -> str:
    """加密 TOTP secret"""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_totp_secret(ciphertext: str) -> str:
    """解密 TOTP secret"""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()


async def generate_totp_secret(user_id: int, email: str) -> dict:
    """为用户生成新的 TOTP 密钥

    Returns:
        dict: {
            "secret": "base32_secret",
            "uri": "otpauth://totp/...",
            "qr_code": "data URI for QR code (optional)"
        }
    """
    import pyotp

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=email, issuer_name="CryptoQuant")

    return {
        "secret": secret,
        "uri": uri,
    }


async def verify_totp(secret: str, code: str) -> bool:
    """验证一次性密码

    Args:
        secret: base32 TOTP secret
        code: 用户输入的 6 位数字

    Returns:
        bool: 是否验证通过
    """
    import pyotp

    totp = pyotp.TOTP(secret)
    return totp.verify(code)


async def validate_code_format(code: str) -> bool:
    """验证码格式校验"""
    return code.isdigit() and len(code) == 6
