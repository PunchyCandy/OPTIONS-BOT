import os
from dataclasses import dataclass

from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.trading.client import TradingClient
from dotenv import load_dotenv


load_dotenv()


BOT_ORDER_PREFIX = "options-bot"


@dataclass(frozen=True)
class BotConfig:
    underlying: str
    account_budget: float
    max_contract_cost: float
    max_mid_price: float
    max_spread_pct: float
    max_open_orders: int
    max_position_qty: int
    order_qty: int
    scan_interval_minutes: int


def _required_env(name):
    value = os.getenv(name)

    if not value:
        raise ValueError(f"Missing {name} in .env")

    return value


def _env_float(name, default):
    value = os.getenv(name)
    return float(value) if value else default


def _env_int(name, default):
    value = os.getenv(name)
    return int(value) if value else default


def get_api_credentials():
    return (
        _required_env("APCA_API_KEY_ID"),
        _required_env("APCA_API_SECRET_KEY"),
    )


def get_trading_client():
    api_key, api_secret = get_api_credentials()
    return TradingClient(api_key=api_key, secret_key=api_secret, paper=True)


def get_stock_data_client():
    api_key, api_secret = get_api_credentials()
    return StockHistoricalDataClient(api_key, api_secret)


def get_option_data_client():
    api_key, api_secret = get_api_credentials()
    return OptionHistoricalDataClient(api_key, api_secret)


def get_bot_config():
    return BotConfig(
        underlying=os.getenv("BOT_UNDERLYING", "SPY"),
        account_budget=_env_float("BOT_ACCOUNT_BUDGET", 100),
        max_contract_cost=_env_float("BOT_MAX_CONTRACT_COST", 100),
        max_mid_price=_env_float("BOT_MAX_MID_PRICE", 1),
        max_spread_pct=_env_float("BOT_MAX_SPREAD_PCT", 10),
        max_open_orders=_env_int("BOT_MAX_OPEN_ORDERS", 1),
        max_position_qty=_env_int("BOT_MAX_POSITION_QTY", 1),
        order_qty=_env_int("BOT_ORDER_QTY", 1),
        scan_interval_minutes=_env_int("BOT_SCAN_INTERVAL_MINUTES", 15),
    )
