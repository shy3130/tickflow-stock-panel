"""Quant migrated: quality/value defensive profile."""
import polars as pl

META = {
    "id": "quant_quality_value_defense",
    "name": "Quant Quality Value Defense",
    "description": "Migrated from quant-screener: liquid, low-volatility, value-aware defensive candidates.",
    "tags": ["quant", "quality", "value", "defense"],
    "basic_filter": {
        "price_min": 2,
        "price_max": 120,
        "market_cap_min": 20e8,
        "amount_min": 0.5e8,
        "exclude_st": True,
        "exclude_new_days": 180,
    },
    "params": [
        {"id": "max_pb", "label": "Max PB", "type": "float", "default": 3.5, "min": 0.2, "max": 20.0, "step": 0.1},
        {"id": "max_pe_ttm", "label": "Max PE TTM", "type": "float", "default": 45.0, "min": 1.0, "max": 200.0, "step": 1.0},
        {"id": "max_vol", "label": "Max annual vol", "type": "float", "default": 0.55, "min": 0.05, "max": 2.0, "step": 0.05},
        {"id": "min_momentum_20d", "label": "Min 20D momentum", "type": "float", "default": -0.08, "min": -0.5, "max": 0.5, "step": 0.01},
    ],
    "scoring": {
        "momentum_20d": 0.20,
        "momentum_60d": 0.20,
        "vol_ratio_5d": 0.10,
        "turnover_rate": 0.10,
        "change_pct": 0.10,
    },
    "order_by": "score",
    "descending": True,
    "limit": 80,
}

ENTRY_SIGNALS = ["signal_ma20_breakout", "signal_macd_golden"]
EXIT_SIGNALS = ["signal_ma20_breakdown"]
STOP_LOSS = -0.07
MAX_HOLD_DAYS = 25


def _optional_le(col: str, value: float) -> pl.Expr:
    if value is None:
        return pl.lit(True)
    return pl.when(pl.col(col).is_not_null()).then(pl.col(col) <= value).otherwise(True)


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    max_pb = float(params.get("max_pb", 3.5))
    max_pe_ttm = float(params.get("max_pe_ttm", 45.0))
    max_vol = float(params.get("max_vol", 0.55))
    min_momentum_20d = float(params.get("min_momentum_20d", -0.08))

    expr = (
        (pl.col("close") > pl.col("ma60"))
        & (pl.col("close") >= pl.col("ma20") * 0.96)
        & (pl.col("momentum_20d").fill_null(0.0) >= min_momentum_20d)
        & (pl.col("annual_vol_20d").fill_null(0.0) <= max_vol)
        & (pl.col("turnover_rate").fill_null(0.0) <= 8.0)
    )
    if "pb" in df.columns:
        expr = expr & _optional_le("pb", max_pb)
    if "pe_ttm" in df.columns:
        expr = expr & _optional_le("pe_ttm", max_pe_ttm)
    return expr
