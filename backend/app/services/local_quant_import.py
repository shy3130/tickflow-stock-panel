"""Import and compare local quant-screener PostgreSQL data.

This module keeps TickFlow's own parquet data model as the source of truth for
the app, while allowing a local quant-screener/Tushare PostgreSQL database to
feed and verify it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
import os
from pathlib import Path
from typing import Any, Callable

import polars as pl

from app.indicators.pipeline import run_pipeline
from app.tickflow.repository import KlineRepository

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError as exc:  # pragma: no cover - optional local integration
    psycopg = None
    dict_row = None
    _PSYCOPG_IMPORT_ERROR = exc
else:
    _PSYCOPG_IMPORT_ERROR = None


DEFAULT_QUANT_ROOT = Path("I:/VibeCodingWorkStore/quant-screener")
DEFAULT_MARKET_SCHEMA = "market_data"
DEFAULT_TUSHARE_SCHEMA = "tushare_data"
DEFAULT_ADJUSTED_PREFIX = "stock_daily_forward_adjusted"
DEFAULT_MINUTE_TABLE = "stock_minute_1m"
LOCAL_QUANT_AUTO_ENV = "LOCAL_QUANT_DAILY_IMPORT"
ProgressCb = Callable[[str, int, str], None]
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LocalQuantSettings:
    host: str = "127.0.0.1"
    port: int = 5432
    user: str = "postgres"
    password: str = ""
    dbname: str = "quant"
    market_schema: str = DEFAULT_MARKET_SCHEMA
    tushare_schema: str = DEFAULT_TUSHARE_SCHEMA
    adjusted_prefix: str = DEFAULT_ADJUSTED_PREFIX
    minute_table: str = DEFAULT_MINUTE_TABLE

    @property
    def dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.dbname} "
            f"user={self.user} password={self.password}"
        )


def load_local_quant_settings(root: Path | None = None) -> LocalQuantSettings:
    source_root = Path(os.getenv("LOCAL_QUANT_ROOT") or root or DEFAULT_QUANT_ROOT)
    env_path = source_root / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

    return LocalQuantSettings(
        host=os.getenv("LOCAL_QUANT_PGHOST") or os.getenv("PGHOST", "127.0.0.1"),
        port=int(os.getenv("LOCAL_QUANT_PGPORT") or os.getenv("PGPORT", "5432")),
        user=os.getenv("LOCAL_QUANT_PGUSER") or os.getenv("PGUSER", "postgres"),
        password=os.getenv("LOCAL_QUANT_PGPASSWORD") or os.getenv("PGPASSWORD", ""),
        dbname=os.getenv("LOCAL_QUANT_PGDATABASE") or os.getenv("PGDATABASE", "quant"),
        market_schema=os.getenv("LOCAL_QUANT_MARKET_SCHEMA", DEFAULT_MARKET_SCHEMA),
        tushare_schema=os.getenv("LOCAL_QUANT_TUSHARE_SCHEMA", DEFAULT_TUSHARE_SCHEMA),
        adjusted_prefix=os.getenv("LOCAL_QUANT_ADJUSTED_PREFIX", DEFAULT_ADJUSTED_PREFIX),
        minute_table=os.getenv("LOCAL_QUANT_MINUTE_TABLE", DEFAULT_MINUTE_TABLE),
    )


def _require_psycopg() -> None:
    if psycopg is None:
        raise RuntimeError("psycopg is required for local quant import") from _PSYCOPG_IMPORT_ERROR


def _infer_ts_code(raw_symbol: str) -> str:
    symbol = str(raw_symbol or "").strip().upper()
    if not symbol:
        return ""
    if "." in symbol:
        return symbol
    if symbol.startswith(("5", "6", "9")):
        return f"{symbol}.SH"
    if symbol.startswith(("0", "1", "2", "3")):
        return f"{symbol}.SZ"
    if symbol.startswith(("4", "8")):
        return f"{symbol}.BJ"
    return symbol


def _table_year(table_name: str, prefix: str) -> int | None:
    stem = table_name.replace(f"{prefix}_", "", 1)
    try:
        return int(stem)
    except ValueError:
        return None


def discover_adjusted_tables(settings: LocalQuantSettings) -> list[str]:
    _require_psycopg()
    with psycopg.connect(settings.dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select table_name
                from information_schema.tables
                where table_schema = %s
                  and table_name ~ %s
                order by table_name
                """,
                (settings.market_schema, f"^{settings.adjusted_prefix}_[0-9]{{4}}$"),
            )
            return [str(row[0]) for row in cur.fetchall()]


def _tables_for_range(
    settings: LocalQuantSettings,
    start_date: date | None,
    end_date: date | None,
) -> list[str]:
    tables = discover_adjusted_tables(settings)
    if start_date is None and end_date is None:
        return tables
    selected = []
    start_year = start_date.year if start_date else 0
    end_year = end_date.year if end_date else 9999
    for table in tables:
        year = _table_year(table, settings.adjusted_prefix)
        if year is not None and start_year <= year <= end_year:
            selected.append(table)
    return selected


def local_quant_status(settings: LocalQuantSettings | None = None) -> dict[str, Any]:
    resolved = settings or load_local_quant_settings()
    _require_psycopg()
    tables = discover_adjusted_tables(resolved)
    if not tables:
        return {
            "available": False,
            "adjusted_tables": 0,
            "rows": 0,
            "symbols": 0,
            "min_date": None,
            "max_date": None,
        }

    latest_table = tables[-1]
    earliest_table = tables[0]
    with psycopg.connect(resolved.dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select coalesce(sum(c.reltuples), 0)::bigint
                from pg_class c
                join pg_namespace n on n.oid = c.relnamespace
                where n.nspname = %s
                  and c.relname = any(%s)
                """,
                (resolved.market_schema, tables),
            )
            estimated_rows = int(cur.fetchone()[0] or 0)
            cur.execute(f"select min(trade_date) from {resolved.market_schema}.{earliest_table}")
            min_date = cur.fetchone()[0]
            cur.execute(
                f"""
                select count(*) as latest_rows,
                       count(distinct symbol) as symbols,
                       max(trade_date) as max_date
                from {resolved.market_schema}.{latest_table}
                """
            )
            latest_row = cur.fetchone()
    return {
        "available": True,
        "adjusted_tables": len(tables),
        "rows_estimated": estimated_rows,
        "latest_table": latest_table,
        "latest_table_rows": int(latest_row[0] or 0),
        "symbols": int(latest_row[1] or 0),
        "min_date": min_date.isoformat() if min_date else None,
        "max_date": latest_row[2].isoformat() if latest_row[2] else None,
    }


def _unavailable_local_quant_status(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "adjusted_tables": 0,
        "rows_estimated": 0,
        "latest_table": None,
        "latest_table_rows": 0,
        "symbols": 0,
        "min_date": None,
        "max_date": None,
        "error": reason,
    }


def tickflow_status(repo: KlineRepository) -> dict[str, Any]:
    daily_dir = repo.store.data_dir / "kline_daily"
    if not any(daily_dir.glob("**/*.parquet")):
        return {
            "available": False,
            "rows": 0,
            "symbols": 0,
            "min_date": None,
            "max_date": None,
        }

    daily_latest = repo.latest_daily_date()
    daily_rows = 0
    daily_symbols = 0
    daily_min = None
    try:
        row = repo.execute_one(
            """
            select count(*) as rows,
                   count(distinct symbol) as symbols,
                   min(date) as min_date,
                   max(date) as max_date
            from kline_daily
            """
        )
        if row:
            daily_rows = int(row[0] or 0)
            daily_symbols = int(row[1] or 0)
            daily_min = row[2]
            daily_latest = row[3] or daily_latest
    except Exception:
        pass

    return {
        "available": daily_rows > 0,
        "rows": daily_rows,
        "symbols": daily_symbols,
        "min_date": daily_min.isoformat() if hasattr(daily_min, "isoformat") else daily_min,
        "max_date": daily_latest.isoformat() if hasattr(daily_latest, "isoformat") else daily_latest,
    }


def local_quant_minute_status(settings: LocalQuantSettings | None = None) -> dict[str, Any]:
    resolved = settings or load_local_quant_settings()
    _require_psycopg()
    with psycopg.connect(resolved.dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select exists (
                    select 1
                    from information_schema.tables
                    where table_schema = %s and table_name = %s
                )
                """,
                (resolved.tushare_schema, resolved.minute_table),
            )
            exists = bool(cur.fetchone()["exists"])
            if not exists:
                return {
                    "available": False,
                    "table": f"{resolved.tushare_schema}.{resolved.minute_table}",
                    "rows": 0,
                    "symbols": 0,
                    "min_time": None,
                    "max_time": None,
                }
            cur.execute(
                f"""
                select count(*) as rows,
                       count(distinct ts_code) as symbols,
                       min(trade_time) as min_time,
                       max(trade_time) as max_time
                from {resolved.tushare_schema}.{resolved.minute_table}
                """
            )
            row = cur.fetchone()
    min_time = row["min_time"]
    max_time = row["max_time"]
    return {
        "available": int(row["rows"] or 0) > 0,
        "table": f"{resolved.tushare_schema}.{resolved.minute_table}",
        "rows": int(row["rows"] or 0),
        "symbols": int(row["symbols"] or 0),
        "min_time": min_time.isoformat() if min_time else None,
        "max_time": max_time.isoformat() if max_time else None,
    }


def _unavailable_local_quant_minute_status(reason: str) -> dict[str, Any]:
    settings = load_local_quant_settings()
    return {
        "available": False,
        "table": f"{settings.tushare_schema}.{settings.minute_table}",
        "rows": 0,
        "symbols": 0,
        "min_time": None,
        "max_time": None,
        "error": reason,
    }


def tickflow_minute_status(repo: KlineRepository) -> dict[str, Any]:
    try:
        row = repo.execute_one(
            """
            select count(*) as rows,
                   count(distinct symbol) as symbols,
                   min(datetime) as min_time,
                   max(datetime) as max_time
            from kline_minute
            """
        )
        if row:
            min_time = row[2]
            max_time = row[3]
            return {
                "available": int(row[0] or 0) > 0,
                "rows": int(row[0] or 0),
                "symbols": int(row[1] or 0),
                "min_time": min_time.isoformat() if hasattr(min_time, "isoformat") else min_time,
                "max_time": max_time.isoformat() if hasattr(max_time, "isoformat") else max_time,
            }
    except Exception:
        pass
    return {
        "available": False,
        "rows": 0,
        "symbols": 0,
        "min_time": None,
        "max_time": None,
    }


def compare_sources(repo: KlineRepository) -> dict[str, Any]:
    try:
        local = local_quant_status()
    except Exception as exc:  # noqa: BLE001
        logger.info("local quant status unavailable: %s", exc)
        local = _unavailable_local_quant_status(str(exc))
    tickflow = tickflow_status(repo)
    try:
        local_minute = local_quant_minute_status()
    except Exception as exc:  # noqa: BLE001
        logger.info("local quant minute status unavailable: %s", exc)
        local_minute = _unavailable_local_quant_minute_status(str(exc))
    return {
        "tickflow": tickflow,
        "local_quant": local,
        "minute": {
            "tickflow": tickflow_minute_status(repo),
            "local_quant": local_minute,
        },
        "mode": local_quant_mode_status(),
        "diagnostics": _comparison_diagnostics(tickflow, local),
        "recommendation": _comparison_recommendation(tickflow, local),
    }


def local_quant_auto_import_enabled() -> bool:
    raw = os.getenv(LOCAL_QUANT_AUTO_ENV, "auto").strip().lower()
    if raw in {"0", "false", "no", "off", "tickflow"}:
        return False
    root = Path(os.getenv("LOCAL_QUANT_ROOT") or DEFAULT_QUANT_ROOT)
    if raw in {"1", "true", "yes", "on", "local", "auto"}:
        return root.exists()
    return root.exists()


def local_quant_mode_status() -> dict[str, Any]:
    raw = os.getenv(LOCAL_QUANT_AUTO_ENV, "auto").strip().lower()
    enabled = local_quant_auto_import_enabled()
    return {
        "env_value": raw,
        "auto_import_enabled": enabled,
        "daily_source": "local_quant" if enabled else "tickflow",
        "source_root": str(Path(os.getenv("LOCAL_QUANT_ROOT") or DEFAULT_QUANT_ROOT)),
    }


def _comparison_recommendation(tickflow: dict[str, Any], local: dict[str, Any]) -> str:
    if not local.get("available"):
        return "local_quant_unavailable"
    if not tickflow.get("available"):
        return "import_local_quant_first"
    if tickflow.get("max_date") != local.get("max_date"):
        return "incremental_import_required"
    tickflow_min = _parse_iso_date(tickflow.get("min_date"))
    local_min = _parse_iso_date(local.get("min_date"))
    if tickflow_min and local_min and tickflow_min > local_min + timedelta(days=180):
        return "history_coverage_gap"
    if int(tickflow.get("symbols") or 0) < int(local.get("symbols") or 0) * 0.95:
        return "symbol_coverage_gap"
    return "sources_aligned"


def _comparison_diagnostics(tickflow: dict[str, Any], local: dict[str, Any]) -> dict[str, Any]:
    tickflow_min = _parse_iso_date(tickflow.get("min_date"))
    tickflow_max = _parse_iso_date(tickflow.get("max_date"))
    local_min = _parse_iso_date(local.get("min_date"))
    local_max = _parse_iso_date(local.get("max_date"))
    tickflow_symbols = int(tickflow.get("symbols") or 0)
    local_symbols = int(local.get("symbols") or 0)

    history_gap_days = 0
    if tickflow_min and local_min and tickflow_min > local_min:
        history_gap_days = (tickflow_min - local_min).days

    return {
        "latest_aligned": bool(tickflow_max and local_max and tickflow_max == local_max),
        "history_gap_days": history_gap_days,
        "symbol_gap": max(local_symbols - tickflow_symbols, 0),
        "tickflow_history_days": _date_span_days(tickflow_min, tickflow_max),
        "local_history_days": _date_span_days(local_min, local_max),
        "suggested_import_days": [30, 365, 1095],
    }


def _date_span_days(start: date | None, end: date | None) -> int:
    if not start or not end or end < start:
        return 0
    return (end - start).days + 1


def _parse_iso_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def fetch_local_quant_daily(
    *,
    settings: LocalQuantSettings | None = None,
    start_date: date | None,
    end_date: date | None,
) -> pl.DataFrame:
    resolved = settings or load_local_quant_settings()
    _require_psycopg()
    tables = _tables_for_range(resolved, start_date, end_date)
    if not tables:
        return pl.DataFrame()

    predicates = []
    params: list[Any] = []
    if start_date is not None:
        predicates.append("q.trade_date >= %s")
        params.append(start_date)
    if end_date is not None:
        predicates.append("q.trade_date <= %s")
        params.append(end_date)
    where_sql = "where " + " and ".join(predicates) if predicates else ""

    parts = []
    for table in tables:
        parts.append(
            f"""
            select
                coalesce(sb.ts_code, q.symbol) as symbol,
                q.trade_date as date,
                q.open_price as open,
                q.high_price as high,
                q.low_price as low,
                q.close_price as close,
                q.volume_shares as volume,
                q.turnover_value as amount,
                q.turnover_rate as turnover_rate
            from {resolved.market_schema}.{table} q
            left join {resolved.tushare_schema}.stock_basic sb
              on sb.symbol = q.symbol or sb.ts_code = q.symbol
            {where_sql}
            """
        )
    sql = " union all ".join(parts)
    with psycopg.connect(resolved.dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params * len(tables)))
            rows = [dict(row) for row in cur.fetchall()]
    if not rows:
        return pl.DataFrame()

    normalized = []
    for row in rows:
        normalized.append(
            {
                "symbol": _infer_ts_code(str(row.get("symbol") or "")),
                "date": row.get("date"),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "amount": row.get("amount"),
                "turnover_rate": row.get("turnover_rate"),
            }
        )
    df = pl.DataFrame(normalized)
    # TickFlow stores daily volume in hands. Local quant adjusted tables use
    # volume_shares, so convert shares -> hands to match TickFlow/Tushare.
    return df.with_columns(
        pl.col("symbol").cast(pl.Utf8, strict=False),
        pl.col("date").cast(pl.Date, strict=False),
        pl.col("open").cast(pl.Float64, strict=False),
        pl.col("high").cast(pl.Float64, strict=False),
        pl.col("low").cast(pl.Float64, strict=False),
        pl.col("close").cast(pl.Float64, strict=False),
        (pl.col("volume").cast(pl.Float64, strict=False) / 100.0).alias("volume"),
        pl.col("amount").cast(pl.Float64, strict=False),
        pl.col("turnover_rate").cast(pl.Float64, strict=False),
    ).unique(subset=["symbol", "date"], keep="last").drop_nulls(["symbol", "date", "open", "high", "low", "close"])


def fetch_local_quant_minute(
    *,
    settings: LocalQuantSettings | None = None,
    start_time: datetime | None,
    end_time: datetime | None,
) -> pl.DataFrame:
    resolved = settings or load_local_quant_settings()
    _require_psycopg()
    predicates = []
    params: list[Any] = []
    if start_time is not None:
        predicates.append("trade_time >= %s")
        params.append(start_time)
    if end_time is not None:
        predicates.append("trade_time <= %s")
        params.append(end_time)
    where_sql = "where " + " and ".join(predicates) if predicates else ""
    sql = f"""
        select ts_code as symbol,
               trade_time as datetime,
               open,
               high,
               low,
               close,
               vol as volume,
               amount
        from {resolved.tushare_schema}.{resolved.minute_table}
        {where_sql}
        order by trade_time, ts_code
    """
    with psycopg.connect(resolved.dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = [dict(row) for row in cur.fetchall()]
    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    # Tushare minute vol is in hands and amount is in yuan in the local table,
    # so keep units as-is to match kline_minute.
    return df.with_columns(
        pl.col("symbol").cast(pl.Utf8, strict=False),
        pl.col("datetime").cast(pl.Datetime("us"), strict=False),
        pl.col("open").cast(pl.Float64, strict=False),
        pl.col("high").cast(pl.Float64, strict=False),
        pl.col("low").cast(pl.Float64, strict=False),
        pl.col("close").cast(pl.Float64, strict=False),
        pl.col("volume").cast(pl.Float64, strict=False),
        pl.col("amount").cast(pl.Float64, strict=False),
    ).unique(subset=["symbol", "datetime"], keep="last").drop_nulls(["symbol", "datetime", "open", "high", "low", "close"])


def _latest_tickflow_minute_datetime(repo: KlineRepository) -> datetime | None:
    try:
        row = repo.execute_one("select max(datetime) from kline_minute")
        if row and row[0]:
            value = row[0]
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(str(value))
    except Exception:
        pass
    return None


def _write_minute_partitions(repo: KlineRepository, df: pl.DataFrame) -> int:
    if df.is_empty():
        return 0
    df = df.with_columns(pl.col("datetime").dt.date().alias("_trade_date"))
    written = 0
    for day_df in df.partition_by("_trade_date"):
        trade_date = day_df["_trade_date"][0]
        out = repo.store.data_dir / "kline_minute" / f"date={trade_date}" / "part.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        day_df = day_df.drop("_trade_date")
        if out.exists():
            existing = pl.read_parquet(out)
            if "datetime" in existing.columns:
                existing = existing.filter(pl.col("datetime").is_not_null())
            day_df = pl.concat([existing, day_df], how="diagonal_relaxed").unique(
                subset=["symbol", "datetime"], keep="last"
            )
        day_df.sort(["symbol", "datetime"]).write_parquet(out)
        written += day_df.height
    repo.store._register_views()
    return written


def import_local_quant_minute(
    repo: KlineRepository,
    *,
    days: int = 5,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, Any]:
    status = local_quant_minute_status()
    if not status.get("available") or not status.get("max_time"):
        return {"status": "unavailable", "rows_written": 0, "reason": "local_quant_minute_unavailable"}

    local_max = datetime.fromisoformat(str(status["max_time"]))
    resolved_end = end_time or local_max
    tickflow_latest = _latest_tickflow_minute_datetime(repo)
    if start_time is not None:
        resolved_start = start_time
    elif tickflow_latest and tickflow_latest.date() < resolved_end.date():
        resolved_start = tickflow_latest
    else:
        start_day = resolved_end.date() - timedelta(days=max(1, min(30, int(days or 5))) - 1)
        resolved_start = datetime.combine(start_day, datetime.min.time())

    if resolved_start > resolved_end:
        return {
            "status": "up_to_date",
            "rows_written": 0,
            "start_time": resolved_start.isoformat(),
            "end_time": resolved_end.isoformat(),
        }

    df = fetch_local_quant_minute(start_time=resolved_start, end_time=resolved_end)
    if df.is_empty():
        return {
            "status": "empty",
            "rows_written": 0,
            "start_time": resolved_start.isoformat(),
            "end_time": resolved_end.isoformat(),
        }

    rows = _write_minute_partitions(repo, df)
    return {
        "status": "ok",
        "rows_written": rows,
        "symbols": df.select(pl.col("symbol").n_unique()).item(),
        "start_time": df["datetime"].min().isoformat(),
        "end_time": df["datetime"].max().isoformat(),
    }


def import_local_quant_daily(
    repo: KlineRepository,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    days: int | None = None,
    compute_enriched: bool = True,
) -> dict[str, Any]:
    if days is not None and days > 0:
        resolved_end = end_date or date.today()
        resolved_start = start_date or (resolved_end - timedelta(days=days - 1))
    else:
        resolved_start = start_date
        resolved_end = end_date

    df = fetch_local_quant_daily(start_date=resolved_start, end_date=resolved_end)
    if df.is_empty():
        return {
            "status": "empty",
            "rows_written": 0,
            "start_date": resolved_start.isoformat() if resolved_start else None,
            "end_date": resolved_end.isoformat() if resolved_end else None,
            "enriched_rows_written": 0,
        }

    repo.append_daily(df)
    repo.store._register_views()

    inst_rows = upsert_instruments_from_local_quant(repo)
    enriched_rows = 0
    if compute_enriched:
        enriched_rows = run_pipeline(repo.store.data_dir, new_dates_only=True)
        repo.store._register_views()
        repo.refresh_cache()

    return {
        "status": "ok",
        "rows_written": df.height,
        "symbols": df.select(pl.col("symbol").n_unique()).item(),
        "start_date": df["date"].min().isoformat(),
        "end_date": df["date"].max().isoformat(),
        "instrument_rows": inst_rows,
        "enriched_rows_written": enriched_rows,
    }


def import_local_quant_daily_chunked(
    repo: KlineRepository,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    days: int | None = None,
    compute_enriched: bool = True,
    chunk_days: int = 90,
    on_progress: Callable[..., None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    emit = on_progress or (lambda *args, **kwargs: None)
    cancel_requested = should_cancel or (lambda: False)
    local = local_quant_status()
    local_max = _parse_iso_date(local.get("max_date"))

    if days is not None and days > 0:
        resolved_end = end_date or local_max or date.today()
        resolved_start = start_date or (resolved_end - timedelta(days=days - 1))
    else:
        resolved_start = start_date or _parse_iso_date(local.get("min_date"))
        resolved_end = end_date or local_max or date.today()

    if not resolved_start or not resolved_end or resolved_start > resolved_end:
        return {
            "status": "empty",
            "rows_written": 0,
            "start_date": resolved_start.isoformat() if resolved_start else None,
            "end_date": resolved_end.isoformat() if resolved_end else None,
            "chunks": 0,
            "enriched_rows_written": 0,
        }

    chunk_days = max(15, min(int(chunk_days or 90), 366))
    total_days = (resolved_end - resolved_start).days + 1
    total_chunks = (total_days + chunk_days - 1) // chunk_days
    rows_written = 0
    symbols: set[str] = set()
    chunks_written = 0

    current = resolved_start
    chunk_index = 0
    while current <= resolved_end:
        if cancel_requested():
            raise RuntimeError("cancelled")
        chunk_index += 1
        chunk_end = min(current + timedelta(days=chunk_days - 1), resolved_end)
        stage_pct = int(100 * chunk_index / total_chunks)
        pct = 5 + int(65 * chunk_index / total_chunks)
        emit(
            "local_quant_import",
            pct,
            f"local quant chunk {chunk_index}/{total_chunks} [{current} ~ {chunk_end}]",
            stage_pct=stage_pct,
            skip_log=True,
        )
        df = fetch_local_quant_daily(start_date=current, end_date=chunk_end)
        if not df.is_empty():
            repo.append_daily(df)
            rows_written += df.height
            symbols.update(df["symbol"].unique().to_list())
            chunks_written += 1
        current = chunk_end + timedelta(days=1)

    emit("local_quant_import", 72, "refresh parquet views")
    repo.store._register_views()

    if cancel_requested():
        raise RuntimeError("cancelled")
    emit("local_quant_instruments", 78, "refresh instruments from local quant")
    inst_rows = upsert_instruments_from_local_quant(repo)

    enriched_rows = 0
    if compute_enriched:
        if cancel_requested():
            raise RuntimeError("cancelled")
        emit("local_quant_enriched", 82, "compute enriched indicators")
        enriched_rows = run_pipeline(repo.store.data_dir, new_dates_only=True)
        repo.store._register_views()
        repo.refresh_cache()
    else:
        repo.clear_cache()
        repo.refresh_cache()

    emit("local_quant_import", 100, "local quant import complete")
    return {
        "status": "ok" if rows_written else "empty",
        "rows_written": rows_written,
        "symbols": len(symbols),
        "start_date": resolved_start.isoformat(),
        "end_date": resolved_end.isoformat(),
        "chunks": total_chunks,
        "chunks_written": chunks_written,
        "instrument_rows": inst_rows,
        "enriched_rows_written": enriched_rows,
    }


def import_local_quant_incremental(
    repo: KlineRepository,
    *,
    compute_enriched: bool = False,
) -> dict[str, Any]:
    local = local_quant_status()
    tickflow = tickflow_status(repo)
    if not local.get("available") or not local.get("max_date"):
        return {
            "status": "unavailable",
            "rows_written": 0,
            "reason": "local_quant_unavailable",
        }

    end = date.fromisoformat(str(local["max_date"]))
    tickflow_max = tickflow.get("max_date")
    start = date.fromisoformat(str(tickflow_max)) if tickflow_max else end - timedelta(days=30)
    if start > end:
        return {
            "status": "up_to_date",
            "rows_written": 0,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }

    return import_local_quant_daily(
        repo,
        start_date=start,
        end_date=end,
        days=None,
        compute_enriched=compute_enriched,
    )


def upsert_instruments_from_local_quant(repo: KlineRepository) -> int:
    settings = load_local_quant_settings()
    _require_psycopg()
    tables = discover_adjusted_tables(settings)
    latest_table = tables[-1] if tables else None
    with psycopg.connect(settings.dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if latest_table:
                cur.execute(
                    f"""
                    with latest_date as (
                        select max(trade_date) as trade_date
                        from {settings.market_schema}.{latest_table}
                    ),
                    metrics as (
                        select distinct on (symbol)
                               symbol,
                               total_shares,
                               float_shares,
                               total_market_cap,
                               float_market_cap,
                               pe_ttm,
                               pb
                        from {settings.market_schema}.{latest_table}
                        where trade_date = (select trade_date from latest_date)
                        order by symbol, trade_date desc
                    )
                    select sb.ts_code,
                           sb.symbol as code,
                           sb.name,
                           sb.area,
                           sb.industry,
                           sb.market,
                           sb.list_date,
                           m.total_shares,
                           m.float_shares,
                           m.total_market_cap,
                           m.float_market_cap,
                           m.pe_ttm,
                           m.pb
                    from {settings.tushare_schema}.stock_basic sb
                    left join metrics m
                      on m.symbol = sb.symbol or m.symbol = sb.ts_code
                    where sb.ts_code is not null
                    """
                )
            else:
                cur.execute(
                    f"""
                    select ts_code, symbol as code, name, area, industry, market, list_date,
                           null as total_shares,
                           null as float_shares,
                           null as total_market_cap,
                           null as float_market_cap,
                           null as pe_ttm,
                           null as pb
                    from {settings.tushare_schema}.stock_basic
                    where ts_code is not null
                    """
                )
            rows = [dict(row) for row in cur.fetchall()]
    if not rows:
        return 0
    normalized = []
    for row in rows:
        ts_code = _infer_ts_code(str(row.get("ts_code") or row.get("code") or ""))
        if not ts_code:
            continue
        exchange = ts_code.split(".")[-1] if "." in ts_code else ""
        normalized.append(
            {
                "symbol": ts_code,
                "name": row.get("name"),
                "code": row.get("code") or ts_code.split(".")[0],
                "exchange": exchange,
                "region": "CN",
                "type": "stock",
                "industry": row.get("industry"),
                "area": row.get("area"),
                "market": row.get("market"),
                "list_date": row.get("list_date"),
                "total_shares": row.get("total_shares"),
                "float_shares": row.get("float_shares"),
                "total_market_cap": row.get("total_market_cap"),
                "float_market_cap": row.get("float_market_cap"),
                "pe_ttm": row.get("pe_ttm"),
                "pb": row.get("pb"),
                "as_of": date.today(),
            }
        )
    df = pl.DataFrame(normalized)
    if df.is_empty():
        return 0
    numeric_cols = [
        "total_shares",
        "float_shares",
        "total_market_cap",
        "float_market_cap",
        "pe_ttm",
        "pb",
    ]
    df = df.with_columns(
        [pl.col(c).cast(pl.Float64, strict=False) for c in numeric_cols if c in df.columns]
    )
    out = repo.store.data_dir / "instruments" / "instruments.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        existing = pl.read_parquet(out)
        df = pl.concat([existing, df], how="diagonal_relaxed").unique(subset=["symbol"], keep="last")
    df.sort("symbol").write_parquet(out)
    repo.clear_cache()
    repo.refresh_cache()
    return df.height
