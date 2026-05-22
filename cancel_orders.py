import argparse

from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

from alpaca_clients import BOT_ORDER_PREFIX, get_trading_client


def should_cancel_order(order, symbol=None, all_orders=False):
    if symbol and order.symbol != symbol:
        return False

    if all_orders:
        return True

    client_order_id = str(getattr(order, "client_order_id", ""))
    return client_order_id.startswith(BOT_ORDER_PREFIX)


def cancel_open_orders(symbol=None, all_orders=False, trading_client=None):
    trading_client = trading_client or get_trading_client()
    request = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=50)
    orders = trading_client.get_orders(filter=request)
    matching_orders = [
        order
        for order in orders
        if should_cancel_order(order, symbol=symbol, all_orders=all_orders)
    ]

    if not matching_orders:
        print("No matching open orders to cancel.")
        return

    for order in matching_orders:
        print(f"Canceling {order.symbol} order {order.id}...")
        trading_client.cancel_order_by_id(order.id)

    print("Done.")


def parse_args():
    parser = argparse.ArgumentParser(description="Cancel open paper orders.")
    parser.add_argument("--symbol", help="Only cancel orders for this exact option symbol.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Cancel all open orders, not just bot-created orders.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cancel_open_orders(symbol=args.symbol, all_orders=args.all)
