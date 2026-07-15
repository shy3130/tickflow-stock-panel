"""月线聚合年线 + period access flags."""
from __future__ import annotations

from datetime import date

import polars as pl

from app.plugins.stocksdk.provider import _aggregate_monthly_to_yearly
from app.services.period_kline_access import monthly_access_flags, yearly_access_flags


def test_aggregate_monthly_to_yearly_ohlcv():
    df = pl.DataFrame(
        {
            "symbol": ["600519.SH"] * 4,
            "date": [
                date(2024, 1, 31),
                date(2024, 6, 30),
                date(2024, 12, 31),
                date(2025, 3, 31),
            ],
            "open": [100.0, 110.0, 120.0, 130.0],
            "high": [105.0, 115.0, 125.0, 135.0],
            "low": [95.0, 105.0, 115.0, 125.0],
            "close": [102.0, 112.0, 122.0, 132.0],
            "volume": [10.0, 20.0, 30.0, 40.0],
            "amount": [1.0, 2.0, 3.0, 4.0],
        }
    )
    out = _aggregate_monthly_to_yearly(df)
    assert out.height == 2
    y2024 = out.filter(pl.col("date").dt.year() == 2024).row(0, named=True)
    assert y2024["open"] == 100.0
    assert y2024["high"] == 125.0
    assert y2024["low"] == 95.0
    assert y2024["close"] == 122.0
    assert y2024["volume"] == 60.0
    assert y2024["amount"] == 6.0
    assert y2024["date"].isoformat() == "2024-12-31"


def test_aggregate_empty():
    empty = pl.DataFrame({"symbol": [], "date": [], "open": [], "close": []})
    assert _aggregate_monthly_to_yearly(empty).is_empty()


def test_monthly_yearly_access_flags_structure(monkeypatch):
    monkeypatch.setattr(
        "app.services.period_kline_access.period_provider_active",
        lambda dataset: dataset in ("monthly", "yearly"),
    )
    monkeypatch.setattr(
        "app.services.preferences.get_monthly_data_provider",
        lambda: "stocksdk",
    )
    monkeypatch.setattr(
        "app.services.preferences.get_yearly_data_provider",
        lambda: "stocksdk",
    )
    m = monthly_access_flags(None)
    assert m["monthly_access"] is True
    assert m["monthly_provider"] == "stocksdk"
    assert m["monthly_provider_active"] is True
    y = yearly_access_flags(None)
    assert y["yearly_access"] is True
    assert y["yearly_provider"] == "stocksdk"
