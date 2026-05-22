from tabulate import tabulate

from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

from alpaca_clients import get_trading_client


trading_client = get_trading_client()


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
