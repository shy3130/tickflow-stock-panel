"""日/周以外周期 K 线（月/年）共用同步逻辑。按 date 分区，模型对齐 kline_weekly。"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import polars as pl

from app.market_time import cn_now, last_cn_weekday
from app.tickflow.rate_limits import chunked
from app.tickflow.repository import KlineRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PeriodKlineKind:
    dataset: str
    subdir: str
    view: str
    getter_name: str
    provider_getter: Callable[[], str]
    provider_active: Callable[[], bool]
    default_window: int
    max_window: int
    """最近同步向前看的自然日跨度 ≈ window * approx_days。"""
    approx_days: int
    chunk_env: str
    default_chunk: int = 80


def _chunk_size(kind: PeriodKlineKind) -> int:
    try:
        return max(20, int(os.getenv(kind.chunk_env, str(kind.default_chunk))))
    except ValueError:
        return kind.default_chunk


def sync_period_batch(
    kind: PeriodKlineKind,
    symbols: list[str],
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    on_chunk_done: Callable[[int, int], None] | None = None,
) -> pl.DataFrame:
    if not kind.provider_active() or not symbols:
        return pl.DataFrame()
    provider_name = kind.provider_getter()
    from app.data_providers import custom as custom_sources

    if not custom_sources.provider_has_dataset(provider_name, kind.dataset):
        return pl.DataFrame()
    provider = custom_sources.get_provider(provider_name)
    getter = getattr(provider, kind.getter_name, None)
    if getter is None:
        return pl.DataFrame()
    return getter(
        symbols,
        start_time=start_time,
        end_time=end_time,
        on_chunk_done=on_chunk_done,
    )


def refresh_period_view(
    repo: KlineRepository,
    *,
    subdir: str,
    view: str,
) -> None:
    try:
        d = repo.store.data_dir.as_posix()
        repo.db.execute(
            f"""CREATE OR REPLACE VIEW {view} AS
                SELECT * FROM read_parquet('{d}/{subdir}/**/*.parquet', union_by_name=true)"""
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("refresh %s view failed: %s", view, e)


def persist_period_frame(
    df: pl.DataFrame,
    repo: KlineRepository,
    *,
    subdir: str,
    view: str,
    refresh_view: bool = True,
) -> int:
    if df.is_empty() or "date" not in df.columns:
        return 0
    repo.append_period_kline(df, subdir)
    if refresh_view:
        refresh_period_view(repo, subdir=subdir, view=view)
    return int(df.height)


def _sync_persist_chunks(
    kind: PeriodKlineKind,
    symbols: list[str],
    repo: KlineRepository,
    *,
    start_time: datetime,
    end_time: datetime,
    on_chunk_done: Callable[[int, int], None] | None = None,
) -> tuple[int, int]:
    chunks = list(chunked(symbols, _chunk_size(kind)))
    if not chunks:
        return 0, 0
    total_written = 0
    total_fetched = 0
    for i, chunk in enumerate(chunks):
        df = sync_period_batch(
            kind,
            chunk,
            start_time=start_time,
            end_time=end_time,
        )
        total_fetched += int(df.height)
        is_last = i == len(chunks) - 1
        total_written += persist_period_frame(
            df, repo, subdir=kind.subdir, view=kind.view, refresh_view=is_last
        )
        if on_chunk_done:
            on_chunk_done(i + 1, len(chunks))
    return total_written, total_fetched


def sync_and_persist_period(
    kind: PeriodKlineKind,
    symbols: list[str],
    repo: KlineRepository,
    window: int,
    on_chunk_done: Callable[[int, int], None] | None = None,
) -> int:
    if not kind.provider_active() or not symbols:
        return 0
    now = cn_now().replace(tzinfo=None)
    end_d = min(last_cn_weekday(now.date()), repo.latest_daily_date() or now.date())
    last_d = repo.latest_period_kline_date(kind.view)
    step = max(7, kind.approx_days // 4)
    if last_d:
        start_d = last_d - timedelta(days=step)
    else:
        start_d = end_d - timedelta(days=max(step, max(1, window) * kind.approx_days))
    start_time = datetime.combine(start_d, time.min)
    end_time = datetime.combine(end_d, time(23, 59, 59))
    written, _ = _sync_persist_chunks(
        kind,
        symbols,
        repo,
        start_time=start_time,
        end_time=end_time,
        on_chunk_done=on_chunk_done,
    )
    return written


def backfill_period_range(
    kind: PeriodKlineKind,
    symbols: list[str],
    repo: KlineRepository,
    *,
    start_date: date,
    end_date: date,
    on_chunk_done: Callable[[int, int], None] | None = None,
) -> tuple[int, int]:
    start_time = datetime.combine(start_date, time.min)
    end_time = datetime.combine(end_date, time(23, 59, 59))
    return _sync_persist_chunks(
        kind,
        symbols,
        repo,
        start_time=start_time,
        end_time=end_time,
        on_chunk_done=on_chunk_done,
    )
