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


# ============ HttpOnly cookie 流程回归(防止后续误改无声破窗) ============


@pytest.mark.asyncio
async def test_login_sets_httponly_cookies(client: AsyncClient, test_user):
    """登录应通过 Set-Cookie 下发 access/refresh,带 HttpOnly + SameSite=Strict"""
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "test@example.com", "password": "testpass123"},
    )
    assert resp.status_code == 200

    set_cookies = resp.headers.get_list("set-cookie")
    access = next((c for c in set_cookies if c.lower().startswith("access_token=")), None)
    refresh = next((c for c in set_cookies if c.lower().startswith("refresh_token=")), None)
    assert access is not None, f"missing access_token cookie in {set_cookies}"
    assert refresh is not None, f"missing refresh_token cookie in {set_cookies}"

    # HttpOnly + SameSite=Strict 是核心安全约束,不能漏
    assert "HttpOnly" in access
    assert "samesite=strict" in access.lower()
    assert "HttpOnly" in refresh
    assert "samesite=strict" in refresh.lower()

    # refresh cookie 必须收窄到 /api/v1/auth,业务接口不应该自动带它
    assert "path=/api/v1/auth" in refresh.lower()

    # body 不应再包含 token (上轮 cookie 改造去掉)
    body = resp.json()
    data = body.get("data", body)
    assert "access_token" not in data
    assert "refresh_token" not in data


@pytest.mark.asyncio
async def test_refresh_via_cookie(client: AsyncClient, test_user):
    """登录后再调 /refresh — 不传 body,服务端从 cookie 读 refresh_token"""
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "test@example.com", "password": "testpass123"},
    )
    assert login.status_code == 200

    # AsyncClient 自动保存 cookies → refresh 调用会自动带 refresh_token cookie
    refresh = await client.post("/api/v1/auth/refresh")
    assert refresh.status_code == 200, f"got {refresh.status_code}: {refresh.text}"

    # 应下发新的 access + refresh cookie
    set_cookies = refresh.headers.get_list("set-cookie")
    assert any(c.lower().startswith("access_token=") for c in set_cookies)
    assert any(c.lower().startswith("refresh_token=") for c in set_cookies)


@pytest.mark.asyncio
async def test_logout_clears_cookies(client: AsyncClient, test_user):
    """登出应通过 Set-Cookie 清掉 access + refresh,path 与下发时一致"""
    await client.post(
        "/api/v1/auth/login",
        data={"username": "test@example.com", "password": "testpass123"},
    )
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 200

    # delete_cookie 通过 Set-Cookie: name=""; Max-Age=0 实现
    set_cookies = resp.headers.get_list("set-cookie")
    cleared_access = any(
        c.lower().startswith("access_token=")
        and ("max-age=0" in c.lower() or 'access_token=""' in c.lower() or "expires=" in c.lower())
        for c in set_cookies
    )
    cleared_refresh = any(
        c.lower().startswith("refresh_token=")
        and ("max-age=0" in c.lower() or 'refresh_token=""' in c.lower() or "expires=" in c.lower())
        for c in set_cookies
    )
    assert cleared_access, f"access_token not cleared in {set_cookies}"
    assert cleared_refresh, f"refresh_token not cleared in {set_cookies}"


@pytest.mark.asyncio
async def test_refresh_token_single_use(client: AsyncClient, test_user):
    """refresh token rotation:一枚 refresh 用过一次就废,防被偷复用。

    Redis 必须可用 (测试 docker compose 内的 Redis on 6379/15)。
    Redis 不可用时该测试会跳过 (revocation 降级放行,行为期望不一致)。
    """
    # 跨 test 复用的 Redis 单例可能绑定了旧 event loop;直接清空 module 状态,
    # 让下一次 get_redis_client() 在当前 loop 重建。await close 会因为旧 loop 已关而抛,
    # 所以这里不 await,只把引用 set None 让 GC 慢慢回收旧资源。
    import app.redis as redis_mod

    redis_mod._redis_client = None
    redis_mod._pool = None

    try:
        r = await redis_mod.get_redis_client()
        await r.ping()
    except Exception:
        pytest.skip("Redis 不可用,跳过 refresh rotation 测试")

    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "test@example.com", "password": "testpass123"},
    )
    assert login.status_code == 200
    old_refresh = client.cookies.get("refresh_token")
    assert old_refresh, "should have refresh_token cookie after login"

    # 第一次 refresh — 正常,服务端会 revoke old_refresh 的 jti 并下发新 refresh
    first = await client.post("/api/v1/auth/refresh")
    assert first.status_code == 200
    new_refresh = client.cookies.get("refresh_token")
    assert new_refresh is not None, "rotation should issue a new refresh cookie"
    assert new_refresh != old_refresh, "rotation should issue a different refresh value"

    # 模拟"被偷的旧 token 拿来重放":绕过 client 的 cookie jar(已被新值覆盖),
    # 直接通过 Cookie header 显式发旧值,验证服务端能识别并拒绝。
    second = await client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"refresh_token={old_refresh}"},
    )
    assert (
        second.status_code == 401
    ), f"old refresh should be revoked after rotation, got {second.status_code}: {second.text}"
