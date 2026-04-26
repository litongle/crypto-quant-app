"""
认证流程测试 — 注册/登录/token验证
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    """正常注册"""
    resp = await client.post("/api/v1/auth/register", json={
        "name": "newuser",
        "email": "new@example.com",
        "password": "SecurePass123",
    })
    assert resp.status_code in (200, 201), f"Got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_register_password_too_short(client: AsyncClient):
    """密码太短应该被拒绝（P1-2: min_length=8）"""
    resp = await client.post("/api/v1/auth/register", json={
        "name": "shortpw",
        "email": "short@example.com",
        "password": "abc",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user):
    """正常登录（OAuth2 表单格式）"""
    resp = await client.post("/api/v1/auth/login", data={
        "username": "test@example.com",
        "password": "testpass123",
    })
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user):
    """密码错误"""
    resp = await client.post("/api/v1/auth/login", data={
        "username": "test@example.com",
        "password": "wrongpassword",
    })
    assert resp.status_code in (401, 400)


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient, auth_headers):
    """认证后获取用户信息"""
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    """未认证访问应被拒绝"""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)
