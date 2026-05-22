import unittest
from types import SimpleNamespace

from alpaca_clients import BOT_ORDER_PREFIX, BotConfig
from cancel_orders import should_cancel_order
from scan_options import choose_best_contract, validate_order_risk


class FakeTradingClient:
    def __init__(self, orders=None, position_qty=0, buying_power=100000, trading_blocked=False):
        self.orders = orders or []
        self.position_qty = position_qty
        self.account = SimpleNamespace(
            buying_power=str(buying_power),
            trading_blocked=trading_blocked,
        )

    def get_orders(self, filter=None):
        return self.orders

    def get_open_position(self, symbol):
        if self.position_qty == 0:
            raise ValueError("position not found")

        return SimpleNamespace(qty=str(self.position_qty))

    def get_account(self):
        return self.account


def make_config(**overrides):
    defaults = {
        "underlying": "SPY",
        "max_contract_cost": 2500,
        "max_mid_price": 25,
        "max_spread_pct": 10,
        "max_open_orders": 1,
        "max_position_qty": 1,
        "order_qty": 1,
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


if __name__ == "__main__":
    unittest.main()
