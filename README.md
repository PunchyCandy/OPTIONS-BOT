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
