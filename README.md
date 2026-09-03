# Trade alert bot

Architecture-only scaffold: record holdings and cost basis, poll prices, evaluate pluggable buy/sell strategies, and send reminders (console / email). **No live orders.** Condition files are not implemented yet — drop them in `config/strategies/` later.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill SMTP_* if you enable email
```

## Holdings

Edit [`config/holdings.yaml`](config/holdings.yaml) or use the CLI:

```bash
python -m bot holdings sync
python -m bot holdings list
python -m bot holdings add 2330.TW 1000 580 --note "台積電"
python -m bot holdings remove AAPL
```

`add` / `remove` also rewrite `config/holdings.yaml`.

## Run

```bash
python -m bot run-once    # one tick
python -m bot serve       # interval from config/settings.yaml
```

With the default `noop` strategy you should see `No signals.` That is expected until real rules are registered.

## Settings

[`config/settings.yaml`](config/settings.yaml):

- `strategies`: ids registered in `bot/strategies/registry.py` (currently `noop`)
- `notify.channels`: `console` and/or `email`
- `notify.dedupe_hours`: suppress the same `symbol|side|rule_id` for this window
- `price_provider`: `yfinance` (or `stub` in tests)

## Adding a strategy later

1. Put the condition file under `config/strategies/`.
2. Implement a class matching `bot.strategies.base.Strategy`.
3. `register("your-id", YourClass)` in `bot/strategies/registry.py`.
4. Add the id to `settings.yaml` → `strategies`.
