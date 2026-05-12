"""RuntimeConfig 模型基础测试。"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.runtime_config import RuntimeConfig


@pytest.mark.asyncio
async def test_runtime_config_insert_and_query(db_session):
    db_session.add(RuntimeConfig(key="TEST_KEY", value="abc", is_encrypted=False))
    await db_session.commit()

    result = await db_session.execute(select(RuntimeConfig).where(RuntimeConfig.key == "TEST_KEY"))
    row = result.scalar_one()
    assert row.value == "abc"
    assert row.is_encrypted is False
    assert row.updated_at is not None


@pytest.mark.asyncio
async def test_runtime_config_primary_key_unique(db_session):
    db_session.add(RuntimeConfig(key="DUP", value="v1"))
    await db_session.commit()
    db_session.add(RuntimeConfig(key="DUP", value="v2"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
