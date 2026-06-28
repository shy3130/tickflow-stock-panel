"""Quant-screener migrated quality/value profile."""
import polars as pl

META = {
    "id": "quant_quality_profile",
    "name": "Quant Quality Profile",
    "description": "Migrated from quant-screener QualityGrowthStrategy using TickFlow-available valuation, trend and stability proxies.",
    "tags": ["quant", "quality", "value", "migration"],
    "basic_filter": {
        "price_min": 2,
        "price_max": 150,
        "market_cap_min": 20e8,
        "amount_min": 0.5e8,
        "exclude_st": True,
        "exclude_new_days": 180,
    },
    "params": [
        {"id": "max_pe_ttm", "label": "Max PE TTM", "type": "float", "default": 45.0, "min": 1.0, "max": 200.0, "step": 1.0},
        {"id": "max_pb", "label": "Max PB", "type": "float", "default": 4.0, "min": 0.2, "max": 20.0, "step": 0.1},
        {"id": "max_vol", "label": "Max annual vol", "type": "float", "default": 0.65, "min": 0.05, "max": 2.0, "step": 0.05},
    ],
    "scoring": {"momentum_60d": 0.25, "momentum_20d": 0.20, "turnover_rate": 0.15, "change_pct": 0.10},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

ENTRY_SIGNALS = ["signal_ma20_breakout", "signal_macd_golden"]
EXIT_SIGNALS = ["signal_ma20_breakdown"]
STOP_LOSS = -0.07
MAX_HOLD_DAYS = 25


def _optional_between(df: pl.DataFrame, col: str, low: float, high: float) -> pl.Expr:
    if col not in df.columns:
        return pl.lit(True)
    return pl.when(pl.col(col).is_not_null()).then(pl.col(col).is_between(low, high)).otherwise(True)


def _optional_le(df: pl.DataFrame, col: str, value: float) -> pl.Expr:
    if col not in df.columns:
        return pl.lit(True)
    return pl.when(pl.col(col).is_not_null()).then(pl.col(col) <= value).otherwise(True)


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    max_pe = float(params.get("max_pe_ttm", 45.0))
    max_pb = float(params.get("max_pb", 4.0))
    max_vol = float(params.get("max_vol", 0.65))
    return (
        (pl.col("close") >= pl.col("ma60") * 0.98)
        & (pl.col("momentum_20d").fill_null(-1.0) >= -0.08)
        & (pl.col("annual_vol_20d").fill_null(0.0) <= max_vol)
        & _optional_between(df, "pe_ttm", 0.0, max_pe)
        & _optional_between(df, "pb", 0.0, max_pb)
        & _optional_le(df, "turnover_rate", 8.0)
    )
