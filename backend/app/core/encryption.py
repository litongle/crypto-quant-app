"""敏感配置字段的对称加密工具。

key 派生自 JWT_SECRET_KEY（HKDF-SHA256），不引入新的引导级 secret。
注意：JWT_SECRET_KEY 变更会让已加密的字段全部失效，需要在前端重新填写。
"""

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings


def _derive_fernet_key() -> bytes:
    secret = get_settings().jwt_secret_key.encode("utf-8")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"crypto-quant-runtime-config",
        info=b"fernet-key-v1",
    )
    return base64.urlsafe_b64encode(hkdf.derive(secret))


def encrypt_secret(plaintext: str) -> str:
    """加密为 Fernet token 字符串。"""
    return Fernet(_derive_fernet_key()).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    """解密 token；key 不匹配或 token 损坏抛 InvalidToken。"""
    return Fernet(_derive_fernet_key()).decrypt(token.encode("ascii")).decode("utf-8")
