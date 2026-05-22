import os
from dotenv import load_dotenv
from tabulate import tabulate

from alpaca.trading.client import TradingClient


load_dotenv()

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

if not API_KEY or not API_SECRET:
    raise ValueError("Missing Alpaca API key or secret in .env")

trading_client = TradingClient(
    api_key=API_KEY,
    secret_key=API_SECRET,
    paper=True
)


def show_positions():
    positions = trading_client.get_all_positions()

    if not positions:
        print("No open positions.")
        return

    rows = []

    for p in positions:
        rows.append([
            p.symbol,
            p.qty,
            p.avg_entry_price,
            p.current_price,
            p.market_value,
            p.unrealized_pl,
            p.unrealized_plpc,
        ])

    print(tabulate(
        rows,
        headers=[
            "Symbol",
            "Qty",
            "Avg Entry",
            "Current",
            "Market Value",
            "Unrealized P/L",
            "Unrealized P/L %"
        ],
        tablefmt="github"
    ))


if __name__ == "__main__":
    show_positions()