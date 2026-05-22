from tabulate import tabulate

from alpaca_clients import get_trading_client


trading_client = get_trading_client()


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
