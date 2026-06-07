import argparse
import time
from datetime import date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import yfinance as yf
from alpaca.data.requests import OptionLatestQuoteRequest, StockLatestQuoteRequest
from alpaca.trading.enums import AssetStatus, ContractType, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOptionContractsRequest, GetOrdersRequest, LimitOrderRequest
from tabulate import tabulate

from alpaca_clients import (
    BOT_ORDER_PREFIX,
    get_bot_config,
    get_option_data_client,
    get_stock_data_client,
    get_trading_client,
)


def has_open_order_for_symbol(trading_client, symbol):
    request = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=50)
    orders = trading_client.get_orders(filter=request)
    return any(order.symbol == symbol for order in orders)


def count_open_bot_orders(trading_client):
    request = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=50)
    orders = trading_client.get_orders(filter=request)

    return sum(
        1
        for order in orders
        if str(getattr(order, "client_order_id", "")).startswith(BOT_ORDER_PREFIX)
    )


def get_position_qty(trading_client, symbol):
    try:
        position = trading_client.get_open_position(symbol)
    except Exception:
        return 0

    return abs(int(float(position.qty)))


def get_stock_mid_price(stock_data_client, symbol="SPY"):
    request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
    quotes = stock_data_client.get_stock_latest_quote(request)
    quote = quotes[symbol]

    bid = float(quote.bid_price)
    ask = float(quote.ask_price)

    if bid <= 0 or ask <= 0:
        raise ValueError(f"Bad stock quote for {symbol}: bid={bid}, ask={ask}")

    return round((bid + ask) / 2, 2)


def get_contracts(trading_client, symbol="SPY", contract_type=ContractType.CALL):
    today = date.today()
    min_exp = today + timedelta(days=30)
    max_exp = today + timedelta(days=45)

    request = GetOptionContractsRequest(
        underlying_symbols=[symbol],
        status=AssetStatus.ACTIVE,
        type=contract_type,
        expiration_date_gte=min_exp,
        expiration_date_lte=max_exp,
        limit=1000,
    )

    response = trading_client.get_option_contracts(request)
    return getattr(response, "option_contracts", response)


def filter_near_money_contracts(contracts, underlying_price, width=20):
    return [
        contract
        for contract in contracts
        if abs(float(contract.strike_price) - underlying_price) <= width
    ]


def chunk_list(items, chunk_size=100):
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]


def attach_option_quotes(option_data_client, contracts):
    symbols = [c.symbol for c in contracts]

    if not symbols:
        return []

    all_quotes = {}

    for symbol_chunk in chunk_list(symbols, 100):
        request = OptionLatestQuoteRequest(symbol_or_symbols=symbol_chunk)
        quotes = option_data_client.get_option_latest_quote(request)
        all_quotes.update(quotes)

    rows = []

    for contract in contracts:
        quote = all_quotes.get(contract.symbol)

        if quote is None:
            continue

        bid = float(quote.bid_price or 0)
        ask = float(quote.ask_price or 0)

        if bid <= 0 or ask <= 0:
            continue

        mid = round((bid + ask) / 2, 2)
        spread = round(ask - bid, 2)
        spread_pct = round((spread / mid) * 100, 2) if mid > 0 else None

        rows.append(
            {
                "symbol": contract.symbol,
                "type": str(contract.type).replace("ContractType.", ""),
                "strike": float(contract.strike_price),
                "expiration": contract.expiration_date,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "spread_pct": spread_pct,
                "tradable": contract.tradable,
            }
        )

    return rows


def print_candidates(rows, max_rows=30):
    rows = sorted(rows, key=lambda x: (x["expiration"], x["strike"]))
    table = [
        [
            row["symbol"],
            row["type"],
            row["strike"],
            row["expiration"],
            row["bid"],
            row["ask"],
            row["mid"],
            f'{row["spread_pct"]}%',
            row["tradable"],
        ]
        for row in rows[:max_rows]
    ]

    print(
        tabulate(
            table,
            headers=[
                "Symbol",
                "Type",
                "Strike",
                "Expiration",
                "Bid",
                "Ask",
                "Mid",
                "Spread %",
                "Tradable",
            ],
            tablefmt="github",
        )
    )


def choose_best_contract(rows, underlying_price, max_spread_pct=10, max_mid_price=25):
    filtered = []

    for row in rows:
        if not row["tradable"]:
            continue

        if row["spread_pct"] is None or row["spread_pct"] > max_spread_pct:
            continue

        if row["mid"] > max_mid_price:
            continue

        filtered.append(row)

    if not filtered:
        return None

    return min(
        filtered,
        key=lambda row: (
            abs(row["strike"] - underlying_price),
            row["spread_pct"],
            row["mid"],
        ),
    )


def get_trend_signal(symbol="SPY"):
    df = yf.download(symbol, period="6mo", interval="1d", auto_adjust=True)

    if df.empty:
        raise ValueError(f"No price data returned for {symbol}")

    close = df["Close"]

    if hasattr(close, "columns"):
        close = close.iloc[:, 0]

    sma_20 = close.rolling(window=20).mean()
    sma_50 = close.rolling(window=50).mean()

    latest_close = close.iloc[-1].item()
    latest_sma_20 = sma_20.iloc[-1].item()
    latest_sma_50 = sma_50.iloc[-1].item()

    print("\nTrend check:")
    print("Latest close:", round(latest_close, 2))
    print("20 SMA:", round(latest_sma_20, 2))
    print("50 SMA:", round(latest_sma_50, 2))

    if latest_close > latest_sma_20 > latest_sma_50:
        return "BUY_CALL"

    if latest_close < latest_sma_20 < latest_sma_50:
        return "BUY_PUT"

    return "NO_TRADE"


def is_regular_market_hours(trading_client):
    clock = trading_client.get_clock()

    if not clock.is_open:
        return False

    now = datetime.now(ZoneInfo("America/New_York"))
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

    return market_open <= now <= market_close


def market_status_message(trading_client):
    clock = trading_client.get_clock()

    if clock.is_open:
        return "Market is open."

    next_open = getattr(clock, "next_open", None)

    if next_open:
        return f"Market is closed. Next open: {next_open}."

    return "Market is closed."


def validate_order_risk(trading_client, selected_contract, signal, qty, config):
    if selected_contract is None:
        return False, "No selected contract."

    if signal not in ["BUY_CALL", "BUY_PUT"]:
        return False, f"Signal is {signal}."

    symbol = selected_contract["symbol"]

    if not symbol.startswith(config.underlying):
        return False, f"{symbol} is not allowed for underlying {config.underlying}."

    if has_open_order_for_symbol(trading_client, symbol):
        return False, f"Open order already exists for {symbol}."

    if count_open_bot_orders(trading_client) >= config.max_open_orders:
        return False, f"Bot already has {config.max_open_orders} open order(s)."

    current_qty = get_position_qty(trading_client, symbol)

    if current_qty + qty > config.max_position_qty:
        return False, f"Position limit would be exceeded for {symbol}."

    limit_price = round(float(selected_contract["mid"]), 2)
    estimated_cost = limit_price * 100 * qty

    if limit_price > config.max_mid_price:
        return False, f"Mid price {limit_price} exceeds max {config.max_mid_price}."

    if estimated_cost > config.max_contract_cost:
        return False, f"Estimated cost {estimated_cost} exceeds max {config.max_contract_cost}."

    account = trading_client.get_account()

    if getattr(account, "trading_blocked", False):
        return False, "Account trading is blocked."

    buying_power = float(account.buying_power)

    if estimated_cost > buying_power:
        return False, f"Estimated cost {estimated_cost} exceeds buying power {buying_power}."

    return True, "Risk checks passed."


def place_paper_option_order(
    trading_client,
    selected_contract,
    signal,
    qty,
    config,
    require_confirmation=True,
):
    if not is_regular_market_hours(trading_client):
        print("Market is closed for regular options trading. No order placed.")
        return None

    ok, reason = validate_order_risk(trading_client, selected_contract, signal, qty, config)

    if not ok:
        print(f"No order placed. {reason}")
        return None

    symbol = selected_contract["symbol"]
    limit_price = round(float(selected_contract["mid"]), 2)
    estimated_cost = limit_price * 100 * qty

    print("\nOrder preview:")
    print("Symbol:", symbol)
    print("Signal:", signal)
    print("Qty:", qty)
    print("Limit price:", limit_price)
    print("Estimated cost:", estimated_cost)

    if require_confirmation:
        confirm = input("\nPlace this PAPER order? Type YES to confirm: ")

        if confirm != "YES":
            print("Order cancelled.")
            return None
    else:
        print("\nAuto-confirm enabled. Submitting PAPER order.")

    order_request = LimitOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY,
        type="limit",
        time_in_force=TimeInForce.DAY,
        limit_price=limit_price,
        client_order_id=f"{BOT_ORDER_PREFIX}-{uuid4().hex[:20]}",
    )

    order = trading_client.submit_order(order_request)

    print("\nPaper order submitted.")
    print("Order ID:", order.id)
    print("Status:", order.status)
    print("Symbol:", order.symbol)
    print("Limit price:", order.limit_price)

    return order


def parse_args():
    parser = argparse.ArgumentParser(description="Scan near-money option contracts.")
    parser.add_argument("--place-order", action="store_true", help="Submit a paper order after all checks pass.")
    parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation. Use only for paper automation.")
    parser.add_argument("--loop", action="store_true", help="Run continuously for VM/systemd deployment.")
    parser.add_argument(
        "--interval-minutes",
        type=int,
        help="Minutes to sleep between loop iterations. Defaults to BOT_SCAN_INTERVAL_MINUTES.",
    )
    parser.add_argument(
        "--market-open-only",
        action="store_true",
        help="In loop mode, skip scans unless Alpaca reports the market is open.",
    )
    return parser.parse_args()


def run_scan(
    config,
    trading_client,
    stock_data_client,
    option_data_client,
    place_order=False,
    require_confirmation=True,
):
    underlying = config.underlying

    print("\n" + "=" * 72)
    print(datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds"))
    print(market_status_message(trading_client))

    underlying_price = get_stock_mid_price(stock_data_client, underlying)
    print(f"{underlying} estimated mid price: {underlying_price}")

    print("\nFetching call contracts...")
    calls = get_contracts(trading_client, underlying, ContractType.CALL)
    near_calls = filter_near_money_contracts(calls, underlying_price, width=20)
    call_rows = attach_option_quotes(option_data_client, near_calls)

    print(f"\nFound {len(call_rows)} near-money call candidates")
    print_candidates(call_rows)

    best_call = choose_best_contract(
        call_rows,
        underlying_price,
        max_spread_pct=config.max_spread_pct,
        max_mid_price=config.max_mid_price,
    )

    print("\nBest call candidate:")
    print(best_call)

    print("\nFetching put contracts...")
    puts = get_contracts(trading_client, underlying, ContractType.PUT)
    near_puts = filter_near_money_contracts(puts, underlying_price, width=20)
    put_rows = attach_option_quotes(option_data_client, near_puts)

    print(f"\nFound {len(put_rows)} near-money put candidates")
    print_candidates(put_rows)

    best_put = choose_best_contract(
        put_rows,
        underlying_price,
        max_spread_pct=config.max_spread_pct,
        max_mid_price=config.max_mid_price,
    )

    print("\nBest put candidate:")
    print(best_put)

    signal = get_trend_signal(underlying)

    print("\nBot signal:", signal)

    if signal == "BUY_CALL":
        selected_contract = best_call
    elif signal == "BUY_PUT":
        selected_contract = best_put
    else:
        selected_contract = None

    print("\nSelected contract:")
    print(selected_contract)

    if not place_order:
        print("\nDry run only. Re-run with --place-order to submit a paper order.")
        return

    place_paper_option_order(
        trading_client=trading_client,
        selected_contract=selected_contract,
        signal=signal,
        qty=config.order_qty,
        config=config,
        require_confirmation=require_confirmation,
    )


def run_loop(args, config, trading_client, stock_data_client, option_data_client):
    interval_minutes = args.interval_minutes or config.scan_interval_minutes
    sleep_seconds = max(interval_minutes, 1) * 60

    print(f"Starting options bot loop. Interval: {interval_minutes} minute(s).")
    print("Press Ctrl+C to stop.")

    while True:
        try:
            if args.market_open_only and not is_regular_market_hours(trading_client):
                print("\n" + "=" * 72)
                print(datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds"))
                print(market_status_message(trading_client))
                print("Skipping scan until regular market hours.")
            else:
                run_scan(
                    config=config,
                    trading_client=trading_client,
                    stock_data_client=stock_data_client,
                    option_data_client=option_data_client,
                    place_order=args.place_order,
                    require_confirmation=not args.yes,
                )
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"Scan failed: {exc}")

        time.sleep(sleep_seconds)


def main():
    args = parse_args()
    config = get_bot_config()
    trading_client = get_trading_client()
    stock_data_client = get_stock_data_client()
    option_data_client = get_option_data_client()

    if args.yes and not args.place_order:
        raise ValueError("--yes only makes sense with --place-order")

    if args.loop:
        run_loop(args, config, trading_client, stock_data_client, option_data_client)
        return

    run_scan(
        config=config,
        trading_client=trading_client,
        stock_data_client=stock_data_client,
        option_data_client=option_data_client,
        place_order=args.place_order,
        require_confirmation=not args.yes,
    )


if __name__ == "__main__":
    main()
