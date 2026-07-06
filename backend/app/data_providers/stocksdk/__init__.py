"""stock-sdk 内置数据源(免费行情, tickflow 的平替)。"""
from app.data_providers.stocksdk.bridge import StockSDKBridgeError, availability, run_job
from app.data_providers.stocksdk.provider import StockSDKProvider

PROVIDER_NAME = "stocksdk"

__all__ = [
    "PROVIDER_NAME",
    "StockSDKBridgeError",
    "StockSDKProvider",
    "availability",
    "run_job",
]
