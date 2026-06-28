"""Quant-screener migrated liquidity profile."""
import polars as pl

META = {
    "id": "quant_liquidity_profile",
    "name": "Quant Liquidity Profile",
    "description": "Migrated from quant-screener LiquidityStrategy: ample turnover value, healthy turnover and stable volume ratio.",
    "tags": ["quant", "liquidity", "migration"],
    "basic_filter": {
        "price_min": 2,
        "price_max": 200,
        "market_cap_min": 30e8,
        "amount_min": 2.0e8,
        "turnover_min": 0.3,
        "turnover_max": 6.0,
        "exclude_st": True,
        "exclude_new_days": 120,
    },
    "params": [
        {"id": "min_amount", "label": "Min amount", "type": "float", "default": 2.0e8, "min": 0.1e8, "max": 30e8, "step": 0.1e8},
        {"id": "max_volume_ratio", "label": "Max volume ratio", "type": "float", "default": 1.8, "min": 0.5, "max": 6.0, "step": 0.1},
    ],
    "scoring": {"amount": 0.35, "turnover_rate": 0.25, "vol_ratio_5d": 0.20, "momentum_20d": 0.20},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

ENTRY_SIGNALS = ["signal_ma20_breakout"]
EXIT_SIGNALS = ["signal_ma20_breakdown"]
STOP_LOSS = -0.07
MAX_HOLD_DAYS = 25


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    min_amount = float(params.get("min_amount", 2.0e8))
    max_volume_ratio = float(params.get("max_volume_ratio", 1.8))
    return (
        (pl.col("amount").fill_null(0.0) >= min_amount)
        & (pl.col("turnover_rate").fill_null(0.0).is_between(0.3, 6.0))
        & (pl.col("vol_ratio_5d").fill_null(0.0).is_between(0.9, max_volume_ratio))
        & (pl.col("momentum_20d").fill_null(-1.0) > -0.08)
    )
