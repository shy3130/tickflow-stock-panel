"""External data pull engine.

Fetches JSON from configured external APIs and writes rows into ext_data
parquet storage. Existing generic array responses are supported, plus the
Tushare Pro shape: {"data": {"fields": [...], "items": [[...], ...]}}.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.ext_data import (
    ExtConfig,
    ExtConfigStore,
    PullConfig,
    rows_to_parquet,
)

logger = logging.getLogger(__name__)


def _template_values() -> dict[str, str]:
    today = date.today()
    last_weekday = today
    while last_weekday.weekday() >= 5:
        last_weekday -= timedelta(days=1)
    try:
        from app import secrets_store

        tushare_token = secrets_store.get_tushare_token()
    except Exception:
        tushare_token = ""
    return {
        "TUSHARE_TOKEN": tushare_token,
        "TUSHARE_HTTP_URL": secrets_store.get_tushare_http_url(),
        "TODAY": today.isoformat(),
        "TODAY_YYYYMMDD": today.strftime("%Y%m%d"),
        "LAST_WEEKDAY": last_weekday.isoformat(),
        "LAST_WEEKDAY_YYYYMMDD": last_weekday.strftime("%Y%m%d"),
        "NOW_ISO": datetime.now(timezone.utc).isoformat(),
    }


def _render_text_template(value: str, values: dict[str, str]) -> str:
    rendered = value
    for key, val in values.items():
        rendered = rendered.replace("${" + key + "}", val)
    return rendered


def _render_template(value: Any, values: dict[str, str] | None = None) -> Any:
    vals = values or _template_values()
    if isinstance(value, str):
        return _render_text_template(value, vals)
    if isinstance(value, dict):
        return {k: _render_template(v, vals) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_template(v, vals) for v in value]
    return value


def _normalize_url(url: str) -> str:
    resolved = str(url or "").strip()
    if not resolved:
        return resolved
    if "://" not in resolved:
        resolved = f"https://{resolved}"
    return resolved


def _ensure_no_proxy_for_host(url: str) -> None:
    host = (urlparse(url or "").hostname or "").strip()
    if not host:
        return
    existing = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    entries = [item.strip() for item in existing.split(",") if item.strip()]
    lowered = {item.lower() for item in entries}
    if host.lower() not in lowered:
        entries.append(host)
    joined = ",".join(entries)
    os.environ["NO_PROXY"] = joined
    os.environ["no_proxy"] = joined


def _rows_from_fields_items(value: Any) -> list[dict] | None:
    if not isinstance(value, dict):
        return None
    fields = value.get("fields")
    items = value.get("items")
    if not isinstance(fields, list) or not isinstance(items, list):
        return None
    rows: list[dict] = []
    for item in items:
        if isinstance(item, dict):
            rows.append(item)
        elif isinstance(item, list):
            rows.append(dict(zip(fields, item)))
        else:
            raise ValueError(f"fields/items item is not list/dict: {type(item)}")
    return rows


def _coerce_rows(value: Any, path: str) -> list[dict]:
    rows = _rows_from_fields_items(value)
    if rows is not None:
        return rows
    if isinstance(value, dict):
        rows = _rows_from_fields_items(value.get("data"))
        if rows is not None:
            return rows
    if not isinstance(value, list):
        target = "response" if not path else f"path '{path}'"
        raise ValueError(f"{target} does not point to rows; got {type(value)}")
    result: list[dict] = []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError(f"row is not an object: {type(row)}")
        result.append(row)
    return result


def _extract_rows(data: Any, path: str) -> list[dict]:
    """Extract row objects by dot-path.

    Empty path treats the whole response as rows. Tushare fields/items payloads
    can be selected either at "data" or left as the whole response.
    """
    if not path:
        return _coerce_rows(data, path)

    current = data
    for key in path.split("."):
        if isinstance(current, dict):
            if key not in current:
                raise ValueError(f"response path '{path}' missing key '{key}'")
            current = current[key]
        elif isinstance(current, list):
            try:
                current = current[int(key)]
            except (ValueError, IndexError) as e:
                raise ValueError(f"response path '{path}' failed at '{key}': {e}") from e
        else:
            raise ValueError(f"response path '{path}' reached {type(current)}")

    return _coerce_rows(current, path)


def _apply_field_map(rows: list[dict], field_map: dict[str, str]) -> list[dict]:
    """Map external field names to configured internal field names."""
    if not field_map:
        return rows
    mapped = []
    for row in rows:
        new_row: dict = {}
        for k, v in row.items():
            mapped_key = field_map.get(k, k)
            new_row[mapped_key] = v
        mapped.append(new_row)
    return mapped


async def request_pull_json(pull: PullConfig) -> Any:
    """Request a pull URL after rendering local placeholders."""
    values = _template_values()
    url = _normalize_url(_render_template(pull.url, values))
    headers = _render_template(dict(pull.headers or {}), values)
    body = _render_template(pull.body, values) if pull.body else None
    _ensure_no_proxy_for_host(url)

    async with httpx.AsyncClient(timeout=30) as client:
        kwargs: dict[str, Any] = {"headers": headers}
        if pull.method.upper() == "POST" and body:
            kwargs["content"] = body
            if "content-type" not in {k.lower() for k in headers}:
                kwargs["headers"]["Content-Type"] = "application/json"
        resp = await client.request(pull.method.upper(), url, **kwargs)
        resp.raise_for_status()

    try:
        return resp.json()
    except Exception as e:
        raise ValueError(f"response is not valid JSON: {e}") from e


async def fetch_and_ingest(
    config: ExtConfig,
    data_dir,
) -> tuple[int, str]:
    """Run one pull: request external API, parse rows, write parquet."""
    pull = config.pull
    if not pull or not pull.url:
        raise ValueError("pull config or URL is empty")

    data = await request_pull_json(pull)
    rows = _extract_rows(data, pull.response_path)
    if not rows:
        raise ValueError("extracted 0 rows")

    rows = _apply_field_map(rows, pull.field_map)
    if rows and "symbol" not in rows[0]:
        raise ValueError("rows are missing symbol; configure field_map first")

    snap = date.today()
    n = rows_to_parquet(rows, config, data_dir, snapshot_date=snap)
    return n, snap.isoformat()


class PullScheduler:
    """Background scheduler for enabled ext_data pull configs."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._running = False
        self._lock = threading.Lock()

    def start(self, data_dir) -> None:
        self._running = True
        self._data_dir = data_dir
        logger.info("PullScheduler started")

    def stop(self) -> None:
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()
        logger.info("PullScheduler stopped")

    def refresh(self, data_dir) -> None:
        self._data_dir = data_dir
        store = ExtConfigStore(data_dir)
        configs = store.load_all()

        active_ids: set[str] = set()

        for config in configs:
            if not config.pull or not config.pull.enabled or not config.pull.url:
                continue
            active_ids.add(config.id)
            if config.id not in self._tasks:
                task = asyncio.create_task(self._run_loop(config))
                self._tasks[config.id] = task
                logger.info(
                    "PullScheduler: scheduled %s (every %d min)",
                    config.id,
                    config.pull.schedule_minutes,
                )

        for cid in list(self._tasks):
            if cid not in active_ids:
                self._tasks[cid].cancel()
                del self._tasks[cid]
                logger.info("PullScheduler: removed %s", cid)

    async def _run_loop(self, config: ExtConfig) -> None:
        try:
            while self._running:
                pull = config.pull
                if not pull:
                    break
                interval = max(pull.schedule_minutes * 60, 60)
                await asyncio.sleep(interval)
                if not self._running:
                    break
                try:
                    store = ExtConfigStore(self._data_dir)
                    fresh = store.get(config.id)
                    if not fresh or not fresh.pull or not fresh.pull.enabled:
                        break
                    n, d = await fetch_and_ingest(fresh, self._data_dir)
                    fresh.pull.last_run = datetime.now(timezone.utc).isoformat()
                    fresh.pull.last_status = "success"
                    fresh.pull.last_message = f"{n} rows @ {d}"
                    fresh.pull.last_rows = n
                    store.upsert(fresh)
                    logger.info("PullScheduler: %s success, %d rows", config.id, n)
                except Exception as e:
                    store = ExtConfigStore(self._data_dir)
                    fresh = store.get(config.id)
                    if fresh and fresh.pull:
                        fresh.pull.last_run = datetime.now(timezone.utc).isoformat()
                        fresh.pull.last_status = "error"
                        fresh.pull.last_message = str(e)[:200]
                        store.upsert(fresh)
                    logger.warning("PullScheduler: %s error: %s", config.id, e)
        except asyncio.CancelledError:
            pass


pull_scheduler = PullScheduler()
