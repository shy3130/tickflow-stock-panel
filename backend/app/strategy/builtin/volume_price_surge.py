"""量价齐升 — 突破MA20 + 放量 + 收阳"""
import polars as pl

META = {
    "id": "volume_price_surge",
    "name": "量价齐升",
    "description": "突破MA20 + 放量 + 收阳",
    "tags": ["量价", "突破"],
    "params": [
        {"id": "require_ma20_breakout", "label": "要求突破MA20", "type": "bool",
         "default": True},
        {"id": "use_volume_filter", "label": "启用量比过滤", "type": "bool",
         "default": True},
        {"id": "vol_ratio_min", "label": "最低量比", "type": "float",
         "default": 2.0, "min": 0.5, "max": 10.0, "step": 0.1},
        {"id": "require_bullish_candle", "label": "要求收阳", "type": "bool",
         "default": True},
    ],
    "scoring": {"vol_ratio_5d": 0.4, "change_pct": 0.3, "momentum_20d": 0.3},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

ENTRY_SIGNALS = ["signal_ma20_breakout"]
EXIT_SIGNALS = ["signal_ma20_breakdown"]
STOP_LOSS = -0.06
MAX_HOLD_DAYS = 15
ALERTS = []


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    vol_min = params.get("vol_ratio_min", 2.0)
    expr = pl.col("symbol").is_not_null() | pl.col("symbol").is_null()
    if params.get("require_ma20_breakout", True):
        expr = expr & pl.col("signal_ma20_breakout").fill_null(False)
    if params.get("use_volume_filter", True):
        expr = expr & (pl.col("vol_ratio_5d") >= vol_min)
    if params.get("require_bullish_candle", True):
        expr = expr & (pl.col("close") > pl.col("open"))
    return expr
