"""认证流程测试 — 单用户登录 / 刷新 / me。"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user):
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "test@example.com", "password": "testpass123"},
    )
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user):
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "test@example.com", "password": "wrongpassword"},
    )
    assert resp.status_code in (401, 400)


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_invalid_token_returns_401_not_400(client: AsyncClient):
    """JWT 解析失败应返回 401（让前端自动 refresh），不是 400。

    回归：之前 AppException handler 把所有 AppError 都映射成 400，导致 token
    过期被识别成"参数错误"，前端 api.js 只对 401 触发 refresh，结果死循环刷屏。
    """
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401, f"Got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_register_endpoint_removed(client: AsyncClient):
    """/auth/register 应已删除"""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "x@y.com", "password": "Password123", "name": "x"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_2fa_endpoints_removed(client: AsyncClient, auth_headers):
    """所有 /auth/2fa/* 与 /auth/login-2fa 应已删除"""
    for path in (
        "/api/v1/auth/2fa/setup",
        "/api/v1/auth/2fa/verify",
        "/api/v1/auth/2fa/disable",
        "/api/v1/auth/2fa/status",
        "/api/v1/auth/login-2fa",
    ):
        resp = await client.post(path, headers=auth_headers, json={"code": "123456"})
        assert resp.status_code == 404, f"{path} should be 404, got {resp.status_code}"


@pytest.mark.asyncio
async def test_setup_endpoints_removed(client: AsyncClient):
    """/api/v1/setup/* 与 /web/setup 应已删除"""
    for path in (
        "/api/v1/setup/status",
        "/api/v1/setup/env-defaults",
        "/web/setup",
    ):
        resp = await client.get(path)
        assert resp.status_code == 404, f"{path} should be 404, got {resp.status_code}"
