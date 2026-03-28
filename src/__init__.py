"""
Polymarket Weather Trading Analytics Package
"""
from .weather_fetcher   import WeatherAPIClient, CacheManager
from .analytics_engine  import (
    WeatherDataProcessor,
    TradingSignalEngine,
    WeatherMetrics,
    TradingAnalysis,
    TradeSignal,
    AlertLevel,
    WeatherPhysics
)
from .telegram_notifier import TelegramNotifier
from .report_generator  import ReportGenerator

__version__ = "2.0.0"
__all__ = [
    "WeatherAPIClient",
    "CacheManager",
    "WeatherDataProcessor",
    "TradingSignalEngine",
    "WeatherMetrics",
    "TradingAnalysis",
    "TradeSignal",
    "AlertLevel",
    "WeatherPhysics",
    "TelegramNotifier",
    "ReportGenerator",
]
