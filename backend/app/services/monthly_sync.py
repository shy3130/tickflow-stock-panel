"""月 K 同步 (stock-sdk period=monthly → kline_monthly/)。"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date

from app.services.period_kline_sync import (
    PeriodKlineKind,
    backfill_period_range,
    refresh_period_view,
    sync_and_persist_period,
)
from app.services import preferences
from app.services.period_kline_access import period_provider_active
from app.tickflow.repository import KlineRepository

KLINE_MONTHLY_SUBDIR = "kline_monthly"
KLINE_MONTHLY_VIEW = "kline_monthly"

_MONTHLY = PeriodKlineKind(
    dataset="monthly",
    subdir=KLINE_MONTHLY_SUBDIR,
    view=KLINE_MONTHLY_VIEW,
    getter_name="get_monthly",
    provider_getter=preferences.get_monthly_data_provider,
    provider_active=lambda: period_provider_active("monthly"),
    default_window=24,
    max_window=120,
    approx_days=31,
    chunk_env="STOCKSDK_MONTHLY_BATCH",
)


def refresh_monthly_view(repo: KlineRepository) -> None:
    refresh_period_view(repo, subdir=KLINE_MONTHLY_SUBDIR, view=KLINE_MONTHLY_VIEW)


def sync_and_persist_monthly(
    symbols: list[str],
    repo: KlineRepository,
    months: int = 24,
    on_chunk_done: Callable[[int, int], None] | None = None,
) -> int:
    return sync_and_persist_period(
        _MONTHLY, symbols, repo, window=months, on_chunk_done=on_chunk_done
    )


def backfill_monthly_range(
    symbols: list[str],
    repo: KlineRepository,
    *,
    start_date: date,
    end_date: date,
    on_chunk_done: Callable[[int, int], None] | None = None,
) -> tuple[int, int]:
    return backfill_period_range(
        _MONTHLY,
        symbols,
        repo,
        start_date=start_date,
        end_date=end_date,
        on_chunk_done=on_chunk_done,
    )
