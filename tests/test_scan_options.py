import unittest
import pandas as pd
from types import SimpleNamespace
from unittest.mock import patch

from alpaca_clients import BOT_ORDER_PREFIX, BotConfig
from cancel_orders import should_cancel_order
from scan_options import (
    choose_best_contract,
    get_vwap_reclaim_call_signal,
    place_paper_option_order,
    validate_order_risk,
)


class FakeTradingClient:
    def __init__(self, orders=None, position_qty=0, buying_power=100000, trading_blocked=False):
        self.orders = orders or []
        self.position_qty = position_qty
        self.account = SimpleNamespace(
            buying_power=str(buying_power),
            trading_blocked=trading_blocked,
        )
        self.submitted_order = None

    def get_orders(self, filter=None):
        return self.orders

    def get_open_position(self, symbol):
        if self.position_qty == 0:
            raise ValueError("position not found")

        return SimpleNamespace(qty=str(self.position_qty))

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


def make_config(**overrides):
    defaults = {
        "underlying": "SPY",
        "max_contract_cost": 2500,
        "max_mid_price": 25,
        "max_spread_pct": 10,
        "max_open_orders": 1,
        "max_position_qty": 1,
        "order_qty": 1,
        "scan_interval_minutes": 15,
    }
    defaults.update(overrides)
    return BotConfig(**defaults)


class ScanOptionsTests(unittest.TestCase):
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
            "mid": 2.5,
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

    def test_place_paper_option_order_can_skip_prompt_for_vm_mode(self):
        client = FakeTradingClient()
        selected_contract = {
            "symbol": "SPY260619C00600000",
            "mid": 2.5,
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

    def test_vwap_reclaim_call_signal_fires_on_strict_reversal(self):
        index = pd.date_range("2026-06-08 09:30", periods=30, freq="5min", tz="America/New_York")
        close = [
            100, 100, 100, 100, 100,
            100, 100, 100, 100, 100,
            100, 100, 100, 100, 100,
            100, 100, 100, 100, 100,
            99, 98, 97, 96, 95,
            94, 93, 92, 89, 99,
        ]
        volume = [1000] * 29 + [3000]
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

    def test_vwap_reclaim_call_signal_requires_vwap_reclaim(self):
        index = pd.date_range("2026-06-08 09:30", periods=30, freq="5min", tz="America/New_York")
        close = [
            100, 100, 100, 100, 100,
            100, 100, 100, 100, 100,
            100, 100, 100, 100, 100,
            100, 100, 100, 100, 100,
            99, 98, 97, 96, 95,
            94, 93, 92, 89, 98,
        ]
        volume = [1000] * 29 + [3000]
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
