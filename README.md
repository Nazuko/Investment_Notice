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

## Browser UI

```bash
python -m bot web
```

Then open `http://127.0.0.1:5000` in the Cursor Browser panel. Holdings and watchlist pickers search Taiwan listed/OTC names (代號 + 中文名稱). Tables show the Chinese name, with the Yahoo ticker underneath.

Top nav opens personality pages (打工型 / 上班族型 / 老闆型), each with two skill tabs. 成長型 and 被動型 are placeholders until their SOP files are added. Click **更新盤後選股** to screen using yesterday's close and turnover (not intraday prices).

Refresh the bundled catalog:

```bash
python -m bot refresh-symbols
```

## Run (CLI)

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
