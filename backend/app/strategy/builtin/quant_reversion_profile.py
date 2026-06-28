"""Quant-screener migrated pullback/reversion profile."""
import polars as pl

META = {
    "id": "quant_reversion_profile",
    "name": "Quant Reversion Profile",
    "description": "Migrated from quant-screener ReversionStrategy: pullbacks within an intact trend, avoiding over-extension.",
    "tags": ["quant", "reversion", "pullback", "migration"],
    "basic_filter": {
        "price_min": 2,
        "price_max": 180,
        "market_cap_min": 20e8,
        "amount_min": 0.8e8,
        "exclude_st": True,
        "exclude_new_days": 120,
    },
    "params": [
        {"id": "min_pullback", "label": "Min pullback from 60D high", "type": "float", "default": 0.05, "min": 0.0, "max": 0.30, "step": 0.01},
        {"id": "max_pullback", "label": "Max pullback from 60D high", "type": "float", "default": 0.20, "min": 0.05, "max": 0.50, "step": 0.01},
        {"id": "max_extension", "label": "Max MA20 extension", "type": "float", "default": 0.06, "min": 0.0, "max": 0.30, "step": 0.01},
    ],
    "scoring": {"momentum_60d": 0.25, "momentum_20d": 0.20, "rsi_14": 0.20, "turnover_rate": 0.15, "change_pct": 0.20},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

ENTRY_SIGNALS = ["signal_ma20_breakout", "signal_macd_golden"]
EXIT_SIGNALS = ["signal_ma20_breakdown"]
STOP_LOSS = -0.07
TRAILING_STOP = -0.06
MAX_HOLD_DAYS = 20


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    min_pullback = float(params.get("min_pullback", 0.05))
    max_pullback = float(params.get("max_pullback", 0.20))
    max_extension = float(params.get("max_extension", 0.06))
    pullback = (pl.col("high_60d") - pl.col("close")) / pl.col("high_60d")
    extension = pl.col("close") / pl.col("ma20") - 1.0
    return (
        (pl.col("close") >= pl.col("ma20") * 0.98)
        & (pl.col("ma20") >= pl.col("ma60") * 0.98)
        & pullback.is_between(min_pullback, max_pullback)
        & (extension <= max_extension)
        & (pl.col("momentum_20d").fill_null(0.0) <= 0.08)
        & (pl.col("vol_ratio_5d").fill_null(0.0).is_between(0.75, 1.8))
    )
