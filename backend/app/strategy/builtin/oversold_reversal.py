"""超跌反弹 — RSI14 < 30 + 涨幅 > 1% + 站上 MA5, 超卖反弹信号"""
import polars as pl

META = {
    "id": "oversold_reversal",
    "name": "超跌反转",
    "description": "RSI14 < 30超卖 + 涨幅 > 1% + 站上MA5, 超卖反转信号",
    "tags": ["超跌", "反弹", "RSI"],
    "params": [
        {"id": "use_rsi_filter", "label": "启用RSI过滤", "type": "bool",
         "default": True},
        {"id": "rsi_max", "label": "RSI上限", "type": "float",
         "default": 30.0, "min": 10.0, "max": 50.0, "step": 1.0},
        {"id": "use_change_filter", "label": "启用涨幅过滤", "type": "bool",
         "default": True},
        {"id": "min_change", "label": "最低涨幅%", "type": "float",
         "default": 1.0, "min": 0.5, "max": 5.0, "step": 0.5},
        {"id": "require_above_ma5", "label": "要求收盘价在MA5上方", "type": "bool",
         "default": True},
    ],
    "scoring": {"change_pct": 0.4, "rsi_14": 0.3, "vol_ratio_5d": 0.3},
    "order_by": "score",
    "descending": True,
    "limit": 50,
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
    min_chg = params.get("min_change", 1.0) / 100.0
    expr = pl.col("symbol").is_not_null() | pl.col("symbol").is_null()
    if params.get("use_rsi_filter", True):
        expr = expr & (pl.col("rsi_14") < rsi_max)
    if params.get("use_change_filter", True):
        expr = expr & (pl.col("change_pct") > min_chg)
    if params.get("require_above_ma5", True):
        expr = expr & (pl.col("close") > pl.col("ma5"))
    return expr
