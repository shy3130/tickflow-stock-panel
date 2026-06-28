"""Quant-screener migrated relative-strength profile."""
import polars as pl

META = {
    "id": "quant_relative_strength_profile",
    "name": "Quant Relative Strength Profile",
    "description": "Migrated from quant-screener RelativeStrengthStrategy: market-leading 20D/60D momentum candidates.",
    "tags": ["quant", "relative-strength", "migration"],
    "basic_filter": {
        "price_min": 2,
        "price_max": 180,
        "market_cap_min": 20e8,
        "amount_min": 1.0e8,
        "exclude_st": True,
        "exclude_new_days": 120,
    },
    "params": [
        {"id": "top_pct", "label": "Momentum percentile", "type": "float", "default": 0.85, "min": 0.50, "max": 0.98, "step": 0.01},
        {"id": "min_momentum_20d", "label": "Min 20D momentum", "type": "float", "default": 0.02, "min": -0.2, "max": 0.5, "step": 0.01},
    ],
    "scoring": {"momentum_60d": 0.45, "momentum_20d": 0.35, "vol_ratio_5d": 0.10, "change_pct": 0.10},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

ENTRY_SIGNALS = ["signal_n_day_high", "signal_ma20_breakout"]
EXIT_SIGNALS = ["signal_ma20_breakdown"]
STOP_LOSS = -0.08
MAX_HOLD_DAYS = 20


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    top_pct = float(params.get("top_pct", 0.85))
    min_momentum = float(params.get("min_momentum_20d", 0.02))
    try:
        threshold = (
            df.select(pl.col("momentum_60d").drop_nulls().quantile(top_pct, interpolation="nearest"))
            .item()
        )
    except Exception:
        threshold = 0.0
    threshold = float(threshold or 0.0)
    return (
        (pl.col("momentum_60d").fill_null(-1.0) >= threshold)
        & (pl.col("momentum_20d").fill_null(0.0) >= min_momentum)
        & (pl.col("close") > pl.col("ma20"))
        & (pl.col("ma20") >= pl.col("ma60") * 0.98)
    )
