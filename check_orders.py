import os
from dotenv import load_dotenv
from tabulate import tabulate

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus


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


def show_orders():
    request = GetOrdersRequest(
        status=QueryOrderStatus.ALL,
        limit=20
    )

    orders = trading_client.get_orders(filter=request)

    rows = []

    for order in orders:
        rows.append([
            order.id,
            order.symbol,
            order.side,
            order.qty,
            order.order_type,
            order.limit_price,
            order.status,
            order.filled_qty,
            order.filled_avg_price,
            order.created_at,
        ])

    print(tabulate(
        rows,
        headers=[
            "Order ID",
            "Symbol",
            "Side",
            "Qty",
            "Type",
            "Limit",
            "Status",
            "Filled Qty",
            "Avg Fill",
            "Created At"
        ],
        tablefmt="github"
    ))


if __name__ == "__main__":
    show_orders()