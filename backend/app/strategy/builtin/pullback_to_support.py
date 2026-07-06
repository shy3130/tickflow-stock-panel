"""缩量回踩 — 回踩MA20附近 + 缩量 + 中期趋势向上"""
import polars as pl

META = {
    "id": "pullback_to_support",
    "name": "缩量回踩",
    "description": "回踩MA20附近 + 缩量 + 中期趋势向上",
    "tags": ["回踩", "支撑"],
    "params": [
        {"id": "use_ma20_proximity", "label": "启用MA20附近过滤", "type": "bool",
         "default": True},
        {"id": "ma_proximity", "label": "均线偏离度", "type": "float",
         "default": 0.02, "min": 0.01, "max": 0.05, "step": 0.005},
        {"id": "use_volume_filter", "label": "启用缩量过滤", "type": "bool",
         "default": True},
        {"id": "vol_ratio_max", "label": "最大量比", "type": "float",
         "default": 0.8, "min": 0.2, "max": 1.5, "step": 0.1},
        {"id": "require_above_ma60", "label": "要求收盘价在MA60上方", "type": "bool",
         "default": True},
        {"id": "require_positive_momentum", "label": "要求20日动量为正", "type": "bool",
         "default": True},
    ],
    "scoring": {"momentum_60d": 0.4, "momentum_20d": 0.3, "turnover_rate": 0.3},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

ENTRY_SIGNALS = ["signal_ma_golden_5_20"]
EXIT_SIGNALS = ["signal_ma20_breakdown"]
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 20
ALERTS = []


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    proximity = params.get("ma_proximity", 0.02)
    vol_max = params.get("vol_ratio_max", 0.8)
    expr = pl.col("symbol").is_not_null() | pl.col("symbol").is_null()
    if params.get("use_ma20_proximity", True):
        expr = (
            expr
            & (pl.col("close") > pl.col("ma20") * (1 - proximity))
            & (pl.col("close") < pl.col("ma20") * (1 + proximity))
        )
    if params.get("use_volume_filter", True):
        expr = expr & (pl.col("vol_ratio_5d") < vol_max)
    if params.get("require_above_ma60", True):
        expr = expr & (pl.col("close") > pl.col("ma60"))
    if params.get("require_positive_momentum", True):
        expr = expr & (pl.col("momentum_20d") > 0)
    return expr
