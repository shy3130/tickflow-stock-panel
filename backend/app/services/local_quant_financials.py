"""Import local quant-screener Tushare financial tables into TickFlow parquet."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from app.services.local_quant_import import load_local_quant_settings


TABLE_SPECS: dict[str, dict[str, Any]] = {
    "metrics": {
        "source": "stock_fina_indicator",
        "aliases": {
            "symbol": "ts_code",
            "period_end": "end_date",
            "announce_date": "ann_date",
            "eps_basic": "eps",
            "eps_diluted": "dt_eps",
            "bps": "bps",
            "ocfps": "ocfps",
            "roe": "roe",
            "roe_diluted": "roe_dt",
            "roa": "roa",
            "gross_margin": "gross_margin",
            "net_margin": "netprofit_margin",
            "debt_to_asset_ratio": "debt_to_assets",
            "revenue_yoy": "or_yoy",
            "net_income_yoy": "netprofit_yoy",
            "operating_cash_to_revenue": "ocf_to_or",
            "inventory_turnover": "inv_turn",
        },
    },
    "income": {
        "source": "stock_income",
        "aliases": {
            "symbol": "ts_code",
            "period_end": "end_date",
            "announce_date": "ann_date",
            "revenue": "revenue",
            "operating_cost": "oper_cost",
            "operating_profit": "operate_profit",
            "selling_expense": "sell_exp",
            "admin_expense": "admin_exp",
            "rd_expense": "rd_exp",
            "financial_expense": "fin_exp",
            "non_operating_income": "non_oper_income",
            "non_operating_expense": "non_oper_exp",
            "total_profit": "total_profit",
            "income_tax": "income_tax",
            "net_income": "n_income",
            "net_income_attributable": "n_income_attr_p",
            "basic_eps": "basic_eps",
            "diluted_eps": "diluted_eps",
        },
    },
    "balance_sheet": {
        "source": "stock_balancesheet",
        "aliases": {
            "symbol": "ts_code",
            "period_end": "end_date",
            "announce_date": "ann_date",
            "total_assets": "total_assets",
            "total_current_assets": "total_cur_assets",
            "total_non_current_assets": "total_nca",
            "cash_and_equivalents": "money_cap",
            "accounts_receivable": "accounts_receiv",
            "inventory": "inventories",
            "fixed_assets": "fix_assets",
            "intangible_assets": "intan_assets",
            "goodwill": "goodwill",
            "total_liabilities": "total_liab",
            "total_current_liabilities": "total_cur_liab",
            "total_non_current_liabilities": "total_ncl",
            "short_term_borrowing": "st_borr",
            "long_term_borrowing": "lt_borr",
            "accounts_payable": "accounts_pay",
            "total_equity": "total_hldr_eqy_exc_min_int",
            "equity_attributable": "total_hldr_eqy_exc_min_int",
            "retained_earnings": "undistr_porfit",
            "minority_interest": "minority_int",
        },
    },
    "cash_flow": {
        "source": "stock_cashflow",
        "aliases": {
            "symbol": "ts_code",
            "period_end": "end_date",
            "announce_date": "ann_date",
            "net_operating_cash_flow": "n_cashflow_act",
            "net_investing_cash_flow": "n_cashflow_inv_act",
            "net_financing_cash_flow": "n_cash_flows_fnc_act",
            "capex": "c_pay_acq_const_fiolta",
            "net_cash_change": "n_incr_cash_cash_equ",
        },
    },
}


def _parse_raw_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text or None


def _load_source_rows(source_table: str) -> list[dict[str, Any]]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required for local quant financial import") from exc

    settings = load_local_quant_settings()
    rows: list[dict[str, Any]] = []
    with psycopg.connect(settings.dsn + " connect_timeout=5", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("set statement_timeout = '60000ms'")
            cur.execute(
                f"""
                select ts_code, ann_date, end_date, raw_json::text as raw_json
                from {settings.tushare_schema}.{source_table}
                where raw_json is not null
                """
            )
            while True:
                batch = cur.fetchmany(10_000)
                if not batch:
                    break
                rows.extend(dict(row) for row in batch)
    return rows


def _to_financial_rows(source_rows: list[dict[str, Any]], aliases: dict[str, str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in source_rows:
        raw = _parse_raw_json(row.get("raw_json"))
        raw.setdefault("ts_code", row.get("ts_code"))
        raw.setdefault("ann_date", row.get("ann_date"))
        raw.setdefault("end_date", row.get("end_date"))
        item: dict[str, Any] = {}
        for target, source in aliases.items():
            item[target] = raw.get(source)
        item["symbol"] = item.get("symbol") or raw.get("ts_code")
        item["period_end"] = _normalize_date(item.get("period_end"))
        item["announce_date"] = _normalize_date(item.get("announce_date"))
        if item.get("symbol") and item.get("period_end"):
            output.append(item)
    return output


def import_local_quant_financials(data_dir: Path, table: str | None = None) -> dict[str, int]:
    targets = [table] if table else list(TABLE_SPECS)
    results: dict[str, int] = {}
    for target in targets:
        if target not in TABLE_SPECS:
            raise ValueError(f"invalid financial table: {target}")
        spec = TABLE_SPECS[target]
        rows = _to_financial_rows(_load_source_rows(spec["source"]), spec["aliases"])
        out_dir = data_dir / "financials" / target
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "part.parquet"
        if rows:
            df = pl.from_dicts(rows, infer_schema_length=None).unique(
                subset=["symbol", "period_end", "announce_date"],
                keep="last",
            )
            df.write_parquet(out_file)
            results[target] = df.height
        else:
            results[target] = 0
    return results


def _recent_quarter_periods(count: int = 12) -> list[str]:
    from datetime import date

    today = date.today()
    quarters = [331, 630, 930, 1231]
    periods: list[str] = []
    year = today.year
    while len(periods) < count:
        for mmdd in reversed(quarters):
            period = f"{year}{mmdd:04d}"
            if period <= today.strftime("%Y%m%d"):
                periods.append(period)
                if len(periods) >= count:
                    break
        year -= 1
    return periods


def _to_tushare_financial_rows(source_rows: list[dict[str, Any]], aliases: dict[str, str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in source_rows:
        item: dict[str, Any] = {}
        for target, source in aliases.items():
            item[target] = raw.get(source)
        item["symbol"] = item.get("symbol") or raw.get("ts_code")
        item["period_end"] = _normalize_date(item.get("period_end"))
        item["announce_date"] = _normalize_date(item.get("announce_date"))
        if item.get("symbol") and item.get("period_end"):
            output.append(item)
    return output


def import_tushare_financials(data_dir: Path, table: str | None = None, periods: int = 12) -> dict[str, int]:
    """Import Tushare financial statement data into TickFlow financial parquet.

    Uses the quarter-wide VIP endpoints where available so the local shape stays
    aligned with TickFlow's financial tables without requiring per-symbol calls.
    """
    from app.services.tushare_import import _client

    api_map = {
        "metrics": "fina_indicator_vip",
        "income": "income_vip",
        "balance_sheet": "balancesheet_vip",
        "cash_flow": "cashflow_vip",
    }
    client = _client()
    targets = [table] if table else list(TABLE_SPECS)
    results: dict[str, int] = {}
    period_values = _recent_quarter_periods(periods)

    for target in targets:
        if target not in TABLE_SPECS:
            raise ValueError(f"invalid financial table: {target}")
        spec = TABLE_SPECS[target]
        fields = sorted(set(spec["aliases"].values()))
        source_rows: list[dict[str, Any]] = []
        last_error: Exception | None = None
        for period in period_values:
            try:
                source_rows.extend(client.call(api_map[target], params={"period": period}, fields=",".join(fields)))
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                break
        if last_error is not None and not source_rows:
            raise RuntimeError(f"Tushare {api_map[target]} import failed: {last_error}") from last_error

        rows = _to_tushare_financial_rows(source_rows, spec["aliases"])
        out_dir = data_dir / "financials" / target
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "part.parquet"
        if rows:
            df = pl.from_dicts(rows, infer_schema_length=None).unique(
                subset=["symbol", "period_end", "announce_date"],
                keep="last",
            )
            df.write_parquet(out_file)
            results[target] = df.height
        else:
            results[target] = 0
    return results


def import_local_quant_adj_factor(data_dir: Path) -> dict[str, int]:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required for local quant adj_factor import") from exc

    settings = load_local_quant_settings()
    rows: list[dict[str, Any]] = []
    with psycopg.connect(settings.dsn + " connect_timeout=5") as conn:
        with conn.cursor() as cur:
            cur.execute("set statement_timeout = '120000ms'")
            cur.execute(
                f"""
                select ts_code, trade_date, adj_factor
                from {settings.tushare_schema}.stock_adj_factor
                where ts_code is not null
                  and trade_date is not null
                  and adj_factor is not null
                """
            )
            while True:
                batch = cur.fetchmany(100_000)
                if not batch:
                    break
                rows.extend(
                    {
                        "symbol": str(ts_code),
                        "trade_date": trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date),
                        "ex_factor": float(adj_factor),
                    }
                    for ts_code, trade_date, adj_factor in batch
                )
    out_dir = data_dir / "adj_factor"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "all.parquet"
    if rows:
        df = (
            pl.from_dicts(rows, infer_schema_length=None)
            .with_columns(
                pl.col("symbol").cast(pl.Utf8, strict=False),
                pl.col("trade_date").cast(pl.Date, strict=False),
                pl.col("ex_factor").cast(pl.Float64, strict=False),
            )
            .drop_nulls(["symbol", "trade_date", "ex_factor"])
            .unique(subset=["symbol", "trade_date"], keep="last")
            .sort(["symbol", "trade_date"])
        )
        df.write_parquet(out_file)
        return {"adj_factor": df.height}
    return {"adj_factor": 0}


def import_local_quant_global_index_daily(data_dir: Path) -> dict[str, int]:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required for local quant index import") from exc

    settings = load_local_quant_settings()
    rows: list[dict[str, Any]] = []
    with psycopg.connect(settings.dsn + " connect_timeout=5") as conn:
        with conn.cursor() as cur:
            cur.execute("set statement_timeout = '120000ms'")
            cur.execute(
                f"""
                select ts_code, trade_date, open, high, low, close, vol
                from {settings.tushare_schema}.global_index_daily
                where ts_code is not null
                  and trade_date is not null
                """
            )
            while True:
                batch = cur.fetchmany(100_000)
                if not batch:
                    break
                rows.extend(
                    {
                        "symbol": str(ts_code),
                        "date": trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date),
                        "open": float(open_) if open_ is not None else None,
                        "high": float(high) if high is not None else None,
                        "low": float(low) if low is not None else None,
                        "close": float(close) if close is not None else None,
                        "volume": float(vol) if vol is not None else None,
                    }
                    for ts_code, trade_date, open_, high, low, close, vol in batch
                )
    if not rows:
        return {"index_daily": 0, "index_instruments": 0}
    # TickFlow stores index daily in the same OHLCV shape as stock daily:
    # symbol/date/open/high/low/close/volume/amount, date is pl.Date.
    # Tushare global_index_daily.vol is volume-like and kept as-is, amount is
    # not available in this local table, so persist it as null Float64.
    df = (
        pl.from_dicts(rows, infer_schema_length=None)
        .with_columns(
            pl.col("symbol").cast(pl.Utf8, strict=False),
            pl.col("date").cast(pl.Date, strict=False),
            pl.col("open").cast(pl.Float64, strict=False),
            pl.col("high").cast(pl.Float64, strict=False),
            pl.col("low").cast(pl.Float64, strict=False),
            pl.col("close").cast(pl.Float64, strict=False),
            pl.col("volume").cast(pl.Float64, strict=False),
            pl.lit(None).cast(pl.Float64).alias("amount"),
        )
        .drop_nulls(["symbol", "date", "open", "high", "low", "close"])
        .unique(subset=["symbol", "date"], keep="last")
        .sort(["symbol", "date"])
    )
    out_dir = data_dir / "kline_index_daily" / "date=local_quant_global"
    out_dir.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out_dir / "part.parquet")

    inst = (
        df.select("symbol")
        .unique()
        .with_columns(
            pl.col("symbol").alias("name"),
            pl.col("symbol").str.split(".").list.first().alias("code"),
            pl.lit("GLOBAL").alias("region"),
            pl.lit("index").alias("asset_type"),
            pl.lit(None).alias("exchange"),
            pl.lit(None).alias("as_of"),
        )
    )
    inst_dir = data_dir / "instruments_index"
    inst_dir.mkdir(parents=True, exist_ok=True)
    inst.write_parquet(inst_dir / "instruments.parquet")
    return {"index_daily": df.height, "index_instruments": inst.height}


def import_local_quant_global_index_profile(repo) -> dict[str, int]:
    """Import local Tushare global index daily data and rebuild index enriched storage."""
    from app.indicators.pipeline import compute_enriched

    result = import_local_quant_global_index_daily(repo.store.data_dir)
    daily_glob = repo.store.data_dir / "kline_index_daily" / "**" / "*.parquet"
    try:
        raw = pl.scan_parquet(str(daily_glob)).collect()
    except Exception:
        raw = pl.DataFrame()

    enriched_rows = 0
    if not raw.is_empty():
        raw = raw.with_columns(
            pl.col("date").cast(pl.Date, strict=False),
            pl.col("symbol").cast(pl.Utf8, strict=False),
        ).drop_nulls(["symbol", "date", "open", "high", "low", "close"])
        if not raw.is_empty():
            enriched = compute_enriched(raw, factors=None, instruments=None)
            repo.append_index_enriched(enriched)
            enriched_rows = enriched.height

    repo.refresh_index_views()
    repo.clear_cache()
    repo.refresh_cache()
    return {**result, "index_enriched": enriched_rows}
