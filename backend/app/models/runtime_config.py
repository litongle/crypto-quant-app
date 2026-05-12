"""运行时配置表 — 承载所有前端可改的设置。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RuntimeConfig(Base):
    """运行时配置 key/value 表。

    敏感字段（如 token、密码）以 Fernet 密文存储，is_encrypted=True。
    其余字段明文存储。
    """

    __tablename__ = "runtime_config"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
