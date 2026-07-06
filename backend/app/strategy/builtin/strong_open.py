"""强势高开 — 高开 > 3% 且保持上涨, 集合竞价强势"""
import polars as pl

META = {
    "id": "strong_open",
    "name": "强势高开",
    "description": "高开 > 3% 且收盘高于开盘价, 集合竞价强势",
    "tags": ["高开", "强势"],
    "params": [
        {"id": "use_open_gap_filter", "label": "启用高开过滤", "type": "bool",
         "default": True},
        {"id": "min_open_gap", "label": "最低高开%", "type": "float",
         "default": 3.0, "min": 1.0, "max": 10.0, "step": 0.5},
        {"id": "require_close_above_open", "label": "要求收盘高于开盘", "type": "bool",
         "default": True},
        {"id": "use_change_filter", "label": "启用涨幅过滤", "type": "bool",
         "default": True},
        {"id": "min_change", "label": "最低涨幅%", "type": "float",
         "default": 3.0, "min": 1.0, "max": 10.0, "step": 0.5},
    ],
    "scoring": {"change_pct": 0.4, "amplitude": 0.2, "amount": 0.4},
    "order_by": "score",
    "descending": True,
    "limit": 50,
}

ENTRY_SIGNALS = []
EXIT_SIGNALS = ["signal_ma20_breakdown"]
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 10
ALERTS = []


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    min_gap = params.get("min_open_gap", 3.0) / 100.0
    min_chg = params.get("min_change", 3.0) / 100.0
    expr = pl.col("symbol").is_not_null() | pl.col("symbol").is_null()
    if params.get("use_open_gap_filter", True):
        expr = expr & (pl.col("open") > pl.col("prev_close") * (1 + min_gap))
    if params.get("require_close_above_open", True):
        expr = expr & (pl.col("close") > pl.col("open"))
    if params.get("use_change_filter", True):
        expr = expr & (pl.col("change_pct") > min_chg)
    return expr
