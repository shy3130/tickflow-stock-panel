"""Quant migrated: momentum/liquidity profile."""
import polars as pl

META = {
    "id": "quant_momentum_liquidity",
    "name": "Quant Momentum Liquidity",
    "description": "Migrated from quant-screener: liquid leaders with positive trend and controlled volatility.",
    "tags": ["quant", "momentum", "liquidity"],
    "basic_filter": {
        "price_min": 2,
        "price_max": 180,
        "market_cap_min": 30e8,
        "amount_min": 1.0e8,
        "exclude_st": True,
        "exclude_new_days": 120,
    },
    "params": [
        {"id": "min_momentum_20d", "label": "Min 20D momentum", "type": "float", "default": 0.02, "min": -0.2, "max": 0.5, "step": 0.01},
        {"id": "min_volume_ratio", "label": "Min volume ratio", "type": "float", "default": 0.8, "min": 0.2, "max": 5.0, "step": 0.1},
        {"id": "max_vol", "label": "Max annual vol", "type": "float", "default": 0.85, "min": 0.1, "max": 3.0, "step": 0.05},
    ],
    "scoring": {
        "momentum_20d": 0.30,
        "momentum_60d": 0.30,
        "vol_ratio_5d": 0.20,
        "change_pct": 0.10,
        "turnover_rate": 0.10,
    },
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

ENTRY_SIGNALS = ["signal_n_day_high", "signal_ma20_breakout", "signal_volume_surge"]
EXIT_SIGNALS = ["signal_ma20_breakdown", "signal_macd_dead"]
STOP_LOSS = -0.08
TRAILING_STOP = -0.06
MAX_HOLD_DAYS = 20
ALERTS = [{"field": "signal_volume_surge", "message": "Volume expansion"}]


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    min_momentum_20d = float(params.get("min_momentum_20d", 0.02))
    min_volume_ratio = float(params.get("min_volume_ratio", 0.8))
    max_vol = float(params.get("max_vol", 0.85))
    return (
        (pl.col("close") > pl.col("ma20"))
        & (pl.col("ma20") > pl.col("ma60"))
        & (pl.col("momentum_20d").fill_null(0.0) >= min_momentum_20d)
        & (pl.col("vol_ratio_5d").fill_null(0.0) >= min_volume_ratio)
        & (pl.col("annual_vol_20d").fill_null(0.0) <= max_vol)
        & (pl.col("turnover_rate").fill_null(1.0) >= 0.2)
    )
