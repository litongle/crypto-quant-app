"""
安全模块测试 — 密码哈希/JWT/加密
"""
import pytest
from app.core.security import (
    verify_password,
    hash_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    encrypt_api_key,
    decrypt_api_key,
)


class TestPasswordHashing:
    """密码哈希测试"""

    def test_hash_and_verify(self):
        """正常密码验证"""
        hashed = hash_password("MySecurePassword123")
        assert verify_password("MySecurePassword123", hashed)

    def test_wrong_password(self):
        """错误密码验证"""
        hashed = hash_password("MySecurePassword123")
        assert not verify_password("WrongPassword", hashed)

    def test_empty_password(self):
        """空密码"""
        hashed = hash_password("")
        assert verify_password("", hashed)

    def test_long_password_truncation(self):
        """超长密码截断（bcrypt 72字节限制，P3-5 修复验证）"""
        # 100 字节的中文密码
        long_pw = "密码" * 50  # 每个中文字符3字节 UTF-8
        hashed = hash_password(long_pw)
        # 截断后的密码也能验证通过
        assert verify_password(long_pw, hashed)

    def test_unicode_password(self):
        """Unicode 密码"""
        pw = "我的密码🔐🔑"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed)


class TestJWTTokens:
    """JWT Token 测试"""

    def test_create_access_token(self):
        """创建访问令牌"""
        token = create_access_token({"sub": "1"})
        assert isinstance(token, str)
        assert len(token) > 20

    def test_create_refresh_token(self):
        """创建刷新令牌"""
        token = create_refresh_token({"sub": "1"})
        assert isinstance(token, str)

    def test_verify_access_token(self):
        """验证访问令牌"""
        token = create_access_token({"sub": "42"})
        payload = verify_token(token, token_type="access")
        assert payload["sub"] == "42"
        assert payload["type"] == "access"

    def test_verify_refresh_token(self):
        """验证刷新令牌"""
        token = create_refresh_token({"sub": "42"})
        payload = verify_token(token, token_type="refresh")
        assert payload["sub"] == "42"
        assert payload["type"] == "refresh"

    def test_token_type_mismatch(self):
        """令牌类型不匹配"""
        token = create_access_token({"sub": "1"})
        with pytest.raises(ValueError, match="Expected refresh token"):
            verify_token(token, token_type="refresh")

    def test_invalid_token(self):
        """无效令牌"""
        with pytest.raises(ValueError):
            verify_token("invalid.token.here", token_type="access")


class TestAPIKeyEncryption:
    """API Key 加密存储测试"""

    def test_encrypt_decrypt(self):
        """加密解密循环"""
        original = "my-secret-api-key-12345"
        encrypted = encrypt_api_key(original)
        assert encrypted != original
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == original

    def test_empty_string(self):
        """空字符串加密"""
        assert encrypt_api_key("") == ""
        assert decrypt_api_key("") == ""

    def test_different_keys_produce_different_ciphertext(self):
        """不同明文产生不同密文"""
        ct1 = encrypt_api_key("key1")
        ct2 = encrypt_api_key("key2")
        assert ct1 != ct2

    def test_same_key_produces_different_ciphertext(self):
        """相同明文每次加密结果不同（Fernet 使用随机 IV）"""
        ct1 = encrypt_api_key("same-key")
        ct2 = encrypt_api_key("same-key")
        assert ct1 != ct2  # Fernet 随机 IV
        assert decrypt_api_key(ct1) == decrypt_api_key(ct2)
