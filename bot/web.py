from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from bot.alerts import AlertLog
from bot.config import database_path, load_settings
from bot.engine import build_runtime, run_tick
from bot.holdings import HoldingsStore
from bot.prices import PriceProvider, make_price_provider


def create_app(
    *,
    settings: dict[str, Any] | None = None,
    db_path: Path | None = None,
    yaml_path: Path | None = None,
    price_provider: PriceProvider | None = None,
    seed_yaml: bool = True,
) -> Flask:
    app = Flask(__name__)
    app.secret_key = "trade-alert-bot-dev"
    cfg = settings if settings is not None else load_settings()
    path = db_path if db_path is not None else database_path(cfg)
    store = HoldingsStore(path, yaml_path=yaml_path)
    if seed_yaml:
        yaml_file = store.yaml_path
        if yaml_file.exists() and not store.list_positions() and not store.list_watchlist():
            store.import_yaml(yaml_file)

    prices = price_provider or make_price_provider(cfg.get("price_provider", "yfinance"))
    alert_log = AlertLog(path)

    app.config["BOT_SETTINGS"] = cfg
    app.config["BOT_DB"] = path
    app.config["BOT_STORE"] = store
    app.config["BOT_PRICES"] = prices
    app.config["BOT_ALERTS"] = alert_log

    def _quotes(symbols: list[str]) -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        for symbol in symbols:
            try:
                out[symbol] = prices.get_quote(symbol).price
            except Exception:
                out[symbol] = None
        return out

    def _symbols() -> list[str]:
        return [p.symbol for p in store.list_positions()] + [
            w.symbol for w in store.list_watchlist()
        ]

    @app.get("/")
    def index():
        positions = store.list_positions()
        watch = store.list_watchlist()
        rows = [{"position": p} for p in positions]
        return render_template(
            "index.html",
            rows=rows,
            watch=watch,
            alerts=alert_log.list_recent(),
            settings=cfg,
        )

    @app.get("/api/quotes")
    def api_quotes():
        return jsonify(_quotes(_symbols()))

    @app.post("/positions")
    def add_position():
        symbol = (request.form.get("position_symbol") or request.form.get("symbol") or "").strip()
        qty = request.form.get("qty")
        avg_cost = request.form.get("avg_cost")
        note = (request.form.get("position_note") or request.form.get("note") or "").strip()
        if not symbol or qty in (None, "") or avg_cost in (None, ""):
            flash("請填寫標的、數量與購入均價。", "error")
            return redirect(url_for("index"))
        try:
            store.upsert_position(symbol, float(qty), float(avg_cost), note)
            store.export_yaml()
            flash(f"已記錄 {symbol.upper()}。", "ok")
        except ValueError:
            flash("數量與購入均價必須是數字。", "error")
        return redirect(url_for("index"))

    @app.post("/positions/<symbol>/delete")
    def delete_position(symbol: str):
        if store.remove_position(symbol):
            store.export_yaml()
            flash(f"已移除庫存 {symbol.upper()}。", "ok")
        else:
            flash(f"找不到 {symbol.upper()}。", "error")
        return redirect(url_for("index"))

    @app.post("/watchlist")
    def add_watch():
        symbol = (request.form.get("watch_symbol") or request.form.get("symbol") or "").strip()
        note = (request.form.get("watch_note") or request.form.get("note") or "").strip()
        if not symbol:
            flash("請填寫監控標的。", "error")
            return redirect(url_for("index"))
        store.upsert_watch(symbol, note)
        store.export_yaml()
        flash(f"已加入監控 {symbol.upper()}。", "ok")
        return redirect(url_for("index"))

    @app.post("/watchlist/<symbol>/delete")
    def delete_watch(symbol: str):
        if store.remove_watch(symbol):
            store.export_yaml()
            flash(f"已移除監控 {symbol.upper()}。", "ok")
        else:
            flash(f"找不到監控 {symbol.upper()}。", "error")
        return redirect(url_for("index"))

    @app.post("/run")
    def run():
        try:
            _store, _prices, engine, notifier, _alerts, dedupe_hours = build_runtime(cfg, path)
            signals = run_tick(
                store=store,
                prices=prices,
                engine=engine,
                notifier=notifier,
                alert_log=alert_log,
                dedupe_hours=dedupe_hours,
            )
            if signals:
                flash(f"已送出 {len(signals)} 則買賣提醒。", "ok")
            else:
                flash("目前沒有買賣訊號（條件檔尚未接入時這是正常的）。", "ok")
        except Exception as exc:
            flash(f"檢查失敗：{exc}", "error")
        return redirect(url_for("index"))

    @app.post("/reload-yaml")
    def reload_yaml():
        store.import_yaml()
        flash("已從 holdings.yaml 重新載入。", "ok")
        return redirect(url_for("index"))

    return app


def run_server(host: str = "0.0.0.0", port: int = 5000) -> None:
    app = create_app()
    print(f"Open http://127.0.0.1:{port} in the Browser panel")
    app.run(host=host, port=port, debug=False)
