import os
from dotenv import load_dotenv

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


def cancel_open_orders():
    request = GetOrdersRequest(
        status=QueryOrderStatus.OPEN,
        limit=50
    )

    orders = trading_client.get_orders(filter=request)

    if not orders:
        print("No open orders to cancel.")
        return

    for order in orders:
        print(f"Canceling {order.symbol} order {order.id}...")
        trading_client.cancel_order_by_id(order.id)

    print("Done.")


if __name__ == "__main__":
    cancel_open_orders()