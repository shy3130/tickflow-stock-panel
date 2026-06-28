"""Quant-screener migrated trend profile."""
import polars as pl

META = {
    "id": "quant_trend_profile",
    "name": "Quant Trend Profile",
    "description": "Migrated from quant-screener TrendStrategy: multi-MA trend, near 60D high, momentum and volume confirmation.",
    "tags": ["quant", "trend", "migration"],
    "basic_filter": {
        "price_min": 2,
        "price_max": 200,
        "market_cap_min": 20e8,
        "amount_min": 1.0e8,
        "exclude_st": True,
        "exclude_new_days": 120,
    },
    "params": [
        {"id": "min_momentum_20d", "label": "Min 20D momentum", "type": "float", "default": 0.04, "min": -0.2, "max": 0.5, "step": 0.01},
        {"id": "near_high_ratio", "label": "Near 60D high ratio", "type": "float", "default": 0.985, "min": 0.90, "max": 1.0, "step": 0.005},
        {"id": "min_volume_ratio", "label": "Min volume ratio", "type": "float", "default": 1.2, "min": 0.2, "max": 5.0, "step": 0.1},
    ],
    "scoring": {"momentum_60d": 0.35, "momentum_20d": 0.30, "vol_ratio_5d": 0.20, "change_pct": 0.15},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

ENTRY_SIGNALS = ["signal_n_day_high", "signal_ma20_breakout"]
EXIT_SIGNALS = ["signal_ma20_breakdown", "signal_macd_dead"]
STOP_LOSS = -0.08
TRAILING_STOP = -0.06
MAX_HOLD_DAYS = 20


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    min_momentum = float(params.get("min_momentum_20d", 0.04))
    near_high_ratio = float(params.get("near_high_ratio", 0.985))
    min_volume_ratio = float(params.get("min_volume_ratio", 1.2))
    long_ma_ok = (
        (pl.col("close") > pl.col("ma20"))
        & (pl.col("ma20") > pl.col("ma60"))
    )
    return (
        long_ma_ok
        & (pl.col("close") >= pl.col("high_60d") * near_high_ratio)
        & (pl.col("momentum_20d").fill_null(0.0) >= min_momentum)
        & (pl.col("vol_ratio_5d").fill_null(0.0) >= min_volume_ratio)
    )
