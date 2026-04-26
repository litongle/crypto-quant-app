"""
配置模块测试 — 生产环境安全校验（P0-1）
"""
import pytest
from unittest.mock import patch
import sys


class TestProductionSecurity:
    """P0-1: 生产环境安全校验测试"""

    def test_dev_env_allows_default_keys(self):
        """开发环境允许默认密钥"""
        from app.config import Settings
        settings = Settings(
            environment="development",
            secret_key="dev-secret-key-change-me",
            jwt_secret_key="dev-jwt-secret-key-change-me",
        )
        # 不应抛异常
        settings.validate_production_secrets()
        assert settings.is_production is False

    def test_prod_env_rejects_default_secret_key(self):
        """生产环境拒绝默认 secret_key"""
        from app.config import Settings, _DEFAULT_SECRET_KEY, _DEFAULT_JWT_SECRET_KEY
        settings = Settings(
            environment="production",
            secret_key=_DEFAULT_SECRET_KEY,  # 默认值
            jwt_secret_key="real-jwt-key-here-at-least-32-chars",
        )
        with pytest.raises(SystemExit):
            settings.validate_production_secrets()

    def test_prod_env_rejects_default_jwt_key(self):
        """生产环境拒绝默认 jwt_secret_key"""
        from app.config import Settings, _DEFAULT_SECRET_KEY, _DEFAULT_JWT_SECRET_KEY
        settings = Settings(
            environment="production",
            secret_key="real-secret-key-here-at-least-32-chars",
            jwt_secret_key=_DEFAULT_JWT_SECRET_KEY,  # 默认值
        )
        with pytest.raises(SystemExit):
            settings.validate_production_secrets()

    def test_prod_env_rejects_debug_true(self):
        """生产环境拒绝 debug=True"""
        from app.config import Settings
        settings = Settings(
            environment="production",
            secret_key="real-secret-key-here-at-least-32-chars",
            jwt_secret_key="real-jwt-key-here-at-least-32-chars",
            debug=True,
        )
        with pytest.raises(SystemExit):
            settings.validate_production_secrets()

    def test_prod_env_accepts_valid_config(self):
        """生产环境接受合法配置"""
        from app.config import Settings
        settings = Settings(
            environment="production",
            secret_key="real-secret-key-here-at-least-32-chars",
            jwt_secret_key="real-jwt-key-here-at-least-32-chars",
            debug=False,
        )
        # 不应抛异常
        settings.validate_production_secrets()
        assert settings.is_production is True

    def test_staging_is_production(self):
        """staging 环境也视为生产"""
        from app.config import Settings
        settings = Settings(environment="staging")
        assert settings.is_production is True

    def test_debug_default_false(self):
        """P0-2: debug 默认值为 False"""
        from app.config import Settings
        settings = Settings()
        assert settings.debug is False
