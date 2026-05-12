import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.trade_schemas import TradingSymbolRulesSchema
from app.models.exchange import ExchangeAccount


@pytest.mark.asyncio
async def test_risk_dashboard_paper_accounts_and_account_detail(
    client: AsyncClient,
    auth_headers,
    test_user,
    db_session: AsyncSession,
):
    risk_resp = await client.get("/api/v1/asset/risk-dashboard", headers=auth_headers)
    assert risk_resp.status_code == 200, risk_resp.text
    risk_data = risk_resp.json()["data"]
    assert "exposurePercent" in risk_data
    assert "alerts" in risk_data

    create_paper_resp = await client.post("/api/v1/asset/paper-account", headers=auth_headers)
    assert create_paper_resp.status_code == 200, create_paper_resp.text

    list_paper_resp = await client.get("/api/v1/asset/paper-accounts", headers=auth_headers)
    assert list_paper_resp.status_code == 200, list_paper_resp.text
    paper_accounts = list_paper_resp.json()["data"]
    assert len(paper_accounts) >= 1
    assert paper_accounts[0]["isPaper"] is True

    reset_paper_resp = await client.post(
        f"/api/v1/asset/paper-account/{paper_accounts[0]['id']}/reset",
        headers=auth_headers,
    )
    assert reset_paper_resp.status_code == 200, reset_paper_resp.text

    account = ExchangeAccount(
        user_id=test_user.id,
        exchange="binance",
        account_name="Primary",
        is_active=True,
        status="active",
        balance="1234.56",
        frozen_balance="12.34",
    )
    account.set_api_key("test-api-key-123456")
    account.set_secret_key("test-secret-key-123456")
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    account_detail_resp = await client.get(
        f"/api/v1/trading/accounts/{account.id}",
        headers=auth_headers,
    )
    assert account_detail_resp.status_code == 200, account_detail_resp.text
    account_detail = account_detail_resp.json()["data"]
    assert account_detail["accountName"] == "Primary"
    assert account_detail["balance"].startswith("1234.56")
    assert account_detail["isPaper"] is False

@pytest.mark.asyncio
async def test_market_symbols_and_orderbook_endpoints(
    client: AsyncClient,
    auth_headers,
    monkeypatch,
):
    async def fake_get_orderbook(self, symbol, limit=20, exchange="binance", market_type="spot"):
        assert symbol == "BTCUSDT"
        assert exchange == "binance"
        assert market_type == "spot"
        return {
            "bids": [
                {"price": "65000.1", "quantity": "1.25"},
                {"price": "64999.9", "quantity": "2.10"},
            ],
            "asks": [
                {"price": "65000.5", "quantity": "0.85"},
                {"price": "65001.0", "quantity": "1.40"},
            ],
        }

    monkeypatch.setattr(
        "app.api.v1.market.MarketService.get_orderbook",
        fake_get_orderbook,
    )

    symbols_resp = await client.get("/api/v1/market/symbols", headers=auth_headers)
    assert symbols_resp.status_code == 200, symbols_resp.text
    symbols_data = symbols_resp.json()["data"]
    assert "BTCUSDT" in symbols_data["symbols"]
    assert symbols_data["count"] >= 1

    orderbook_resp = await client.get(
        "/api/v1/market/orderbook/BTCUSDT?exchange=binance&market=spot&limit=12",
        headers=auth_headers,
    )
    assert orderbook_resp.status_code == 200, orderbook_resp.text
    orderbook_data = orderbook_resp.json()["data"]
    assert orderbook_data["bids"][0]["price"] == "65000.1"
    assert orderbook_data["asks"][0]["quantity"] == "0.85"


@pytest.mark.asyncio
async def test_manual_trading_symbol_rules_endpoint(
    client: AsyncClient,
    auth_headers,
    test_user,
    db_session: AsyncSession,
    monkeypatch,
):
    account = ExchangeAccount(
        user_id=test_user.id,
        exchange="okx",
        account_name="Rules Account",
        is_active=True,
        status="active",
        balance="5000",
        frozen_balance="0",
    )
    account.set_api_key("test-api-key-123456")
    account.set_secret_key("test-secret-key-123456")
    account.set_passphrase("test-passphrase")
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)

    async def fake_get_symbol_rules(self, *, user_id, account_id, symbol):
        assert user_id == test_user.id
        assert account_id == account.id
        assert symbol == "BTCUSDT.P"
        return TradingSymbolRulesSchema(
            symbol="BTCUSDT.P",
            baseSymbol="BTCUSDT",
            exchangeSymbol="BTC-USDT-SWAP",
            exchange="okx",
            marketType="perp",
            quantityUnit="cont",
            quantityLabel="数量 (张)",
            sideMode="contract",
            minQty="0.01",
            stepSize="0.01",
            minNotional="1",
            tickSize="0.1",
        )

    monkeypatch.setattr(
        "app.api.v1.orders.OrderService.get_symbol_rules",
        fake_get_symbol_rules,
    )

    resp = await client.get(
        f"/api/v1/trading/symbol-rules?account_id={account.id}&symbol=BTCUSDT.P",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["marketType"] == "perp"
    assert data["quantityLabel"] == "数量 (张)"
    assert data["exchangeSymbol"] == "BTC-USDT-SWAP"


@pytest.mark.asyncio
async def test_trading_accounts_include_paper_and_contract_settings_endpoint(
    client: AsyncClient,
    auth_headers,
    test_user,
    db_session: AsyncSession,
    monkeypatch,
):
    paper_account = ExchangeAccount(
        user_id=test_user.id,
        exchange="binance",
        account_name="Paper Manual",
        is_active=True,
        is_paper=True,
        status="active",
        balance="100000",
        frozen_balance="0",
        balances={"USDT": "100000"},
        contract_settings={"BTCUSDT.P": {"leverage": 8, "margin_mode": "isolated"}},
    )
    paper_account.set_api_key("test-api-key-123456")
    paper_account.set_secret_key("test-secret-key-123456")
    db_session.add(paper_account)
    await db_session.commit()
    await db_session.refresh(paper_account)

    accounts_resp = await client.get(
        "/api/v1/trading/accounts?include_paper=true",
        headers=auth_headers,
    )
    assert accounts_resp.status_code == 200, accounts_resp.text
    accounts = accounts_resp.json()["data"]
    assert any(item["id"] == paper_account.id and item["isPaper"] for item in accounts)

    settings_resp = await client.get(
        f"/api/v1/trading/accounts/{paper_account.id}/contract-settings?symbol=BTCUSDT.P",
        headers=auth_headers,
    )
    assert settings_resp.status_code == 200, settings_resp.text
    settings = settings_resp.json()["data"]
    assert settings["leverage"] == 8
    assert settings["margin_mode"] == "isolated"

    async def fake_update_contract_settings(
        self, *, user_id, account_id, symbol, leverage, margin_mode
    ):
        assert user_id == test_user.id
        assert account_id == paper_account.id
        assert symbol == "BTCUSDT.P"
        assert leverage == 12
        assert margin_mode == "cross"
        return {
            "account_id": account_id,
            "symbol": symbol,
            "leverage": leverage,
            "margin_mode": margin_mode,
            "is_paper": True,
        }

    monkeypatch.setattr(
        "app.api.v1.orders.OrderService.update_contract_settings",
        fake_update_contract_settings,
    )

    update_resp = await client.post(
        f"/api/v1/trading/accounts/{paper_account.id}/contract-settings",
        headers=auth_headers,
        json={
            "symbol": "BTCUSDT.P",
            "leverage": 12,
            "marginMode": "cross",
        },
    )
    assert update_resp.status_code == 200, update_resp.text
    update_data = update_resp.json()["data"]
    assert update_data["leverage"] == 12
    assert update_data["margin_mode"] == "cross"
