import os
from datetime import date, timedelta
from dotenv import load_dotenv
from tabulate import tabulate
import yfinance as yf

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOptionContractsRequest
from alpaca.trading.enums import AssetStatus, ContractType

from alpaca.data.historical import StockHistoricalDataClient, OptionHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, OptionLatestQuoteRequest

from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest


def has_open_order_for_symbol(symbol):
    request = GetOrdersRequest(
        status=QueryOrderStatus.OPEN,
        limit=50
    )

    orders = trading_client.get_orders(filter=request)

    for order in orders:
        if order.symbol == symbol:
            return True

    return False

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

stock_data_client = StockHistoricalDataClient(API_KEY, API_SECRET)
option_data_client = OptionHistoricalDataClient(API_KEY, API_SECRET)


def get_stock_mid_price(symbol="SPY"):
    request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
    quotes = stock_data_client.get_stock_latest_quote(request)

    quote = quotes[symbol]

    bid = float(quote.bid_price)
    ask = float(quote.ask_price)

    if bid <= 0 or ask <= 0:
        raise ValueError(f"Bad stock quote for {symbol}: bid={bid}, ask={ask}")

    return round((bid + ask) / 2, 2)


def get_contracts(symbol="SPY", contract_type=ContractType.CALL):
    today = date.today()
    min_exp = today + timedelta(days=30)
    max_exp = today + timedelta(days=45)

    request = GetOptionContractsRequest(
        underlying_symbols=[symbol],
        status=AssetStatus.ACTIVE,
        type=contract_type,
        expiration_date_gte=min_exp,
        expiration_date_lte=max_exp,
        limit=1000
    )

    response = trading_client.get_option_contracts(request)
    contracts = getattr(response, "option_contracts", response)

    return contracts


def filter_near_money_contracts(contracts, underlying_price, width=20):
    filtered = []

    for contract in contracts:
        strike = float(contract.strike_price)

        if abs(strike - underlying_price) <= width:
            filtered.append(contract)

    return filtered


def chunk_list(items, chunk_size=100):
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]


def attach_option_quotes(contracts):
    symbols = [c.symbol for c in contracts]

    if not symbols:
        return []

    all_quotes = {}

    # Alpaca option latest quote endpoint allows max 100 symbols per request
    for symbol_chunk in chunk_list(symbols, 100):
        request = OptionLatestQuoteRequest(symbol_or_symbols=symbol_chunk)
        quotes = option_data_client.get_option_latest_quote(request)
        all_quotes.update(quotes)

    rows = []

    for c in contracts:
        quote = all_quotes.get(c.symbol)

        if quote is None:
            continue

        bid = float(quote.bid_price or 0)
        ask = float(quote.ask_price or 0)

        if bid <= 0 or ask <= 0:
            continue

        mid = round((bid + ask) / 2, 2)
        spread = round(ask - bid, 2)
        spread_pct = round((spread / mid) * 100, 2) if mid > 0 else None

        rows.append({
            "symbol": c.symbol,
            "type": str(c.type).replace("ContractType.", ""),
            "strike": float(c.strike_price),
            "expiration": c.expiration_date,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread_pct": spread_pct,
            "tradable": c.tradable,
        })

    return rows


def print_candidates(rows, max_rows=30):
    rows = sorted(rows, key=lambda x: (x["expiration"], x["strike"]))

    table = []

    for r in rows[:max_rows]:
        table.append([
            r["symbol"],
            r["type"],
            r["strike"],
            r["expiration"],
            r["bid"],
            r["ask"],
            r["mid"],
            f'{r["spread_pct"]}%',
            r["tradable"],
        ])

    print(tabulate(
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
            "Tradable"
        ],
        tablefmt="github"
    ))


def choose_best_contract(rows, underlying_price, max_spread_pct=10, max_mid_price=25):
    """
    Pick the best near-money contract based on:
    - tradable
    - tight spread
    - affordable contract price
    - strike closest to underlying price
    """

    filtered = []

    for r in rows:
        if not r["tradable"]:
            continue

        if r["spread_pct"] is None:
            continue

        if r["spread_pct"] > max_spread_pct:
            continue

        if r["mid"] > max_mid_price:
            continue

        filtered.append(r)

    if not filtered:
        return None

    # Closest strike to current SPY price
    best = min(
        filtered,
        key=lambda r: abs(r["strike"] - underlying_price)
    )

    return best


def chunk_list(items, chunk_size=100):
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]


def attach_option_quotes(contracts):
    symbols = [c.symbol for c in contracts]

    if not symbols:
        return []

    all_quotes = {}

    # Alpaca option latest quote endpoint allows max 100 symbols per request
    for symbol_chunk in chunk_list(symbols, 100):
        request = OptionLatestQuoteRequest(symbol_or_symbols=symbol_chunk)
        quotes = option_data_client.get_option_latest_quote(request)
        all_quotes.update(quotes)

    rows = []

    for c in contracts:
        quote = all_quotes.get(c.symbol)

        if quote is None:
            continue

        bid = float(quote.bid_price or 0)
        ask = float(quote.ask_price or 0)

        if bid <= 0 or ask <= 0:
            continue

        mid = round((bid + ask) / 2, 2)
        spread = round(ask - bid, 2)
        spread_pct = round((spread / mid) * 100, 2) if mid > 0 else None

        rows.append({
            "symbol": c.symbol,
            "type": str(c.type).replace("ContractType.", ""),
            "strike": float(c.strike_price),
            "expiration": c.expiration_date,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread_pct": spread_pct,
            "tradable": c.tradable,
        })

    return rows


def get_trend_signal(symbol="SPY"):
    df = yf.download(symbol, period="6mo", interval="1d", auto_adjust=True)

    if df.empty:
        raise ValueError(f"No price data returned for {symbol}")

    # yfinance sometimes returns MultiIndex columns even for one ticker.
    # This safely turns Close into a normal Series.
    close = df["Close"]

    if hasattr(close, "columns"):
        close = close.iloc[:, 0]

    df["SMA_20"] = close.rolling(window=20).mean()
    df["SMA_50"] = close.rolling(window=50).mean()

    latest_close = close.iloc[-1].item()
    sma_20 = df["SMA_20"].iloc[-1].item()
    sma_50 = df["SMA_50"].iloc[-1].item()

    print("\nTrend check:")
    print("Latest close:", round(latest_close, 2))
    print("20 SMA:", round(sma_20, 2))
    print("50 SMA:", round(sma_50, 2))

    if latest_close > sma_20 and sma_20 > sma_50:
        return "BUY_CALL"

    if latest_close < sma_20 and sma_20 < sma_50:
        return "BUY_PUT"

    return "NO_TRADE"


def place_paper_option_order(selected_contract, signal, qty=1):
    if not is_regular_market_hours():
        print("Market is closed for regular options trading. No order placed.")
        return None
    
    if selected_contract is None:
        print("No selected contract. No order placed.")
        return None

    if signal not in ["BUY_CALL", "BUY_PUT"]:
        print(f"Signal is {signal}. No order placed.")
        return None

    symbol = selected_contract["symbol"]
    limit_price = round(float(selected_contract["mid"]), 2)

    estimated_cost = limit_price * 100 * qty

    if has_open_order_for_symbol(symbol):
        print(f"Open order already exists for {symbol}. No new order placed.")
        return None

    print("\nOrder preview:")
    print("Symbol:", symbol)
    print("Signal:", signal)
    print("Qty:", qty)
    print("Limit price:", limit_price)
    print("Estimated cost:", estimated_cost)

    confirm = input("\nPlace this PAPER order? Type YES to confirm: ")

    if confirm != "YES":
        print("Order cancelled.")
        return None

    order_request = LimitOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY,
        type="limit",
        time_in_force=TimeInForce.DAY,
        limit_price=limit_price
    )

    order = trading_client.submit_order(order_request)

    print("\nPaper order submitted.")
    print("Order ID:", order.id)
    print("Status:", order.status)
    print("Symbol:", order.symbol)
    print("Limit price:", order.limit_price)

    return order


from datetime import datetime
from zoneinfo import ZoneInfo


def is_regular_market_hours():
    now = datetime.now(ZoneInfo("America/New_York"))

    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

    is_weekday = now.weekday() < 5

    return is_weekday and market_open <= now <= market_close

if __name__ == "__main__":
    underlying = "SPY"

    spy_price = get_stock_mid_price(underlying)
    print(f"{underlying} estimated mid price: {spy_price}")

    print("\nFetching call contracts...")
    calls = get_contracts(underlying, ContractType.CALL)
    near_calls = filter_near_money_contracts(calls, spy_price, width=20)
    call_rows = attach_option_quotes(near_calls)

    print(f"\nFound {len(call_rows)} near-money call candidates")
    print_candidates(call_rows)

    best_call = choose_best_contract(
        call_rows,
        spy_price,
        max_spread_pct=10,
        max_mid_price=25
    )

    print("\nBest call candidate:")
    print(best_call)

    print("\nFetching put contracts...")
    puts = get_contracts(underlying, ContractType.PUT)
    near_puts = filter_near_money_contracts(puts, spy_price, width=20)
    put_rows = attach_option_quotes(near_puts)

    print(f"\nFound {len(put_rows)} near-money put candidates")
    print_candidates(put_rows)

    best_put = choose_best_contract(
        put_rows,
        spy_price,
        max_spread_pct=10,
        max_mid_price=25
    )

    print("\nBest put candidate:")
    print(best_put)

    signal = get_trend_signal("SPY")

    print("\nBot signal:", signal)

    if signal == "BUY_CALL":
        selected_contract = best_call
    elif signal == "BUY_PUT":
        selected_contract = best_put
    else:
        selected_contract = None

    print("\nSelected contract:")
    print(selected_contract)

    place_paper_option_order(
        selected_contract=selected_contract,
        signal=signal,
        qty=1
    )