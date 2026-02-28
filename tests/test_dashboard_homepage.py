"""Tests for the dashboard homepage and related API endpoints."""

import pytest
from fastapi.testclient import TestClient

from tradeengine.dashboard.app import create_app
from tradeengine.strategies.registry import auto_discover


@pytest.fixture(scope="module")
def client():
    """Create a TestClient for the dashboard app."""
    auto_discover()
    app = create_app()
    return TestClient(app)


class TestHomepage:
    """Tests for GET / homepage."""

    def test_homepage_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_homepage_is_html(self, client):
        resp = client.get("/")
        assert "text/html" in resp.headers["content-type"]

    def test_homepage_contains_title(self, client):
        resp = client.get("/")
        assert "TradeEngine" in resp.text

    def test_homepage_contains_strategies(self, client):
        """Homepage should render available strategies in the selector."""
        resp = client.get("/")
        html = resp.text
        assert "ma_crossover" in html
        assert "rsi" in html
        assert "macd" in html
        assert "bollinger" in html

    def test_homepage_language_is_zh_tw(self, client):
        resp = client.get("/")
        assert 'lang="zh-TW"' in resp.text

    def test_homepage_contains_dashboard_title(self, client):
        resp = client.get("/")
        assert "儀表板" in resp.text

    def test_homepage_has_tab_navigation(self, client):
        """Homepage should have all 7 tabs."""
        html = client.get("/").text
        assert 'data-tab="backtest"' in html
        assert 'data-tab="optimize"' in html
        assert 'data-tab="bots"' in html
        assert 'data-tab="account"' in html
        assert 'data-tab="strategies"' in html
        assert 'data-tab="cache"' in html
        assert 'data-tab="guide"' in html

    def test_homepage_has_tab_content_panels(self, client):
        html = client.get("/").text
        assert 'id="tab-backtest"' in html
        assert 'id="tab-optimize"' in html
        assert 'id="tab-bots"' in html
        assert 'id="tab-account"' in html
        assert 'id="tab-strategies"' in html
        assert 'id="tab-cache"' in html
        assert 'id="tab-guide"' in html

    def test_guide_tab_has_tutorial_content(self, client):
        html = client.get("/").text
        assert "Pionex API" in html
        assert "模擬交易" in html
        assert "即時交易" in html

    def test_homepage_backtest_has_source_selector(self, client):
        html = client.get("/").text
        assert 'id="bt-source"' in html
        assert 'id="bt-sl"' in html
        assert 'id="bt-tp"' in html
        assert 'id="bt-capital"' in html


class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_ok(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"


class TestStrategyAPI:
    """Tests for strategy-related API endpoints."""

    def test_list_strategies(self, client):
        resp = client.get("/api/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 7
        names = [s["name"] for s in data]
        assert "ma_crossover" in names

    def test_strategy_detail(self, client):
        resp = client.get("/api/strategy/ma_crossover")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "ma_crossover"
        assert "parameters" in data
        assert len(data["parameters"]) > 0

    def test_strategy_detail_has_param_fields(self, client):
        resp = client.get("/api/strategy/rsi")
        data = resp.json()
        param = data["parameters"][0]
        assert "name" in param
        assert "default" in param
        assert "type" in param

    def test_strategy_not_found(self, client):
        resp = client.get("/api/strategy/nonexistent_strategy")
        assert resp.status_code == 404
        assert "error" in resp.json()


class TestAccountAPI:
    """Tests for account status endpoint."""

    def test_account_status(self, client):
        resp = client.get("/api/account/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "api_configured" in data
        assert isinstance(data["api_configured"], bool)


class TestCSVAPI:
    """Tests for CSV file discovery endpoint."""

    def test_csv_files_endpoint(self, client):
        resp = client.get("/api/csv-files")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_csv_file_structure(self, client):
        """If CSV files exist, they should have expected fields."""
        resp = client.get("/api/csv-files")
        data = resp.json()
        if len(data) > 0:
            item = data[0]
            assert "filename" in item
            assert "symbol" in item
            assert "timeframe" in item
            assert "label" in item


class TestBotAPI:
    """Tests for bot management endpoints."""

    def test_list_bots(self, client):
        resp = client.get("/api/bots")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_and_delete_bot(self, client):
        # Create
        resp = client.post("/api/bots", json={
            "name": "Test Bot",
            "strategy": "ma_crossover",
            "symbol": "BTC_USDT",
            "timeframe": "1h",
            "capital": 1000,
            "paper_mode": True,
            "params": {"fast_period": 9, "slow_period": 21},
        })
        assert resp.status_code == 200
        bot = resp.json()
        assert bot["name"] == "Test Bot"
        assert bot["strategy"] == "ma_crossover"
        assert bot["status"] == "stopped"
        bot_id = bot["bot_id"]

        # Get detail
        resp = client.get(f"/api/bots/{bot_id}")
        assert resp.status_code == 200
        assert resp.json()["bot_id"] == bot_id

        # Delete
        resp = client.delete(f"/api/bots/{bot_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_get_nonexistent_bot(self, client):
        resp = client.get("/api/bots/nonexistent")
        assert resp.status_code == 404
