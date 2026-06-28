"""Local quant-screener data bridge APIs."""
from __future__ import annotations

import asyncio
import concurrent.futures as _cf
from datetime import date
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.data import invalidate_storage_cache
from app.services.local_quant_import import (
    compare_sources,
    import_local_quant_daily,
    import_local_quant_daily_chunked,
    import_local_quant_minute,
)
from app.services.local_quant_financials import import_local_quant_adj_factor, import_local_quant_global_index_profile
from app.services.pipeline_jobs import job_store

router = APIRouter(prefix="/api/local-quant", tags=["local-quant"])
logger = logging.getLogger(__name__)
_local_quant_executor = _cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-quant")


class ImportDailyRequest(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    days: int | None = Field(default=30, ge=1, le=5000)
    compute_enriched: bool = True
    chunk_days: int = Field(default=90, ge=15, le=366)


class ImportMinuteRequest(BaseModel):
    days: int = Field(default=5, ge=1, le=30)


@router.get("/compare")
def compare(request: Request) -> dict:
    """Compare TickFlow parquet coverage with local quant-screener PostgreSQL."""
    try:
        return compare_sources(request.app.state.repo)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/import/daily")
def import_daily(body: ImportDailyRequest, request: Request) -> dict:
    """Import local quant-screener daily bars into TickFlow parquet storage."""
    try:
        result = import_local_quant_daily(
            request.app.state.repo,
            start_date=body.start_date,
            end_date=body.end_date,
            days=body.days,
            compute_enriched=body.compute_enriched,
        )
        invalidate_storage_cache()
        return result
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/import/adj-factor")
def import_adj_factor(request: Request) -> dict:
    try:
        result = import_local_quant_adj_factor(request.app.state.repo.store.data_dir)
        request.app.state.repo.store._register_views()
        request.app.state.repo.clear_cache()
        request.app.state.repo.refresh_cache()
        invalidate_storage_cache()
        return {"status": "ok", "synced": result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/import/global-index-daily")
def import_global_index_daily(request: Request) -> dict:
    try:
        result = import_local_quant_global_index_profile(request.app.state.repo)
        request.app.state.repo.store._register_views()
        request.app.state.repo.clear_cache()
        request.app.state.repo.refresh_cache()
        invalidate_storage_cache()
        return {"status": "ok", "synced": result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/import/minute")
def import_minute(body: ImportMinuteRequest, request: Request) -> dict:
    try:
        result = import_local_quant_minute(request.app.state.repo, days=body.days)
        request.app.state.repo.store._register_views()
        request.app.state.repo.clear_cache()
        request.app.state.repo.refresh_cache()
        invalidate_storage_cache()
        return {"status": "ok", "synced": result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/import/daily/job")
async def import_daily_job(body: ImportDailyRequest, request: Request) -> dict:
    """Import local quant daily bars in chunks as a tracked background job."""
    existing_id = job_store.active_id()
    if existing_id:
        existing = job_store.get(existing_id)
        if existing and existing["status"] in {"pending", "running"}:
            return {"status": "reused", "job_id": existing_id}

    repo = request.app.state.repo
    job_id = job_store.create()

    async def task() -> None:
        job_store.start(job_id)
        loop = asyncio.get_event_loop()

        def progress(
            stage: str,
            pct: int,
            msg: str,
            stage_pct: int | None = None,
            skip_log: bool = False,
        ) -> None:
            job_store.progress(job_id, stage, pct, msg, stage_pct=stage_pct, skip_log=skip_log)

        try:
            progress("local_quant_import", 1, "start local quant chunked import")

            def should_cancel() -> bool:
                current = job_store.get(job_id)
                return not current or current.get("status") != "running"

            result = await loop.run_in_executor(
                _local_quant_executor,
                lambda: import_local_quant_daily_chunked(
                    repo,
                    start_date=body.start_date,
                    end_date=body.end_date,
                    days=body.days,
                    compute_enriched=body.compute_enriched,
                    chunk_days=body.chunk_days,
                    on_progress=progress,
                    should_cancel=should_cancel,
                ),
            )
            job_store.succeed(job_id, result)
            invalidate_storage_cache()
        except Exception as exc:  # noqa: BLE001
            logger.exception("local quant import job failed")
            job_store.fail(job_id, str(exc))
            invalidate_storage_cache()

    asyncio.create_task(task())
    return {"status": "started", "job_id": job_id}
