"""均线回踩反弹 — 价格在 MA20 附近(±2%)且 MA 多头排列, 回踩买入"""
import polars as pl

META = {
    "id": "pullback_ma20_bounce",
    "name": "均线回踩反弹",
    "description": "价格在MA20附近(±2%)且MA5>MA20>MA60多头排列, 回踩买入",
    "tags": ["回踩", "均线", "反弹"],
    "params": [
        {"id": "use_ma20_proximity", "label": "启用MA20附近过滤", "type": "bool",
         "default": True},
        {"id": "ma_proximity", "label": "MA偏离度%", "type": "float",
         "default": 2.0, "min": 0.5, "max": 5.0, "step": 0.5},
        {"id": "require_ma_alignment", "label": "要求MA5>MA20>MA60", "type": "bool",
         "default": True},
        {"id": "require_positive_change", "label": "要求当日上涨", "type": "bool",
         "default": True},
    ],
    "scoring": {"momentum_60d": 0.4, "change_pct": 0.3, "momentum_20d": 0.3},
    "order_by": "score",
    "descending": True,
    "limit": 50,
}

ENTRY_SIGNALS = ["signal_ma_golden_5_20"]
EXIT_SIGNALS = ["signal_ma20_breakdown", "signal_ma_dead_5_20"]
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 15
ALERTS = []


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    proximity = params.get("ma_proximity", 2.0) / 100.0
    expr = pl.col("symbol").is_not_null() | pl.col("symbol").is_null()
    if params.get("use_ma20_proximity", True):
        expr = (
            expr
            & (pl.col("close") > pl.col("ma20") * (1 - proximity))
            & (pl.col("close") < pl.col("ma20") * (1 + proximity))
        )
    if params.get("require_ma_alignment", True):
        expr = expr & (pl.col("ma5") > pl.col("ma20")) & (pl.col("ma20") > pl.col("ma60"))
    if params.get("require_positive_change", True):
        expr = expr & (pl.col("change_pct") > 0)
    return expr
