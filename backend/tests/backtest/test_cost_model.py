"""成本模型拆分测试 — 佣金(双边) + 印花税(仅卖出) + 滑点(双边)。

覆盖:
1. 向后兼容: 仅传 fees_pct 时, 买卖成本与旧行为完全一致 (无印花税)。
2. 拆分模型: commission_pct / stamp_tax_pct / slippage_bps 各自参与, 印花税只在卖出侧。
3. 优先级: 显式 commission_pct 覆盖 fees_pct。
4. 撮合传导: 印花税只影响卖出腿, 且精度进入 TradeRecord。
"""
from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from app.backtest.engine import BacktestEngine, MatcherConfig

# ---------------------------------------------------------------
# 复用 portfolio 测试的最小面板/掩码构造
# ---------------------------------------------------------------

def _panel(symbols: list[str], days: int = 4, price: float = 10.0, overrides: dict | None = None) -> pl.DataFrame:
    overrides = overrides or {}
    start = date(2024, 1, 1)
    rows = []
    for sym in symbols:
        for i in range(days):
            patch = overrides.get((sym, i), {})
            rows.append({
                "symbol": sym,
                "name": sym,
                "date": start + timedelta(days=i),
                "open": patch.get("open", price),
                "high": patch.get("high", price),
                "low": patch.get("low", price),
                "close": patch.get("close", price),
                "volume": patch.get("volume", 100_000),
                "score": patch.get("score", 1),
                "signal_limit_up": patch.get("signal_limit_up", False),
                "signal_limit_down": patch.get("signal_limit_down", False),
            })
    return pl.DataFrame(rows).sort(["symbol", "date"])


def _mask(panel: pl.DataFrame, marks: set[tuple[str, int]]) -> pl.Series:
    base = date(2024, 1, 1)
    values = []
    for row in panel.select(["symbol", "date"]).iter_rows(named=True):
        day = (row["date"] - base).days
        values.append((row["symbol"], day) in marks)
    return pl.Series(values, dtype=pl.Boolean)


# ---------------------------------------------------------------
# 1. 单元测试: buy_cost_pct / sell_cost_pct
# ---------------------------------------------------------------

def test_legacy_fees_pct_keeps_symmetric_cost_without_stamp():
    """仅传 fees_pct: 买卖成本相等, 均为 fees + slippage, 不含印花税 (旧行为)。"""
    cfg = MatcherConfig(fees_pct=0.0002, slippage_bps=5.0)
    assert cfg.buy_cost_pct() == 0.0002 + 0.0005
    assert cfg.sell_cost_pct() == 0.0002 + 0.0005  # 无印花税, 与买入对称


def test_decomposed_cost_applies_stamp_only_on_sell():
    """拆分模型: 佣金双边, 印花税仅卖出, 滑点双边。"""
    cfg = MatcherConfig(commission_pct=0.0003, stamp_tax_pct=0.001, slippage_bps=5.0)
    assert cfg.buy_cost_pct() == 0.0003 + 0.0005
    assert cfg.sell_cost_pct() == 0.0003 + 0.001 + 0.0005


def test_commission_pct_overrides_fees_pct():
    """同时给 fees_pct 与 commission_pct 时, 以 commission_pct 为准。"""
    cfg = MatcherConfig(fees_pct=0.0002, commission_pct=0.0009, slippage_bps=0)
    assert cfg.buy_cost_pct() == 0.0009
    assert cfg.sell_cost_pct() == 0.0009  # stamp 未设 → 0


# ---------------------------------------------------------------
# 2. 撮合传导: 印花税只影响卖出腿
# ---------------------------------------------------------------

def _round_trip_pnl(cfg_kwargs: dict) -> float:
    """价格恒定的一次买卖来回, 返回唯一成交的 pnl_amount。"""
    panel = _panel(
        ["A"],
        days=3,
        overrides={
            ("A", 1): {"open": 10, "high": 10, "low": 10, "close": 10},
            ("A", 2): {"open": 10, "high": 10, "low": 10, "close": 10},
        },
    )
    entries = _mask(panel, {("A", 0)})
    exits = _mask(panel, set())
    result = BacktestEngine(repo=None).simulate_portfolio(
        panel,
        entries,
        exits,
        MatcherConfig(
            matching="open_t+1",
            max_positions=1,
            max_hold_days=1,
            initial_capital=100_000,
            **cfg_kwargs,
        ),
    )
    assert len(result.trades) == 1
    return result.trades[0].pnl_amount


def test_stamp_tax_only_deducts_on_sell_leg():
    """价格不变时, 加印花税后的亏损增量应恰等于 卖出市值 乘以 印花税率。

    买入腿成本不含印花税 → 两次运行的持仓股数相同, 差额只来自卖出腿。
    """
    base = dict(commission_pct=0.0003, stamp_tax_pct=0.0, slippage_bps=0)
    with_stamp = dict(commission_pct=0.0003, stamp_tax_pct=0.001, slippage_bps=0)

    pnl_no_stamp = _round_trip_pnl(base)
    pnl_with_stamp = _round_trip_pnl(with_stamp)

    # 卖出市值 = shares * 10 * (1 - commission)。股数由买入腿决定, 两次一致。
    # 差额 = -shares * 10 * stamp。用 no_stamp 的 exit_value 反推 shares 不必要,
    # 直接断言: 加印花税更亏, 且差额为正的印花税扣减。
    delta = pnl_no_stamp - pnl_with_stamp
    assert delta > 0
    # 差额应约等于 卖出市值 * 印花税率; 卖出市值≈ 无印花税时的 |exit 成本| 基准
    # 用 shares=9900 (floor(100000/(10*1.0003)/100)*100) 精确校验
    shares = 9900
    assert abs(delta - shares * 10 * 0.001) < 1e-6


def test_independent_candidate_pnl_pct_includes_decomposed_costs():
    """独立候选模式 (close_t): 价格不变时 pnl_pct == -(buy_cost + sell_cost)。"""
    panel = _panel(
        ["A"],
        days=3,
        overrides={("A", 0): {"close": 10}, ("A", 1): {"close": 10}},
    )
    entries = _mask(panel, {("A", 0)})
    exits = _mask(panel, set())
    result = BacktestEngine(repo=None).simulate_independent_candidates(
        panel,
        entries,
        exits,
        MatcherConfig(matching="close_t", commission_pct=0.0003, stamp_tax_pct=0.001, slippage_bps=0, max_hold_days=1),
    )
    assert len(result.trades) == 1
    # buy_cost=0.0003, sell_cost=0.0003+0.001=0.0013 → 合计 -0.0016
    assert abs(result.trades[0].pnl_pct - (-(0.0003 + 0.0013))) < 1e-9
