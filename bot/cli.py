from __future__ import annotations

import argparse
import sys

from bot.config import database_path, holdings_yaml_path, load_settings
from bot.engine import build_runtime, run_tick
from bot.holdings import HoldingsStore
from bot.scheduler import serve


def _cmd_holdings(args: argparse.Namespace) -> int:
    settings = load_settings()
    store = HoldingsStore(database_path(settings))
    if args.holdings_cmd == "sync":
        store.import_yaml(holdings_yaml_path())
        print(f"Imported {holdings_yaml_path()}")
        return 0
    if args.holdings_cmd == "list":
        positions = store.list_positions()
        watch = store.list_watchlist()
        if not positions:
            print("No positions.")
        else:
            print("Positions:")
            for p in positions:
                print(f"  {p.symbol}  qty={p.qty}  avg_cost={p.avg_cost}  {p.note}")
        if watch:
            print("Watchlist:")
            for w in watch:
                print(f"  {w.symbol}  {w.note}")
        return 0
    if args.holdings_cmd == "add":
        store.upsert_position(args.symbol, args.qty, args.avg_cost, args.note or "")
        store.export_yaml()
        print(f"Upserted {args.symbol.upper()}")
        return 0
    if args.holdings_cmd == "remove":
        removed = store.remove_position(args.symbol)
        store.export_yaml()
        print("Removed" if removed else "Not found", args.symbol.upper())
        return 0 if removed else 1
    raise SystemExit(f"Unknown holdings command: {args.holdings_cmd}")


def _run_once() -> list:
    settings = load_settings()
    store, prices, engine, notifier, alert_log, dedupe_hours = build_runtime(
        settings, database_path(settings)
    )
    store.import_yaml(holdings_yaml_path())
    signals = run_tick(
        store=store,
        prices=prices,
        engine=engine,
        notifier=notifier,
        alert_log=alert_log,
        dedupe_hours=dedupe_hours,
    )
    if not signals:
        print("No signals.")
    else:
        print(f"Dispatched {len(signals)} signal(s).")
    return signals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bot", description="Buy/sell reminder bot")
    sub = parser.add_subparsers(dest="cmd", required=True)

    holdings = sub.add_parser("holdings", help="Manage inventory and cost basis")
    hsub = holdings.add_subparsers(dest="holdings_cmd", required=True)
    hsub.add_parser("list")
    hsub.add_parser("sync", help="Load config/holdings.yaml into the database")
    add = hsub.add_parser("add")
    add.add_argument("symbol")
    add.add_argument("qty", type=float)
    add.add_argument("avg_cost", type=float)
    add.add_argument("--note", default="")
    rem = hsub.add_parser("remove")
    rem.add_argument("symbol")

    sub.add_parser("run-once", help="Fetch prices, evaluate strategies, notify")
    sub.add_parser("serve", help="Run on an interval from settings.yaml")
    sub.add_parser("refresh-symbols", help="Rebuild the Taiwan stock name catalog")
    web = sub.add_parser("web", help="Open a browser UI for holdings and alerts")
    web.add_argument("--host", default="0.0.0.0")
    web.add_argument("--port", type=int, default=5000)

    args = parser.parse_args(argv)
    if args.cmd == "holdings":
        return _cmd_holdings(args)
    if args.cmd == "run-once":
        _run_once()
        return 0
    if args.cmd == "serve":
        serve(load_settings(), _run_once)
        return 0
    if args.cmd == "refresh-symbols":
        from bot.refresh_symbols import refresh
        from bot.symbols import load_catalog

        dest = refresh()
        load_catalog.cache_clear()
        print(f"Wrote {dest}")
        return 0
    if args.cmd == "web":
        from bot.web import run_server

        run_server(host=args.host, port=args.port)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
