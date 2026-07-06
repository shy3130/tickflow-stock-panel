"""超跌反弹 — RSI14 < 30 + 收阳 + 放量"""
import polars as pl

META = {
    "id": "oversold_bounce",
    "name": "超跌反弹",
    "description": "RSI14 < 30超卖区 + 当日收阳 + 放量, 抄底信号",
    "tags": ["超跌", "反弹", "RSI"],
    "params": [
        {"id": "use_rsi_filter", "label": "启用RSI过滤", "type": "bool",
         "default": True},
        {"id": "rsi_max", "label": "RSI上限", "type": "float",
         "default": 30.0, "min": 10.0, "max": 50.0, "step": 1.0},
        {"id": "require_bullish_candle", "label": "要求收阳", "type": "bool",
         "default": True},
        {"id": "use_volume_filter", "label": "启用量比过滤", "type": "bool",
         "default": True},
        {"id": "vol_ratio_min", "label": "最低量比", "type": "float",
         "default": 1.2, "min": 0.5, "max": 5.0, "step": 0.1},
    ],
    "scoring": {"change_pct": 0.3, "vol_ratio_5d": 0.3, "momentum_5d": 0.2, "rsi_14": 0.2},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

ENTRY_SIGNALS = []
EXIT_SIGNALS = ["signal_ma20_breakdown"]
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 15
ALERTS = [
    {"field": "rsi_14", "op": "<", "value": 25, "message": "RSI极度超卖"},
]


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    rsi_max = params.get("rsi_max", 30.0)
    vol_min = params.get("vol_ratio_min", 1.2)
    expr = pl.col("symbol").is_not_null() | pl.col("symbol").is_null()
    if params.get("use_rsi_filter", True):
        expr = expr & (pl.col("rsi_14") < rsi_max)
    if params.get("require_bullish_candle", True):
        expr = expr & (pl.col("close") > pl.col("open"))
    if params.get("use_volume_filter", True):
        expr = expr & (pl.col("vol_ratio_5d") >= vol_min)
    return expr
