from alpaca_clients import get_trading_client


client = get_trading_client()

account = client.get_account()

print("Connected successfully")
print("Account status:", account.status)
print("Buying power:", account.buying_power)
print("Equity:", account.equity)
print("Trading blocked:", account.trading_blocked)
print("Options approved level:", getattr(account, "options_approved_level", "Not shown"))
print("Options trading level:", getattr(account, "options_trading_level", "Not shown"))
