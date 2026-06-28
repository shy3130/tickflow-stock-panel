"""财务数据 API — 独立路由, Cap.FINANCIAL 门控。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import polars as pl
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.financial_sync import get_financial_df
from app.services.financial_analyzer import analyze_financials_stream
from app import secrets_store
from app.services.local_quant_financials import import_local_quant_financials, import_tushare_financials
from app.services import ai_reports, preferences
from app.tickflow.capabilities import Cap

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/financials", tags=["financials"])


def _local_financial_tables(data_dir) -> dict[str, dict]:
    tables = {}
    for table in ("metrics", "income", "balance_sheet", "cash_flow"):
        path = data_dir / "financials" / table / "part.parquet"
        if path.exists():
            try:
                df = pl.read_parquet(path, columns=["symbol"])
                tables[table] = {
                    "rows": len(df),
                    "symbols": df["symbol"].n_unique() if not df.is_empty() else 0,
                }
                continue
            except Exception:
                pass
        tables[table] = {"rows": 0, "symbols": 0}
    return tables


def _has_local_financials(data_dir) -> bool:
    return any(item["rows"] > 0 for item in _local_financial_tables(data_dir).values())


def _record_local_financial_sync(request: Request, result: dict[str, int]) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    fs = getattr(request.app.state, "financial_scheduler", None)
    for table in result:
        if table.startswith("_"):
            continue
        preferences.set_financial_sync_time(table, ts)
        if fs is not None and hasattr(fs, "_last_sync"):
            fs._last_sync[table] = ts


def _require_financial_or_local(request: Request) -> None:
    capset = request.app.state.capabilities
    data_dir = request.app.state.repo.store.data_dir
    if not capset.has(Cap.FINANCIAL) and not _has_local_financials(data_dir):
        capset.require(Cap.FINANCIAL)


@router.get("/status")
def financial_status(request: Request):
    """返回各财务表的同步状态。无需 FINANCIAL 权限（前端根据 available 决定是否展示）。"""
    capset = request.app.state.capabilities
    data_dir = request.app.state.repo.store.data_dir
    tables = _local_financial_tables(data_dir)
    has_local = any(item["rows"] > 0 for item in tables.values())
    if not capset.has(Cap.FINANCIAL) and not has_local:
        return {"available": False, "tables": tables}

    fs = getattr(request.app.state, "financial_scheduler", None)
    last_sync = fs.last_sync if fs else {}

    return {
        "available": True,
        "tables": tables,
        "last_sync": last_sync,
        # 服务端是否正在同步(手动触发)——前端据此显示"同步中"并防重复点击,
        # 且刷新页面后仍能正确反映服务端状态。
        "syncing": bool(fs and fs.is_syncing),
    }


@router.get("/metrics")
def get_metrics(request: Request, symbol: str | None = None):
    """查询核心财务指标。"""
    capset = request.app.state.capabilities
    data_dir = request.app.state.repo.store.data_dir
    if not capset.has(Cap.FINANCIAL) and not _has_local_financials(data_dir):
        capset.require(Cap.FINANCIAL)

    df = get_financial_df(data_dir, "metrics")
    if df.is_empty():
        return {"data": []}
    if symbol:
        df = df.filter(pl.col("symbol") == symbol)
    return {"data": df.to_dicts()}


@router.get("/income")
def get_income(request: Request, symbol: str | None = None):
    """查询利润表。"""
    capset = request.app.state.capabilities
    data_dir = request.app.state.repo.store.data_dir
    if not capset.has(Cap.FINANCIAL) and not _has_local_financials(data_dir):
        capset.require(Cap.FINANCIAL)

    df = get_financial_df(data_dir, "income")
    if df.is_empty():
        return {"data": []}
    if symbol:
        df = df.filter(pl.col("symbol") == symbol)
    return {"data": df.to_dicts()}


@router.get("/balance-sheet")
def get_balance_sheet(request: Request, symbol: str | None = None):
    """查询资产负债表。"""
    capset = request.app.state.capabilities
    data_dir = request.app.state.repo.store.data_dir
    if not capset.has(Cap.FINANCIAL) and not _has_local_financials(data_dir):
        capset.require(Cap.FINANCIAL)

    df = get_financial_df(data_dir, "balance_sheet")
    if df.is_empty():
        return {"data": []}
    if symbol:
        df = df.filter(pl.col("symbol") == symbol)
    return {"data": df.to_dicts()}


@router.get("/cash-flow")
def get_cash_flow(request: Request, symbol: str | None = None):
    """查询现金流量表。"""
    capset = request.app.state.capabilities
    data_dir = request.app.state.repo.store.data_dir
    if not capset.has(Cap.FINANCIAL) and not _has_local_financials(data_dir):
        capset.require(Cap.FINANCIAL)

    df = get_financial_df(data_dir, "cash_flow")
    if df.is_empty():
        return {"data": []}
    if symbol:
        df = df.filter(pl.col("symbol") == symbol)
    return {"data": df.to_dicts()}


@router.api_route("/sync/{table}", methods=["GET", "POST"])
def sync_table(request: Request, table: str):
    """手动触发同步(立即返回,后台异步执行)。

    table: metrics / income / balance_sheet / cash_flow / all
    同步在后台线程执行,全量同步需数分钟。本接口立即返回 started 状态,
    前端通过轮询 GET /status 的 syncing 字段观察进度。
    """
    valid_tables = {"metrics", "income", "balance_sheet", "cash_flow", "all"}
    if table not in valid_tables:
        raise HTTPException(400, f"invalid table: {table}, expected one of {valid_tables}")

    capset = request.app.state.capabilities
    data_dir = request.app.state.repo.store.data_dir
    if not capset.has(Cap.FINANCIAL):
        target = None if table == "all" else table
        try:
            result = import_local_quant_financials(data_dir, target)
            source = "local_quant"
        except Exception as local_exc:
            if not secrets_store.get_tushare_token():
                raise HTTPException(500, f"local quant financial import failed: {local_exc}") from local_exc
            try:
                result = import_tushare_financials(data_dir, target)
                source = "tushare"
            except Exception as tushare_exc:
                raise HTTPException(
                    500,
                    f"local quant financial import failed: {local_exc}; Tushare financial import failed: {tushare_exc}",
                ) from tushare_exc
        try:
            _record_local_financial_sync(request, result)
            request.app.state.repo.store._register_views()
            request.app.state.repo.clear_cache()
            request.app.state.repo.refresh_cache()
            return {"status": "ok", "synced": {"started": True, "source": source, "rows": result}}
        except Exception as e:
            raise HTTPException(500, f"financial import post-process failed: {e}") from e

    fs = getattr(request.app.state, "financial_scheduler", None)
    if not fs:
        return {"status": "error", "message": "FinancialScheduler not available"}

    target = None if table == "all" else table
    result = fs.trigger(target)

    return {"status": "ok", "synced": result}


@router.post("/local-quant/import/{table}")
def import_local_quant_table(request: Request, table: str):
    valid_tables = {"metrics", "income", "balance_sheet", "cash_flow", "all"}
    if table not in valid_tables:
        raise HTTPException(400, f"invalid table: {table}, expected one of {valid_tables}")
    data_dir = request.app.state.repo.store.data_dir
    target = None if table == "all" else table
    try:
        result = import_local_quant_financials(data_dir, target)
        _record_local_financial_sync(request, result)
        request.app.state.repo.store._register_views()
        request.app.state.repo.clear_cache()
        request.app.state.repo.refresh_cache()
        return {"status": "ok", "synced": result}
    except Exception as e:
        raise HTTPException(500, f"local quant financial import failed: {e}") from e


class AnalyzeRequest(BaseModel):
    """AI 财务分析请求。"""
    symbol: str
    focus: str = ""  # 可选:用户追加的分析关注点


@router.post("/analyze")
async def analyze_financials(request: Request, req: AnalyzeRequest):
    """AI 财务分析 — SSE 流式返回。

    后端读取该标的 4 张财务表 → 注入 CFA 分析师级提示词 → 流式调用 LLM →
    逐 chunk 以 SSE 形式推给前端(JSON per line, 非 text/event-stream,
    以便前端用 ReadableStream 逐行解析,更简单可靠)。
    """
    _require_financial_or_local(request)

    if not req.symbol:
        raise HTTPException(400, "symbol 不能为空")

    data_dir = request.app.state.repo.store.data_dir

    async def stream_gen():
        async for chunk in analyze_financials_stream(data_dir, req.symbol, req.focus):
            yield chunk + "\n"

    return StreamingResponse(
        stream_gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ================================================================
# AI 报告 CRUD(历史报告持久化)
# ================================================================

class SaveReportRequest(BaseModel):
    """保存一条 AI 财务分析报告。"""
    symbol: str
    name: str = ""
    focus: str = ""
    content: str
    periods: int | None = None
    summary: str = ""


@router.get("/reports")
def list_reports(request: Request):
    """获取全部历史报告(按时间降序,后端已裁剪到上限)。无需 FINANCIAL 能力读取列表元信息。"""
    capset = request.app.state.capabilities
    data_dir = request.app.state.repo.store.data_dir
    if not capset.has(Cap.FINANCIAL) and not _has_local_financials(data_dir):
        return {"reports": []}
    return {"reports": ai_reports.list_reports()}


@router.post("/reports")
def save_report(request: Request, req: SaveReportRequest):
    """保存一条报告。"""
    _require_financial_or_local(request)
    report = ai_reports.save_report({
        "symbol": req.symbol,
        "name": req.name,
        "focus": req.focus,
        "content": req.content,
        "periods": req.periods,
        "summary": req.summary,
    })
    return {"ok": True, "report": report}


@router.delete("/reports/{report_id}")
def delete_report(request: Request, report_id: str):
    """删除一条报告。"""
    _require_financial_or_local(request)
    ok = ai_reports.delete_report(report_id)
    return {"ok": ok}
