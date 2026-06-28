"""Quant-screener migrated nine-turn reversal proxy."""
import polars as pl

META = {
    "id": "quant_nineturn_profile",
    "name": "Quant Nine-Turn Proxy",
    "description": "Migrated from quant-screener NineturnStrategy as a TickFlow proxy: oversold/new-low reversal back above MA20.",
    "tags": ["quant", "reversal", "nineturn", "migration"],
    "basic_filter": {
        "price_min": 2,
        "price_max": 150,
        "market_cap_min": 10e8,
        "amount_min": 0.3e8,
        "exclude_st": True,
        "exclude_new_days": 120,
    },
    "params": [
        {"id": "max_rsi", "label": "Max RSI14", "type": "float", "default": 42.0, "min": 10.0, "max": 70.0, "step": 1.0},
        {"id": "min_rebound", "label": "Min daily rebound", "type": "float", "default": 0.0, "min": -0.10, "max": 0.10, "step": 0.005},
    ],
    "scoring": {"rsi_14": 0.30, "change_pct": 0.25, "momentum_20d": 0.20, "vol_ratio_5d": 0.15, "turnover_rate": 0.10},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

ENTRY_SIGNALS = ["signal_n_day_low", "signal_ma20_breakout"]
EXIT_SIGNALS = ["signal_ma20_breakdown"]
STOP_LOSS = -0.07
MAX_HOLD_DAYS = 15


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    max_rsi = float(params.get("max_rsi", 42.0))
    min_rebound = float(params.get("min_rebound", 0.0))
    oversold_reversal = (
        (pl.col("rsi_14").fill_null(100.0) <= max_rsi)
        | pl.col("signal_n_day_low").fill_null(False)
    )
    return (
        oversold_reversal
        & (pl.col("change_pct").fill_null(-1.0) >= min_rebound)
        & (pl.col("close") >= pl.col("ma20") * 0.96)
        & (pl.col("momentum_20d").fill_null(0.0) <= 0.06)
        & (pl.col("vol_ratio_5d").fill_null(0.0) >= 0.8)
    )
