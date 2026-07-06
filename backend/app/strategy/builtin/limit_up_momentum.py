"""连板接力 — 近2日涨停且今日涨幅 > 5%, 连板股追踪"""
import polars as pl

META = {
    "id": "limit_up_momentum",
    "name": "连板接力",
    "description": "连板股 + 今日涨幅 > 5%, 连板接力追踪",
    "tags": ["涨停", "连板", "接力"],
    "params": [
        {"id": "use_change_filter", "label": "启用涨幅过滤", "type": "bool",
         "default": True},
        {"id": "min_change", "label": "最低涨幅%", "type": "float",
         "default": 5.0, "min": 2.0, "max": 15.0, "step": 0.5},
        {"id": "use_boards_filter", "label": "启用连板数过滤", "type": "bool",
         "default": True},
        {"id": "min_boards", "label": "最少连板", "type": "int",
         "default": 1, "min": 1, "max": 10, "step": 1},
    ],
    "scoring": {"consecutive_limit_ups": 0.4, "change_pct": 0.3, "amount": 0.3},
    "order_by": "score",
    "descending": True,
    "limit": 50,
}

ENTRY_SIGNALS = ["signal_limit_up"]
EXIT_SIGNALS = []
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 5
ALERTS = []


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    min_chg = params.get("min_change", 5.0) / 100.0
    min_boards = params.get("min_boards", 1)
    expr = pl.col("symbol").is_not_null() | pl.col("symbol").is_null()
    if params.get("use_change_filter", True):
        expr = expr & (pl.col("change_pct") > min_chg)
    if params.get("use_boards_filter", True):
        expr = expr & (pl.col("consecutive_limit_ups") >= min_boards)
    return expr
