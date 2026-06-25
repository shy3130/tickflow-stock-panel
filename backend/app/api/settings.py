"""设置 API — Key 配置 / 模式切换。

提供面向非开发者的 UI 配置入口,避免逼用户改 .env。
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import secrets_store
from app.tickflow import client as tf_client
from app.tickflow.policy import (
    detect_capabilities,
    extras_caps,
    missing_caps,
    probe_log,
    tier_label,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# 默认端点 —— endpoints.json 列表第一项,UI"当前使用"始终对齐此项。
# 注意:Free 模式 SDK 实际走 free-api(免费数据通道),但 UI 显示统一用默认节点。
DEFAULT_PAID_ENDPOINT = "https://api.tickflow.org"


class TickflowKeyIn(BaseModel):
    api_key: str


@router.get("")
def get_settings() -> dict:
    """返回当前配置概况(Key 脱敏)。"""
    from app.config import settings
    from app.services import preferences

    key = secrets_store.get_tickflow_key()
    return {
        "mode": tf_client.current_mode(),
        "tickflow_api_key_masked": secrets_store.mask(key),
        "has_tickflow_key": bool(key),
        "tier_label": tier_label(),
        "current_endpoint": tf_client.current_endpoint(),
        "probe_log": probe_log(),
        "missing_caps": missing_caps(),
        "extras_caps": extras_caps(),
        # 首次使用引导
        "onboarding_completed": preferences.get_onboarding_completed(),
        # AI 配置
        "ai_provider": secrets_store.get_ai_config("ai_provider", settings.ai_provider),
        "ai_base_url": secrets_store.get_ai_config("ai_base_url", settings.ai_base_url),
        "ai_api_key_masked": secrets_store.mask(secrets_store.get_ai_key()),
        "has_ai_key": bool(secrets_store.get_ai_key()),
        "ai_model": secrets_store.get_ai_config("ai_model", settings.ai_model),
        "ai_daily_token_budget": int(secrets_store.get_ai_config("ai_daily_token_budget", str(settings.ai_daily_token_budget)) or settings.ai_daily_token_budget),
        "ai_user_agent": secrets_store.get_ai_config("ai_user_agent", settings.ai_user_agent),
    }


class SwitchEndpointIn(BaseModel):
    url: str


@router.post("/switch_endpoint")
def switch_endpoint(req: SwitchEndpointIn, request: Request) -> dict:
    """切换 TickFlow 端点并立即生效。

    端点切换仅对付费档(starter+,走 api.tickflow.org)有意义;
    none/free 档运行在 free-api 服务器,无付费端点权限,禁止切换。
    """
    # none/free 档没有付费端点权限,禁止切换
    if tf_client.current_mode() != "api_key":
        return {"ok": False, "error": "当前档位无法切换端点,仅付费套餐(Starter+)支持"}

    url = req.url.strip().rstrip("/")
    if not url.startswith("https://"):
        return {"ok": False, "error": "仅支持 HTTPS 端点"}

    # 持久化到 secrets.json
    secrets_store.save({"tickflow_base_url": url})
    # 重置客户端，下次调用自动用新端点
    tf_client.reset_clients()

    return {
        "ok": True,
        "current_endpoint": tf_client.current_endpoint(),
    }


@router.post("/tickflow-key")
def save_tickflow_key(req: TickflowKeyIn, request: Request) -> dict:
    """保存 TickFlow API Key 并立即重新探测能力。

    先探后存(关键改动,修复乱填 key 也会被持久化的问题):
      1. 临时用新 key 探测(付费端点),判定档位
      2. 判定为 none(连单只日K都拿不到)→ key 无效:不存,清除已存的,
         返回 {ok: false, reason: "invalid"},前端提示「Key 无效」
      3. 判定为 free(免费有效 key)→ 存 key,客户端切到 free-api 服务器
      4. 判定为 starter+ → 存 key,切到付费端点(现有逻辑)

    端点联动:从无 key 升级到付费 key 时,残留的 free-api 端点不可用,
    故自动切到默认付费端点(api.tickflow.org);free 档则清除自定义端点。
    """
    from app.tickflow.policy import (
        base_tier_name, is_invalid_key,
    )

    key = req.api_key.strip()
    if not key:
        return {"ok": False, "error": "key empty"}

    # ===== 1) 临时存 key + 重置客户端,让探测走付费端点 =====
    secrets_store.save({"tickflow_api_key": key})
    tf_client.reset_clients()

    # 立即重新探测(此时 client 已按档位判定,但首次探测必然走付费端点验证)
    capset = detect_capabilities(force=True)
    request.app.state.capabilities = capset

    # ===== 2) 判定为无效 key(连单只日K都拿不到)→ 不存,清除 =====
    if is_invalid_key() or base_tier_name() == "none":
        # 无效 key:清除刚存的,避免乱填被持久化;退回 none 档
        secrets_store.clear("tickflow_api_key", "tickflow_base_url")
        tf_client.reset_clients()
        capset = detect_capabilities(force=True)
        request.app.state.capabilities = capset
        return {
            "ok": False,
            "reason": "invalid",
            "error": "Key 无效或已过期,请检查后重试",
            "mode": "none",
            "tier_label": tier_label(),
            "current_endpoint": tf_client.current_endpoint(),
            "probe_log": [],
            "capabilities_count": len(capset.all()),
        }

    # ===== 3) free 档(免费有效 key)→ 存 key,切到 free-api 服务器 =====
    if base_tier_name() == "free":
        # 免费档运行时走 free-api 服务器,清除付费端点的自定义配置
        secrets_store.clear("tickflow_base_url")
        tf_client.reset_clients()
        return {
            "ok": True,
            "tickflow_api_key_masked": secrets_store.mask(key),
            "mode": "free",
            "tier_label": tier_label(),
            "current_endpoint": tf_client.current_endpoint(),
            "probe_log": [],
            "capabilities_count": len(capset.all()),
        }

    # ===== 4) starter+ 付费档 → 确保走付费端点(现有逻辑) =====
    # 若之前是 none/free(无自定义付费端点),切到默认付费端点
    base = secrets_store.load().get("tickflow_base_url")
    if not base:
        secrets_store.save({"tickflow_base_url": DEFAULT_PAID_ENDPOINT})
    tf_client.reset_clients()

    return {
        "ok": True,
        "tickflow_api_key_masked": secrets_store.mask(key),
        "mode": "api_key",
        "tier_label": tier_label(),
        "current_endpoint": tf_client.current_endpoint(),
        "probe_log": [],
        "capabilities_count": len(capset.all()),
    }


@router.delete("/tickflow-key")
def clear_tickflow_key(request: Request) -> dict:
    """清除 Key,退回无档(none)。

    同时清除 tickflow_base_url(测速切换的自定义端点),使客户端走 free-api
    服务器取历史日K;档位标签为 None(无档)。
    """
    secrets_store.clear("tickflow_api_key", "tickflow_base_url")
    tf_client.reset_clients()

    capset = detect_capabilities(force=True)
    request.app.state.capabilities = capset

    return {
        "ok": True,
        "mode": "none",
        "tier_label": tier_label(),
        "current_endpoint": tf_client.current_endpoint(),
        "capabilities_count": len(capset.all()),
    }


@router.post("/onboarding/complete")
def complete_onboarding() -> dict:
    """标记首次使用向导完成。

    写入 preferences.json,前端守卫据此判断是否需要再次展示向导。
    跨设备/清缓存安全 —— 状态落在后端文件,不依赖浏览器本地存储。
    """
    from app.services import preferences
    done = preferences.set_onboarding_completed(True)
    return {"ok": True, "onboarding_completed": done}


class AiSettingsIn(BaseModel):
    provider: str = "openai_compat"
    base_url: str = ""
    api_key: str | None = None
    model: str = ""
    daily_token_budget: int = 500_000
    user_agent: str = ""


@router.post("/ai")
def save_ai_settings(req: AiSettingsIn) -> dict:
    """保存 AI 配置（全部持久化到 secrets.json）"""
    from app.config import settings

    updates: dict = {}
    if req.provider:
        updates["ai_provider"] = req.provider
        settings.ai_provider = req.provider
    if req.base_url:
        updates["ai_base_url"] = req.base_url
        settings.ai_base_url = req.base_url
    if req.api_key is not None:
        if req.api_key:
            updates["ai_api_key"] = req.api_key
            settings.ai_api_key = req.api_key
        else:
            secrets_store.clear("ai_api_key")
            settings.ai_api_key = ""
    if req.model:
        updates["ai_model"] = req.model
        settings.ai_model = req.model
    updates["ai_daily_token_budget"] = req.daily_token_budget
    settings.ai_daily_token_budget = req.daily_token_budget
    # user_agent 允许清空(回到默认浏览器 UA),故无条件持久化
    updates["ai_user_agent"] = req.user_agent
    settings.ai_user_agent = req.user_agent

    if updates:
        secrets_store.save(updates)

    return {"ok": True}


# ===== 偏好设置 =====

def _realtime_allowed() -> bool:
    """当前档位是否允许实时行情(none/free 不允许)。"""
    from app.services.quote_service import QuoteService
    return QuoteService.is_realtime_allowed()


class MinuteSyncPrefs(BaseModel):
    minute_sync_enabled: bool
    minute_sync_days: int = 5


@router.get("/preferences")
def get_preferences() -> dict:
    """返回用户偏好设置。"""
    from app.services import preferences
    return {
        "realtime_quotes_enabled": preferences.get_realtime_quotes_enabled(),
        "realtime_allowed": _realtime_allowed(),
        "indices_nav_pinned": preferences.get_indices_nav_pinned(),
        "minute_sync_enabled": preferences.get_minute_sync_enabled(),
        "minute_sync_days": preferences.get_minute_sync_days(),
        "pipeline_schedule": preferences.get_pipeline_schedule(),
        "instruments_schedule": preferences.get_instruments_schedule(),
        "enriched_batch_size": preferences.get_enriched_batch_size(),
        "index_daily_batch_size": preferences.get_index_daily_batch_size(),
        "watchlist_columns": preferences.get_watchlist_columns(),
        "screener_result_columns": preferences.get_screener_result_columns(),
        "sse_refresh_pages": preferences.get_sse_refresh_pages(),
        "strategy_monitor_enabled": preferences.get_strategy_monitor_enabled(),
        "strategy_monitor_ids": preferences.get_strategy_monitor_ids(),
        "system_notify_enabled": preferences.get_system_notify_enabled(),
        "sidebar_index_symbols": preferences.get_sidebar_index_symbols(),
        "nav_order": preferences.get_nav_order(),
        "nav_hidden": preferences.get_nav_hidden(),
        "screener_auto_run": preferences.get_screener_auto_run(),
        "limit_ladder_monitor_enabled": preferences.get_limit_ladder_monitor_enabled(),
        "depth_polling_interval": preferences.get_depth_polling_interval(),
        "depth_finalize_time": preferences.get_depth_finalize_time(),
    }


@router.get("/preferences/watchlist-columns")
def get_watchlist_columns() -> dict:
    """返回自选列表列配置。"""
    from app.services import preferences
    cols = preferences.get_watchlist_columns()
    return {"columns": cols}


class NavOrderIn(BaseModel):
    nav_order: list[str]


class NavHiddenIn(BaseModel):
    nav_hidden: list[str]


@router.put("/preferences/nav-order")
def update_nav_order(req: NavOrderIn) -> dict:
    """保存左侧菜单排序（内置页面 path + 扩展分析菜单 id 的有序列表）。"""
    from app.services import preferences
    saved = preferences.set_nav_order(req.nav_order)
    return {"nav_order": saved}


@router.put("/preferences/nav-hidden")
def update_nav_hidden(req: NavHiddenIn) -> dict:
    """保存左侧菜单隐藏项。"""
    from app.services import preferences
    saved = preferences.set_nav_hidden(req.nav_hidden)
    return {"nav_hidden": saved}


@router.put("/preferences/watchlist-columns")
def update_watchlist_columns(req: dict) -> dict:
    """保存自选列表列配置。"""
    from app.services import preferences
    columns = req.get("columns", [])
    saved = preferences.set_watchlist_columns(columns)
    return {"columns": saved}


@router.get("/preferences/screener-result-columns")
def get_screener_result_columns() -> dict:
    """返回策略结果列表列配置。"""
    from app.services import preferences
    cols = preferences.get_screener_result_columns()
    return {"columns": cols}


@router.put("/preferences/screener-result-columns")
def update_screener_result_columns(req: dict) -> dict:
    """保存策略结果列表列配置。"""
    from app.services import preferences
    columns = req.get("columns", [])
    saved = preferences.set_screener_result_columns(columns)
    return {"columns": saved}


@router.put("/preferences/minute-sync")
def update_minute_sync(req: MinuteSyncPrefs) -> dict:
    """保存分钟 K 同步偏好。"""
    from app.services import preferences
    days = max(1, min(30, req.minute_sync_days))
    preferences.save({
        "minute_sync_enabled": req.minute_sync_enabled,
        "minute_sync_days": days,
    })
    return {
        "minute_sync_enabled": req.minute_sync_enabled,
        "minute_sync_days": days,
    }


class RealtimeQuotesPrefs(BaseModel):
    realtime_quotes_enabled: bool


@router.put("/preferences/realtime-quotes")
def update_realtime_quotes(req: RealtimeQuotesPrefs, request: Request) -> dict:
    """保存全局实时行情开关。

    none/free 档无实时行情权限:拒绝开启,persist 为关闭并返回 allowed=False,
    前端据此把开关置灰 / 回弹。
    """
    from app.services import preferences
    qs = getattr(request.app.state, "quote_service", None)

    allowed = qs.is_realtime_allowed() if qs else True
    if req.realtime_quotes_enabled and not allowed:
        # 当前档位不允许开启实时行情 — 强制关闭
        preferences.save({"realtime_quotes_enabled": False})
        if qs:
            qs.disable()
        return {"realtime_quotes_enabled": False, "realtime_allowed": False}

    preferences.save({"realtime_quotes_enabled": req.realtime_quotes_enabled})
    if qs:
        if req.realtime_quotes_enabled:
            qs.enable()
        else:
            qs.disable()

    return {"realtime_quotes_enabled": req.realtime_quotes_enabled, "realtime_allowed": allowed}


class IndicesNavPinnedPrefs(BaseModel):
    indices_nav_pinned: bool


@router.put("/preferences/indices-nav-pinned")
def update_indices_nav_pinned(req: IndicesNavPinnedPrefs) -> dict:
    """保存侧栏指数报价卡片固定显示开关。
    ON=常驻显示；OFF=跟随实时行情开关（仅实时开时显示）。"""
    from app.services import preferences
    preferences.save({"indices_nav_pinned": req.indices_nav_pinned})
    return {"indices_nav_pinned": req.indices_nav_pinned}


class RealtimeMonitorConfigIn(BaseModel):
    sse_refresh_pages: dict[str, bool] | None = None
    strategy_monitor_enabled: bool | None = None
    strategy_monitor_ids: list[str] | None = None
    sidebar_index_symbols: list[str] | None = None
    screener_auto_run: bool | None = None


@router.put("/preferences/realtime-monitor")
def update_realtime_monitor_config(req: RealtimeMonitorConfigIn, request: Request) -> dict:
    """更新实时监控配置。策略监控统一迁移为 MonitorRule,由监控引擎评估。"""
    from app.services import preferences

    cfg = req.model_dump(exclude_none=True)
    result = preferences.set_realtime_monitor_config(cfg)

    # 策略监控开关/池变化 → 同步迁移为 type=strategy 规则 + reload 引擎
    if req.strategy_monitor_ids is not None or req.strategy_monitor_enabled is not None:
        monitor_engine = getattr(request.app.state, "monitor_engine", None)
        strategy_engine = getattr(request.app.state, "strategy_engine", None)
        data_dir = request.app.state.repo.store.data_dir
        if monitor_engine is not None and strategy_engine is not None:
            from app.strategy import monitor_rules as mr_store
            try:
                if preferences.get_strategy_monitor_enabled():
                    ids = preferences.get_strategy_monitor_ids()
                    names = {s.id: s.name for s in strategy_engine.list_strategies()}
                    mr_store.migrate_strategy_monitors(data_dir, ids, names)
                else:
                    # 关闭策略监控: 停用所有策略规则
                    mr_store.migrate_strategy_monitors(data_dir, [], {})
                # reload 规则到引擎
                monitor_engine.set_rules(mr_store.load_all(data_dir))
            except Exception:
                pass

    return result


class QuoteIntervalIn(BaseModel):
    interval: float


class SystemNotifyPrefsIn(BaseModel):
    enabled: bool


@router.put("/preferences/system-notify")
def update_system_notify(req: SystemNotifyPrefsIn) -> dict:
    """系统通知开关 — 开启后监控告警同时推送到操作系统通知中心。

    纯偏好, 无副作用 (不像策略监控要迁移规则), 直接落盘即可。
    quote_service 在每轮告警评估时读此开关决定是否发系统通知。
    """
    from app.services import preferences
    saved = preferences.set_system_notify_enabled(req.enabled)
    return {"system_notify_enabled": saved}


@router.put("/preferences/quote-interval")
def update_quote_interval(req: QuoteIntervalIn, request: Request) -> dict:
    """更新行情轮询间隔。按档位自动 clamp。"""
    qs = getattr(request.app.state, "quote_service", None)
    if not qs:
        return {"interval": req.interval, "min_interval": qs.get_min_interval(), "max_interval": 60.0}
    clamped = qs.set_interval(req.interval)
    return {
        "interval": clamped,
        "min_interval": qs.get_min_interval(),
        "max_interval": qs.MAX_INTERVAL,
    }


@router.get("/preferences/quote-interval")
def get_quote_interval(request: Request) -> dict:
    """获取当前行情轮询间隔和档位限制。"""
    qs = getattr(request.app.state, "quote_service", None)
    if not qs:
        return {"interval": 10.0, "min_interval": 5.0, "max_interval": 60.0}
    return {
        "interval": qs._interval,
        "min_interval": qs.get_min_interval(),
        "max_interval": qs.MAX_INTERVAL,
    }


class TestEndpointIn(BaseModel):
    url: str
    # 测试轮数;不传时取 endpoints.json 的 testRounds(默认 5)
    rounds: int | None = None


# 官方端点发现清单 —— 前端浏览器无法直接跨域拉取 tickflow.org/endpoints.json
# (无 CORS 头),因此由后端代理。缓存 5 分钟,失败时回退到内置列表。
ENDPOINTS_URL = "https://tickflow.org/endpoints.json"
ENDPOINTS_TTL = 300.0  # 秒

# 回退列表 —— 与官方 endpoints.json 的 endpoints[] 字段对齐。
# 当远程拉取失败时使用,保证 UI 永远有内容可显示。
_FALLBACK_ENDPOINTS: list[dict] = [
    {
        "id": "default",
        "url": "https://api.tickflow.org",
        "label": "默认端点",
        "region": "auto",
        "description": "默认端点",
        "premium": False,
    },
    {
        "id": "hk",
        "url": "https://hk-api.tickflow.org",
        "label": "香港端点",
        "region": "ap-east-1",
        "description": "备用端点，部分地区访问更稳定",
        "premium": False,
    },
    {
        "id": "sg",
        "url": "https://sg-api.tickflow.org",
        "label": "新加坡端点",
        "region": "ap-southeast-1",
        "description": "备用端点，亚太地区访问更稳定",
        "premium": False,
    },
    {
        "id": "us",
        "url": "https://us-api.tickflow.org",
        "label": "美国端点",
        "region": "us-east-1",
        "description": "备用端点，欧美地区访问更稳定",
        "premium": False,
    },
    {
        "id": "cn",
        "url": "https://139.196.55.234:50443",
        "label": "中国大陆端点（Beta）",
        "region": "cn-east-1",
        "description": "备用端点，中国大陆地区访问更稳定，目前处于测试阶段，谨慎使用",
        "premium": False,
    },
    {
        "id": "cn-premium",
        "url": "https://106.15.238.72:50443",
        "label": "中国大陆专线端点",
        "region": "cn-east-1",
        "description": "专线加速端点，需要专线加速权限（该权限包含在 Expert 及以上套餐中，也可通过自定义组合单独开通）",
        "premium": True,
    },
]

# 进程内缓存:{ "ts": float, "data": dict }
_endpoints_cache: dict = {"ts": 0.0, "data": None}


@router.get("/endpoints")
def list_endpoints() -> dict:
    """代理拉取 tickflow.org/endpoints.json 并返回规范化端点列表。

    前端无法跨域直连该 URL(无 CORS 头),故由本接口代理。带 8s 超时、
    5 分钟内存缓存,远程失败时回退到内置列表,保证 UI 始终有内容。
    返回结构与原始 endpoints.json 一致(透传 schema/version 等元信息)。
    """
    import httpx

    now = time.monotonic()
    cached = _endpoints_cache.get("data")
    if cached is not None and (now - _endpoints_cache["ts"]) < ENDPOINTS_TTL:
        return cached

    source = "remote"
    data: dict | None = None
    try:
        resp = httpx.get(ENDPOINTS_URL, timeout=8.0, follow_redirects=True)
        if resp.status_code == 200:
            parsed = resp.json()
            eps = parsed.get("endpoints")
            # 校验:必须是列表且每项含必要字段,否则视为无效
            if isinstance(eps, list) and all(
                isinstance(e, dict) and "url" in e for e in eps
            ):
                data = {
                    "version": parsed.get("version", 1),
                    "description": parsed.get(
                        "description", "TickFlow API 端点配置"
                    ),
                    "healthPath": parsed.get("healthPath", "/health"),
                    "testRounds": parsed.get("testRounds", 5),
                    "endpoints": eps,
                }
    except (httpx.HTTPError, ValueError):
        logger.warning("拉取 endpoints.json 失败，使用内置回退列表", exc_info=True)

    if data is None:
        source = "fallback"
        data = {
            "version": 1,
            "description": "TickFlow API 端点配置",
            "healthPath": "/health",
            "testRounds": 5,
            "endpoints": _FALLBACK_ENDPOINTS,
        }

    # 标记数据来源,便于前端提示(回退时显示"内置列表")。
    data["source"] = source
    _endpoints_cache["ts"] = now
    _endpoints_cache["data"] = data
    return data


async def _http_ping(url: str, timeout: float = 10.0) -> float | None:
    """单次异步 GET 请求并返回延迟(ms),失败返回 None。

    对齐官方 latency_test.py:用 /health 轻量端点测真实网络延迟,
    不携带 API Key(/health 公开)。异步实现,保证多端点并行测速不阻塞。
    """
    import httpx

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            dt = (time.perf_counter() - t0) * 1000
            # 只把 <400 视为成功;4xx/5xx 也算"不可达"
            if resp.status_code < 400:
                return round(dt, 2)
            return None
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError, OSError):
        return None


@router.post("/test_endpoint")
async def test_endpoint(req: TestEndpointIn) -> dict:
    """测试端点网络延迟:对 /health 多轮探测取中位数。

    参考 TickFlow 官方 latency_test.py:
    - 路径用 /health(公开、轻量),反映真实网络延迟而非业务接口耗时
    - 多轮探测(默认 5 轮,取自 endpoints.json 的 testRounds),间隔 0.3s
    - 返回 median/min/max/success,前端显示中位数
    - 异步实现,保证"全部测速"时多端点真正并行
    """
    import asyncio
    import statistics

    base = req.url.rstrip("/")
    rounds = max(1, min(10, req.rounds or _endpoints_cache.get("data", {}).get("testRounds", 5)))
    health_url = base + "/health"

    latencies: list[float] = []
    for _ in range(rounds):
        ms = await _http_ping(health_url)
        if ms is not None:
            latencies.append(ms)
        # 官方脚本间隔 0.3s;末轮无需等待
        await asyncio.sleep(0.3)

    success = len(latencies)
    if success == 0:
        return {
            "ok": False,
            "error": "不可达",
            "url": req.url,
            "rounds": rounds,
            "success": 0,
            "median_ms": None,
            "min_ms": None,
            "max_ms": None,
        }

    median = round(statistics.median(latencies), 2)
    return {
        "ok": True,
        "url": req.url,
        "rounds": rounds,
        "success": success,
        "median_ms": median,
        "min_ms": round(min(latencies), 2),
        "max_ms": round(max(latencies), 2),
        # 兼容旧字段:取中位数作为代表延迟
        "latency_ms": median,
    }


class PipelineScheduleIn(BaseModel):
    hour: int
    minute: int


@router.put("/preferences/pipeline-schedule")
def update_pipeline_schedule(req: PipelineScheduleIn, request: Request) -> dict:
    """保存盘后管道调度时间并立即 reschedule。"""
    from app.services import preferences
    sched = preferences.set_pipeline_schedule(req.hour, req.minute)

    # 动态 reschedule
    from apscheduler.triggers.cron import CronTrigger
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        scheduler.reschedule_job(
            "daily_pipeline",
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=sched["hour"],
                minute=sched["minute"],
                timezone="Asia/Shanghai",
            ),
        )
        logger.info("pipeline rescheduled to %02d:%02d mon-fri", sched["hour"], sched["minute"])

    return sched


@router.put("/preferences/instruments-schedule")
def update_instruments_schedule(req: PipelineScheduleIn, request: Request) -> dict:
    """保存盘前标的维表调度时间并立即 reschedule。"""
    from app.services import preferences
    sched = preferences.set_instruments_schedule(req.hour, req.minute)

    from apscheduler.triggers.cron import CronTrigger
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        scheduler.reschedule_job(
            "pre_market_instruments",
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=sched["hour"],
                minute=sched["minute"],
                timezone="Asia/Shanghai",
            ),
        )
        return sched


class EnrichedBatchSizeIn(BaseModel):
    size: int


@router.put("/preferences/enriched-batch-size")
def update_enriched_batch_size(req: EnrichedBatchSizeIn) -> dict:
    """保存 enriched 全量计算批次大小。"""
    from app.services import preferences
    size = preferences.set_enriched_batch_size(req.size)
    return {"enriched_batch_size": size}


class IndexDailyBatchSizeIn(BaseModel):
    size: int


@router.put("/preferences/index-daily-batch-size")
def update_index_daily_batch_size(req: IndexDailyBatchSizeIn) -> dict:
    """保存指数日 K 同步批次大小。"""
    from app.services import preferences
    size = preferences.set_index_daily_batch_size(req.size)
    return {"index_daily_batch_size": size}


# ── 五档盘口 sealed 配置 ──────────────────────────────

class LimitLadderMonitorIn(BaseModel):
    enabled: bool


@router.put("/preferences/limit-ladder-monitor")
def update_limit_ladder_monitor(req: LimitLadderMonitorIn, request: Request) -> dict:
    """连板梯队 5 档监控开关。开启→启动 depth 轮询, 关闭→停止。"""
    from app.services import preferences
    preferences.save({"limit_ladder_monitor_enabled": req.enabled})

    # 立即应用: 启停 depth 轮询线程
    depth_svc = getattr(request.app.state, "depth_service", None)
    if depth_svc:
        depth_svc.apply_monitor_toggle(req.enabled)

    return {"limit_ladder_monitor_enabled": req.enabled}


@router.post("/preferences/limit-ladder-monitor/run")
def run_limit_ladder_fix(request: Request) -> dict:
    """立即手动修正一次真假板(拉取五档盘口 + 更新缓存)。需 Pro+。"""
    from app.tickflow.capabilities import Cap
    capset = request.app.state.capabilities
    capset.require(Cap.DEPTH5_BATCH)  # 无能力抛 CapabilityDenied(403)

    depth_svc = getattr(request.app.state, "depth_service", None)
    if not depth_svc:
        raise HTTPException(status_code=503, detail="depth 服务未初始化")
    return depth_svc.run_once()


class DepthPollingIntervalIn(BaseModel):
    interval: float


@router.put("/preferences/depth-polling-interval")
def update_depth_polling_interval(req: DepthPollingIntervalIn, request: Request) -> dict:
    """保存五档盘口盘中轮询间隔(秒)。需 Pro+。"""
    from app.tickflow.capabilities import Cap
    request.app.state.capabilities.require(Cap.DEPTH5_BATCH)

    from app.services import preferences
    interval = preferences.set_depth_polling_interval(req.interval)
    return {"depth_polling_interval": interval}


class DepthFinalizeTimeIn(BaseModel):
    hour: int
    minute: int


@router.put("/preferences/depth-finalize-time")
def update_depth_finalize_time(req: DepthFinalizeTimeIn, request: Request) -> dict:
    """保存盘后 sealed 定版时间(范围15:01~18:00)并立即 reschedule。需 Pro+。"""
    from app.tickflow.capabilities import Cap
    request.app.state.capabilities.require(Cap.DEPTH5_BATCH)

    from app.services import preferences
    sched = preferences.set_depth_finalize_time(req.hour, req.minute)

    from apscheduler.triggers.cron import CronTrigger
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        scheduler.reschedule_job(
            "depth_finalize",
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=sched["hour"],
                minute=sched["minute"],
                timezone="Asia/Shanghai",
            ),
        )
        logger.info("depth_finalize rescheduled to %02d:%02d mon-fri", sched["hour"], sched["minute"])

    return sched

