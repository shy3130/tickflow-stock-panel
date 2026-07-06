"""均线多头 — MA5>MA10>MA20>MA60 + 短期动量为正"""
import polars as pl

META = {
    "id": "bullish_alignment",
    "name": "均线多头",
    "description": "MA5>MA10>MA20>MA60多头排列 + 短期动量为正",
    "tags": ["均线", "多头"],
    "params": [
        {"id": "require_ma_alignment", "label": "要求均线多头排列", "type": "bool",
         "default": True},
        {"id": "require_positive_momentum", "label": "要求20日动量为正", "type": "bool",
         "default": True},
    ],
    "scoring": {"momentum_60d": 0.4, "momentum_20d": 0.3, "turnover_rate": 0.3},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

ENTRY_SIGNALS = ["signal_ma_golden_5_20", "signal_ma_golden_20_60"]
EXIT_SIGNALS = ["signal_ma_dead_5_20", "signal_ma20_breakdown"]
STOP_LOSS = -0.06
MAX_HOLD_DAYS = 20
ALERTS = []


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    expr = pl.col("symbol").is_not_null() | pl.col("symbol").is_null()
    if params.get("require_ma_alignment", True):
        expr = (
            expr
            & (pl.col("ma5") > pl.col("ma10"))
            & (pl.col("ma10") > pl.col("ma20"))
            & (pl.col("ma20") > pl.col("ma60"))
        )
    if params.get("require_positive_momentum", True):
        expr = expr & (pl.col("momentum_20d") > 0)
    return expr
