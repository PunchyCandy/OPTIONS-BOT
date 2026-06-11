import unittest
import pandas as pd
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from alpaca_clients import BOT_ORDER_PREFIX, BotConfig
from cancel_orders import should_cancel_order
from scan_options import (
    choose_best_contract,
    get_contracts,
    get_vwap_reclaim_call_signal,
    manage_open_positions,
    place_paper_option_order,
    validate_order_risk,
)


class FakeTradingClient:
    def __init__(
        self,
        orders=None,
        position_qty=0,
        positions=None,
        buying_power=100000,
        trading_blocked=False,
    ):
        self.orders = orders or []
        self.position_qty = position_qty
        self.positions = positions or []
        self.account = SimpleNamespace(
            buying_power=str(buying_power),
            trading_blocked=trading_blocked,
        )
        self.submitted_order = None
        self.option_contracts_request = None

    def get_orders(self, filter=None):
        return self.orders

    def get_open_position(self, symbol):
        if self.position_qty == 0:
            raise ValueError("position not found")

        return SimpleNamespace(qty=str(self.position_qty))

    def get_all_positions(self):
        return self.positions

    def get_account(self):
        return self.account

    def get_clock(self):
        return SimpleNamespace(is_open=True)

    def submit_order(self, order_request):
        self.submitted_order = order_request
        return SimpleNamespace(
            id="order-1",
            status="accepted",
            symbol=order_request.symbol,
            limit_price=order_request.limit_price,
        )

    def get_option_contracts(self, request):
        self.option_contracts_request = request
        return SimpleNamespace(option_contracts=[])


class FakeOptionDataClient:
    def __init__(self, bid, ask):
        self.bid = bid
        self.ask = ask

    def get_option_latest_quote(self, request):
        symbol = request.symbol_or_symbols[0]
        return {
            symbol: SimpleNamespace(
                bid_price=self.bid,
                ask_price=self.ask,
            )
        }


def make_config(**overrides):
    defaults = {
        "underlying": "SPY",
        "account_budget": 100,
        "max_contract_cost": 100,
        "max_mid_price": 1,
        "max_spread_pct": 10,
        "max_open_orders": 1,
        "max_position_qty": 1,
        "order_qty": 1,
        "scan_interval_minutes": 15,
    }
    defaults.update(overrides)
    return BotConfig(**defaults)


class ScanOptionsTests(unittest.TestCase):
    def test_get_contracts_requests_same_day_expiration(self):
        client = FakeTradingClient()

        contracts = get_contracts(client, "SPY")

        self.assertEqual(contracts, [])
        self.assertEqual(client.option_contracts_request.expiration_date_gte, date.today())
        self.assertEqual(client.option_contracts_request.expiration_date_lte, date.today())

    def test_choose_best_contract_filters_and_prefers_nearest_strike(self):
        rows = [
            {"symbol": "SPY1", "strike": 600, "mid": 2, "spread_pct": 5, "tradable": True},
            {"symbol": "SPY2", "strike": 601, "mid": 2, "spread_pct": 1, "tradable": True},
            {"symbol": "SPY3", "strike": 599, "mid": 30, "spread_pct": 1, "tradable": True},
            {"symbol": "SPY4", "strike": 600, "mid": 2, "spread_pct": 15, "tradable": True},
            {"symbol": "SPY5", "strike": 600, "mid": 2, "spread_pct": 1, "tradable": False},
        ]

        best = choose_best_contract(rows, underlying_price=600, max_spread_pct=10, max_mid_price=25)

        self.assertEqual(best["symbol"], "SPY1")

    def test_should_cancel_order_defaults_to_bot_orders_only(self):
        bot_order = SimpleNamespace(symbol="SPY260619C00600000", client_order_id=f"{BOT_ORDER_PREFIX}-abc")
        manual_order = SimpleNamespace(symbol="SPY260619C00600000", client_order_id="manual")

        self.assertTrue(should_cancel_order(bot_order))
        self.assertFalse(should_cancel_order(manual_order))
        self.assertTrue(should_cancel_order(manual_order, all_orders=True))
        self.assertFalse(should_cancel_order(bot_order, symbol="QQQ260619C00600000"))

    def test_validate_order_risk_rejects_expensive_contract(self):
        client = FakeTradingClient()
        selected_contract = {
            "symbol": "SPY260619C00600000",
            "mid": 30,
        }

        ok, reason = validate_order_risk(
            client,
            selected_contract,
            "BUY_CALL",
            qty=1,
            config=make_config(max_mid_price=25),
        )

        self.assertFalse(ok)
        self.assertIn("exceeds max", reason)

    def test_validate_order_risk_accepts_basic_valid_order(self):
        client = FakeTradingClient()
        selected_contract = {
            "symbol": "SPY260619C00600000",
            "mid": 0.5,
        }

        ok, reason = validate_order_risk(
            client,
            selected_contract,
            "BUY_CALL",
            qty=1,
            config=make_config(),
        )

        self.assertTrue(ok)
        self.assertEqual(reason, "Risk checks passed.")

    def test_validate_order_risk_rejects_when_account_budget_would_be_exceeded(self):
        position = SimpleNamespace(
            symbol="SPY260611C00600000",
            qty="1",
            avg_entry_price="0.5",
            cost_basis="60",
        )
        client = FakeTradingClient(positions=[position])
        selected_contract = {
            "symbol": "SPY260611C00601000",
            "mid": 0.5,
        }

        ok, reason = validate_order_risk(
            client,
            selected_contract,
            "BUY_CALL",
            qty=1,
            config=make_config(account_budget=100),
        )

        self.assertFalse(ok)
        self.assertIn("exceeds account budget", reason)

    def test_place_paper_option_order_can_skip_prompt_for_vm_mode(self):
        client = FakeTradingClient()
        selected_contract = {
            "symbol": "SPY260619C00600000",
            "mid": 0.5,
        }

        with patch("scan_options.is_regular_market_hours", return_value=True):
            order = place_paper_option_order(
                client,
                selected_contract,
                "BUY_CALL",
                qty=1,
                config=make_config(),
                require_confirmation=False,
            )

        self.assertIsNotNone(order)
        self.assertIsNotNone(client.submitted_order)
        self.assertTrue(client.submitted_order.client_order_id.startswith(BOT_ORDER_PREFIX))

    def test_manage_open_positions_sells_at_100_percent_profit(self):
        position = SimpleNamespace(
            symbol="SPY260619C00600000",
            qty="1",
            avg_entry_price="2.0",
        )
        client = FakeTradingClient(positions=[position])
        option_data_client = FakeOptionDataClient(bid=4.0, ask=4.0)

        with patch("scan_options.is_regular_market_hours", return_value=True):
            exit_orders = manage_open_positions(client, option_data_client, make_config())

        self.assertEqual(exit_orders, 1)
        self.assertEqual(client.submitted_order.side.value, "sell")
        self.assertEqual(client.submitted_order.limit_price, 4.0)
        self.assertTrue(client.submitted_order.client_order_id.startswith(f"{BOT_ORDER_PREFIX}-exit-"))

    def test_manage_open_positions_sells_at_50_percent_loss(self):
        position = SimpleNamespace(
            symbol="SPY260619C00600000",
            qty="1",
            avg_entry_price="2.0",
        )
        client = FakeTradingClient(positions=[position])
        option_data_client = FakeOptionDataClient(bid=1.0, ask=1.0)

        with patch("scan_options.is_regular_market_hours", return_value=True):
            exit_orders = manage_open_positions(client, option_data_client, make_config())

        self.assertEqual(exit_orders, 1)
        self.assertEqual(client.submitted_order.side.value, "sell")
        self.assertEqual(client.submitted_order.limit_price, 1.0)

    def test_manage_open_positions_holds_before_exit_thresholds(self):
        position = SimpleNamespace(
            symbol="SPY260619C00600000",
            qty="1",
            avg_entry_price="2.0",
        )
        client = FakeTradingClient(positions=[position])
        option_data_client = FakeOptionDataClient(bid=2.8, ask=2.8)

        with patch("scan_options.is_regular_market_hours", return_value=True):
            exit_orders = manage_open_positions(client, option_data_client, make_config())

        self.assertEqual(exit_orders, 0)
        self.assertIsNone(client.submitted_order)

    def test_vwap_reclaim_call_signal_fires_when_rsi_is_below_25(self):
        index = pd.date_range("2026-06-08 09:30", periods=30, freq="5min", tz="America/New_York")
        close = [
            100, 100, 100, 100, 100,
            100, 100, 100, 100, 100,
            100, 100, 100, 100, 100,
            99, 98, 97, 96, 95,
            94, 93, 92, 91, 90,
            89, 88, 87, 86, 85,
        ]
        volume = [1000] * 30
        df = pd.DataFrame(
            {
                "Open": close,
                "High": [price + 0.25 for price in close],
                "Low": [price - 0.25 for price in close],
                "Close": close,
                "Volume": volume,
            },
            index=index,
        )

        with patch("scan_options.yf.download", return_value=df):
            signal = get_vwap_reclaim_call_signal("SPY")

        self.assertEqual(signal, "BUY_CALL")

    def test_vwap_reclaim_call_signal_requires_rsi_below_25(self):
        index = pd.date_range("2026-06-08 09:30", periods=30, freq="5min", tz="America/New_York")
        close = [
            100, 100, 100, 100, 100,
            100, 100, 100, 100, 100,
            100, 100, 100, 100, 100,
            101, 102, 103, 104, 105,
            106, 107, 108, 109, 110,
            111, 112, 113, 114, 115,
        ]
        volume = [1000] * 30
        df = pd.DataFrame(
            {
                "Open": close,
                "High": [price + 0.25 for price in close],
                "Low": [price - 0.25 for price in close],
                "Close": close,
                "Volume": volume,
            },
            index=index,
        )

        with patch("scan_options.yf.download", return_value=df):
            signal = get_vwap_reclaim_call_signal("SPY")

        self.assertEqual(signal, "NO_TRADE")


if __name__ == "__main__":
    unittest.main()
