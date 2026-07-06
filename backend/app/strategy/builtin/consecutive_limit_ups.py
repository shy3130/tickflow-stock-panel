"""连板股 — 涨停且连续涨停≥2天"""
import polars as pl

META = {
    "id": "consecutive_limit_ups",
    "name": "连板股",
    "description": "当日涨停且连续涨停≥2天, 强势追涨",
    "tags": ["涨停", "连板"],
    "params": [
        {"id": "require_limit_up", "label": "要求当日涨停", "type": "bool",
         "default": True},
        {"id": "use_boards_filter", "label": "启用连板数过滤", "type": "bool",
         "default": True},
        {"id": "min_boards", "label": "最少连板数", "type": "int",
         "default": 2, "min": 1, "max": 20, "step": 1},
    ],
    "scoring": {"consecutive_limit_ups": 0.5, "change_pct": 0.3, "amount": 0.2},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

ENTRY_SIGNALS = ["signal_limit_up"]
EXIT_SIGNALS = []
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 5
ALERTS = []


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    min_boards = params.get("min_boards", 2)
    expr = pl.col("symbol").is_not_null() | pl.col("symbol").is_null()
    if params.get("require_limit_up", True):
        expr = expr & pl.col("signal_limit_up").fill_null(False)
    if params.get("use_boards_filter", True):
        expr = expr & (pl.col("consecutive_limit_ups") >= min_boards)
    return expr
