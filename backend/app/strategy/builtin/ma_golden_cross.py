"""MA金叉 — MA5上穿MA20 + 量能配合 + MA60上方"""
import polars as pl

META = {
    "id": "ma_golden_cross",
    "name": "MA 金叉",
    "description": "MA5上穿MA20当日触发, 量能配合",
    "tags": ["均线", "金叉"],
    "params": [
        {"id": "require_ma_golden", "label": "要求MA5上穿MA20", "type": "bool",
         "default": True},
        {"id": "use_volume_filter", "label": "启用量比过滤", "type": "bool",
         "default": True},
        {"id": "vol_ratio_min", "label": "最低量比", "type": "float",
         "default": 1.2, "min": 0.5, "max": 5.0, "step": 0.1},
        {"id": "require_above_ma60", "label": "要求收盘价在MA60上方", "type": "bool",
         "default": True},
    ],
    "scoring": {"momentum_20d": 0.5, "vol_ratio_5d": 0.3, "change_pct": 0.2},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

ENTRY_SIGNALS = ["signal_ma_golden_5_20"]
EXIT_SIGNALS = ["signal_ma_dead_5_20"]
STOP_LOSS = -0.06
MAX_HOLD_DAYS = 15
ALERTS = []


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    vol_min = params.get("vol_ratio_min", 1.2)
    expr = pl.col("symbol").is_not_null() | pl.col("symbol").is_null()
    if params.get("require_ma_golden", True):
        expr = expr & pl.col("signal_ma_golden_5_20").fill_null(False)
    if params.get("use_volume_filter", True):
        expr = expr & (pl.col("vol_ratio_5d") >= vol_min)
    if params.get("require_above_ma60", True):
        expr = expr & (pl.col("close") > pl.col("ma60"))
    return expr
