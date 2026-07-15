"""年 K 同步：由 stock-sdk 月线在 provider 内聚合 → kline_yearly/。"""
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

KLINE_YEARLY_SUBDIR = "kline_yearly"
KLINE_YEARLY_VIEW = "kline_yearly"

_YEARLY = PeriodKlineKind(
    dataset="yearly",
    subdir=KLINE_YEARLY_SUBDIR,
    view=KLINE_YEARLY_VIEW,
    getter_name="get_yearly",
    provider_getter=preferences.get_yearly_data_provider,
    provider_active=lambda: period_provider_active("yearly"),
    default_window=10,
    max_window=40,
    approx_days=365,
    chunk_env="STOCKSDK_YEARLY_BATCH",
)


def refresh_yearly_view(repo: KlineRepository) -> None:
    refresh_period_view(repo, subdir=KLINE_YEARLY_SUBDIR, view=KLINE_YEARLY_VIEW)


def sync_and_persist_yearly(
    symbols: list[str],
    repo: KlineRepository,
    years: int = 10,
    on_chunk_done: Callable[[int, int], None] | None = None,
) -> int:
    return sync_and_persist_period(
        _YEARLY, symbols, repo, window=years, on_chunk_done=on_chunk_done
    )


def backfill_yearly_range(
    symbols: list[str],
    repo: KlineRepository,
    *,
    start_date: date,
    end_date: date,
    on_chunk_done: Callable[[int, int], None] | None = None,
) -> tuple[int, int]:
    return backfill_period_range(
        _YEARLY,
        symbols,
        repo,
        start_date=start_date,
        end_date=end_date,
        on_chunk_done=on_chunk_done,
    )
