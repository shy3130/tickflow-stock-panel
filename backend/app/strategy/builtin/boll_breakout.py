"""布林突破 — 突破布林上轨 + 放量"""
import polars as pl

META = {
    "id": "boll_breakout",
    "name": "布林突破",
    "description": "突破布林上轨 + 放量, 强势加速信号",
    "tags": ["布林", "突破"],
    "params": [
        {"id": "require_boll_breakout", "label": "要求突破布林上轨", "type": "bool",
         "default": True},
        {"id": "use_volume_filter", "label": "启用量比过滤", "type": "bool",
         "default": True},
        {"id": "vol_ratio_min", "label": "最低量比", "type": "float",
         "default": 1.5, "min": 0.5, "max": 5.0, "step": 0.1},
    ],
    "scoring": {"vol_ratio_5d": 0.4, "change_pct": 0.3, "momentum_20d": 0.3},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

ENTRY_SIGNALS = ["signal_boll_breakout_upper"]
EXIT_SIGNALS = ["signal_boll_breakdown_lower"]
STOP_LOSS = -0.06
MAX_HOLD_DAYS = 15
ALERTS = []


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    vol_min = params.get("vol_ratio_min", 1.5)
    expr = pl.col("symbol").is_not_null() | pl.col("symbol").is_null()
    if params.get("require_boll_breakout", True):
        expr = expr & pl.col("signal_boll_breakout_upper").fill_null(False)
    if params.get("use_volume_filter", True):
        expr = expr & (pl.col("vol_ratio_5d") >= vol_min)
    return expr
