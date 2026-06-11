# OPTIONS-BOT

Paper-trading utilities for scanning SPY option contracts through Alpaca, viewing account state, and managing open paper orders.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env` with your Alpaca paper trading credentials.

## Usage

Scan and print the current decision without placing an order:

```bash
python scan_options.py
```

Place a paper order only after the scanner passes its risk checks:

```bash
python scan_options.py --place-order
```

Run continuously, scanning only during regular market hours:

```bash
python scan_options.py --loop --market-open-only
```

Run continuously and allow paper order placement without a prompt:

```bash
python scan_options.py --loop --market-open-only --place-order --yes
```

Inspect account state:

```bash
python test_connection.py
python check_orders.py
python check_positions.py
```

Cancel bot-created open orders:

```bash
python cancel_orders.py
```

Cancel orders for one symbol:

```bash
python cancel_orders.py --symbol SPY260619C00600000
```

## Safety Notes

The bot defaults to Alpaca paper trading and defaults to dry-run scanning. Keep `--place-order` explicit, and keep `.env` out of git.

## Strategy

The bot uses a calls-only oversold RSI setup for SPY/QQQ-style liquid options:

1. Calculate RSI 14 from recent 5-minute candles.
2. Return `BUY_CALL` when the latest RSI is below 25.
3. Otherwise print `NO_TRADE`.

When the RSI check passes, the bot looks for a same-day-expiration call contract that passes liquidity and risk checks. By default, it only considers cheap contracts with a midpoint at or below $1.00 and keeps total SPY option exposure within a $100 account budget.

In live paper-order mode, each scan also checks open option positions for exits:

1. Submit a sell limit order when the option is up 100% or more from average entry.
2. Submit a sell limit order when the option is down 50% or more from average entry.
3. Skip new entries during a scan that submitted an exit order.

Important `.env` controls:

```bash
BOT_UNDERLYING=SPY
BOT_ACCOUNT_BUDGET=100
BOT_MAX_CONTRACT_COST=100
BOT_MAX_MID_PRICE=1
BOT_MAX_SPREAD_PCT=10
BOT_MAX_OPEN_ORDERS=1
BOT_MAX_POSITION_QTY=1
BOT_ORDER_QTY=1
BOT_SCAN_INTERVAL_MINUTES=15
```

## VM Deployment

Use an Ubuntu VM or similar Linux host. The bot is designed to run under `systemd` as a dedicated `optionsbot` user from `/opt/options-bot`.

On the VM:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv rsync
git clone https://github.com/PunchyCandy/OPTIONS-BOT.git
cd OPTIONS-BOT
sudo ./deploy/install_vm.sh
```

Edit credentials and safety settings:

```bash
sudo nano /opt/options-bot/.env
```

Start the bot:

```bash
sudo systemctl start options-bot
sudo systemctl status options-bot
```

Watch logs:

```bash
sudo journalctl -u options-bot -f
```

Stop it:

```bash
sudo systemctl stop options-bot
```

After pulling updates on the VM, reinstall and restart:

```bash
git pull
sudo ./deploy/install_vm.sh
sudo systemctl restart options-bot
```

The service command is:

```bash
/opt/options-bot/venv/bin/python /opt/options-bot/scan_options.py --loop --market-open-only --place-order --yes
```

That means the VM will stay running, skip scans while the market is closed, and submit paper orders during regular market hours only after all configured risk gates pass.
