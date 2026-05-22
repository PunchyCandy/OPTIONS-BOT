import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

load_dotenv()

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")

if not API_KEY or not API_SECRET:
    raise ValueError("Missing Alpaca API key or secret in .env")

client = TradingClient(
    api_key=API_KEY,
    secret_key=API_SECRET,
    paper=True
)

account = client.get_account()

print("Connected successfully")
print("Account status:", account.status)
print("Buying power:", account.buying_power)
print("Equity:", account.equity)
print("Trading blocked:", account.trading_blocked)
print("Options approved level:", getattr(account, "options_approved_level", "Not shown"))
print("Options trading level:", getattr(account, "options_trading_level", "Not shown"))