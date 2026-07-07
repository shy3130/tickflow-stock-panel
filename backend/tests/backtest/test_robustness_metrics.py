"""稳健性指标测试 — Sortino + 蒙特卡罗回撤分位 + per-trade 明细。

被测新增:
- BacktestEngine._sortino_ratio(returns, periods_per_year): 下行波动调整收益比
- BacktestEngine._mc_drawdown_percentiles(pnls, n_sims): 自助重抽样估计最大回撤分布
- _calc_stats / _calc_portfolio_stats 输出新增 sortino / mc_maxdd_p50 / mc_maxdd_p95 /
  median_pnl / best / worst / avg_holding_days 字段
"""
from __future__ import annotations

from datetime import date

import numpy as np

from app.backtest.engine import BacktestEngine, TradeRecord

# ---------------------------------------------------------------
# Sortino
# ---------------------------------------------------------------

def test_sortino_all_losses_is_exact():
    """全亏损序列: mean/downside_dev * sqrt(252) 可手算校验。"""
    r = np.array([-0.1, -0.1])
    # mean=-0.1; neg=[-0.1,-0.1]; downside_dev=sqrt(mean(0.01,0.01))=0.1
    # sortino = -0.1/0.1 * sqrt(252) = -sqrt(252)
    got = BacktestEngine._sortino_ratio(r)
    assert abs(got - (-np.sqrt(252))) < 1e-6


def test_sortino_no_downside_returns_none():
    """无负收益 → 下行波动为 0, Sortino 未定义, 约定返回 None (不虚报 inf/0)。"""
    r = np.array([0.05, 0.10, 0.02])
    assert BacktestEngine._sortino_ratio(r) is None


def test_sortino_exceeds_sharpe_when_downside_is_tamer():
    """下行波动小于总波动时, Sortino 应高于 Sharpe (只惩罚下行的优势)。"""
    # 大涨小跌: 上行贡献总波动但不进下行 → sortino > sharpe
    r = np.array([0.20, -0.02, 0.20, -0.02])
    mean = float(np.mean(r))
    sharpe = mean / float(np.std(r)) * np.sqrt(252)
    sortino = BacktestEngine._sortino_ratio(r)
    assert sortino is not None
    assert sortino > sharpe


def test_sortino_too_few_points():
    assert BacktestEngine._sortino_ratio(np.array([0.1])) == 0.0
    assert BacktestEngine._sortino_ratio(np.array([])) == 0.0


# ---------------------------------------------------------------
# 蒙特卡罗最大回撤分位
# ---------------------------------------------------------------

def test_mc_drawdown_is_deterministic():
    """固定种子 → 两次调用结果完全一致 (可复现, 可测)。"""
    pnls = np.array([0.05, -0.03, 0.08, -0.06, 0.02, -0.04, 0.10, -0.05])
    a = BacktestEngine._mc_drawdown_percentiles(pnls)
    b = BacktestEngine._mc_drawdown_percentiles(pnls)
    assert a == b
    assert a["mc_maxdd_p50"] is not None


def test_mc_drawdown_p95_is_worse_than_p50():
    """P95(最坏 5% 场景)的回撤应不轻于中位数 P50 (更负或相等)。"""
    pnls = np.array([0.05, -0.03, 0.08, -0.06, 0.02, -0.04, 0.10, -0.05])
    r = BacktestEngine._mc_drawdown_percentiles(pnls)
    assert r["mc_maxdd_p95"] <= r["mc_maxdd_p50"] <= 0.0


def test_mc_drawdown_all_positive_has_zero_drawdown():
    """全正收益: 任何重排都无回撤 → 分位均为 0。"""
    pnls = np.array([0.01, 0.02, 0.03, 0.04, 0.05])
    r = BacktestEngine._mc_drawdown_percentiles(pnls)
    assert r["mc_maxdd_p50"] == 0.0
    assert r["mc_maxdd_p95"] == 0.0


def test_mc_drawdown_too_few_trades():
    r = BacktestEngine._mc_drawdown_percentiles(np.array([0.1, -0.1]))
    assert r["mc_maxdd_p50"] is None
    assert r["mc_maxdd_p95"] is None


# ---------------------------------------------------------------
# 集成: stats 输出新字段
# ---------------------------------------------------------------

def _trades(pnls: list[float], durations: list[int]) -> list[TradeRecord]:
    out = []
    for p, d in zip(pnls, durations, strict=True):
        out.append(TradeRecord(
            symbol="A", entry_date=date(2024, 1, 1), exit_date=date(2024, 1, 1 + d),
            entry_price=10.0, exit_price=10.0 * (1 + p), pnl_pct=p, duration=d,
            exit_reason="signal",
        ))
    return out


def test_calc_stats_emits_robustness_fields():
    trades = _trades([0.10, -0.05, 0.08, -0.06], [3, 2, 5, 4])
    stats = BacktestEngine._calc_stats(trades, 100_000, date(2024, 1, 1), date(2024, 6, 1))
    for k in ("sortino", "mc_maxdd_p50", "mc_maxdd_p95", "median_pnl", "best", "worst", "avg_holding_days"):
        assert k in stats, f"缺字段 {k}"
    assert stats["best"] == round(0.10, 4)
    assert stats["worst"] == round(-0.06, 4)
    assert stats["median_pnl"] == round(float(np.median([0.10, -0.05, 0.08, -0.06])), 4)
    assert stats["avg_holding_days"] == round(float(np.mean([3, 2, 5, 4])), 1)


def test_calc_stats_empty_trades_safe():
    """空交易不应因新字段计算崩溃。"""
    stats = BacktestEngine._calc_stats([], 100_000, date(2024, 1, 1), date(2024, 6, 1))
    assert stats["n_trades"] == 0


def test_portfolio_stats_emits_robustness_fields():
    """portfolio 分支同样输出 sortino / mc / per-trade 字段。"""
    equity_curve = [
        {"date": "2024-01-01", "value": 100_000.0, "exposure": 0.0},
        {"date": "2024-01-02", "value": 103_000.0, "exposure": 0.5},
        {"date": "2024-01-03", "value": 101_000.0, "exposure": 0.5},
        {"date": "2024-01-04", "value": 105_000.0, "exposure": 0.5},
    ]
    trades = _trades([0.06, -0.02, 0.04], [2, 1, 3])
    stats = BacktestEngine._calc_portfolio_stats(equity_curve, trades, 100_000)
    for k in ("sortino", "mc_maxdd_p50", "mc_maxdd_p95", "median_pnl", "best", "worst", "avg_holding_days"):
        assert k in stats, f"缺字段 {k}"
