"""趋势突破 — MA60上方 + 60日新高 + 放量"""
import polars as pl

META = {
    "id": "trend_breakout",
    "name": "趋势突破",
    "description": "MA60上方 + 60日新高 + 量能 ≥ 2倍均量",
    "tags": ["趋势", "突破", "放量"],
    "basic_filter": {
        "price_min": 5,
        "price_max": 200,
        "market_cap_min": 20e8,
        "amount_min": 1e8,
        "exclude_st": True,
        "exclude_new_days": 60,
    },
    "params": [
        {"id": "require_above_ma60", "label": "要求收盘价在MA60上方", "type": "bool",
         "default": True},
        {"id": "require_n_day_high", "label": "要求60日新高", "type": "bool",
         "default": True},
        {"id": "use_volume_filter", "label": "启用量比过滤", "type": "bool",
         "default": True},
        {"id": "vol_ratio_min", "label": "最低量比", "type": "float",
         "default": 2.0, "min": 0.5, "max": 10.0, "step": 0.1},
    ],
    "scoring": {"momentum_60d": 0.4, "vol_ratio_5d": 0.3, "change_pct": 0.3},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

ENTRY_SIGNALS = ["signal_n_day_high"]
EXIT_SIGNALS = ["signal_ma20_breakdown"]
STOP_LOSS = -0.08
MAX_HOLD_DAYS = 20
ALERTS = [
    {"field": "signal_volume_surge", "message": "放量异动"},
]


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    vol_min = params.get("vol_ratio_min", 2.0)
    expr = pl.col("symbol").is_not_null() | pl.col("symbol").is_null()
    if params.get("require_above_ma60", True):
        expr = expr & (pl.col("close") > pl.col("ma60"))
    if params.get("require_n_day_high", True):
        expr = expr & pl.col("signal_n_day_high").fill_null(False)
    if params.get("use_volume_filter", True):
        expr = expr & (pl.col("vol_ratio_5d") >= vol_min)
    return expr
