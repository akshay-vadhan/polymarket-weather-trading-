"""
╔═══════════════════════════════════════════════════════════════╗
║  Telegram Notification System                                 ║
║  Trading alerts aur summary reports bhejne ke liye           ║
╚═══════════════════════════════════════════════════════════════╝
"""

import os
import logging
from typing import List, Optional, Dict
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Import types (circular import avoid karne ke liye)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .analytics_engine import WeatherMetrics, TradingAnalysis


class TelegramNotifier:
    """
    Telegram Bot API wrapper.
    MarkdownV2 format mein rich messages bhejta hai.
    """

    TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self):
        self.token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.token and self.chat_id
                            and self.token != "your_bot_token_here")

        if not self.enabled:
            logger.warning(
                "Telegram credentials nahi mili. "
                "Notifications disabled hain."
            )

    def _escape_md(self, text: str) -> str:
        """
        Telegram MarkdownV2 ke liye special characters escape karo.
        """
        escape_chars = r"_*[]()~`>#+-=|{}.!\\"
        return "".join(
            f"\\{c}" if c in escape_chars else c
            for c in str(text)
        )

    def _make_url(self, method: str) -> str:
        return self.TELEGRAM_API.format(token=self.token, method=method)

    def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        disable_preview: bool = True
    ) -> bool:
        """Core message send function"""
        if not self.enabled:
            logger.info(f"[Telegram MOCK] Message:\n{text}")
            return True

        try:
            resp = requests.post(
                self._make_url("sendMessage"),
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": disable_preview
                },
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("ok"):
                logger.info("✅ Telegram message sent successfully")
                return True
            else:
                logger.error(f"Telegram API error: {data.get('description')}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def send_alert(
        self,
        analysis: "TradingAnalysis",
        metrics: "WeatherMetrics"
    ) -> bool:
        """
        Single station ke liye alert message bhejo.
        Sirf WATCH ya upar ke alerts bhejta hai.
        """
        from .analytics_engine import AlertLevel

        # Only significant alerts
        if analysis.alert_level == AlertLevel.CLEAR:
            return True

        alert_emoji = {
            AlertLevel.CRITICAL : "🚨",
            AlertLevel.WARNING  : "⚠️",
            AlertLevel.WATCH    : "👁️",
        }.get(analysis.alert_level, "ℹ️")

        signal_emoji = analysis.signal.value.split(" ")[0]

        # Current vs Threshold comparison
        curr_vs_threshold = ""
        if analysis.today_high and analysis.threshold_high:
            diff = analysis.today_high - analysis.threshold_high
            curr_vs_threshold = (
                f"+{diff:.1f}{analysis.temp_unit} ABOVE"
                if diff >= 0
                else f"{diff:.1f}{analysis.temp_unit} BELOW"
            )

        message = (
            f"{alert_emoji} <b>POLYMARKET WEATHER ALERT</b> {alert_emoji}\n"
            f"{'─' * 35}\n\n"
            f"📍 <b>Station:</b> {analysis.city} ({analysis.station_id})\n"
            f"⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M IST/EST')}\n\n"
            f"🌡️ <b>Current T-Max:</b> "
            f"<code>{analysis.today_high}{analysis.temp_unit}</code>\n"
            f"🎯 <b>Trade Boundary:</b> "
            f"<code>{analysis.threshold_low}° - {analysis.threshold_high}{analysis.temp_unit}</code>\n"
            f"📊 <b>Position:</b> <code>{curr_vs_threshold}</code>\n\n"
            f"🤖 <b>Trade Signal:</b> {analysis.signal.value}\n"
            f"📈 <b>Score:</b> {analysis.signal_score}/100 "
            f"(Confidence: {analysis.confidence*100:.0f}%)\n\n"
        )

        # Top bullish/bearish reasons
        if analysis.bullish_factors:
            message += (
                f"✅ <b>Bullish:</b>\n"
                f"  • {analysis.bullish_factors[0]}\n"
            )
        if analysis.bearish_factors:
            message += (
                f"❌ <b>Bearish:</b>\n"
                f"  • {analysis.bearish_factors[0]}\n"
            )

        # Key weather effect
        if analysis.weather_effects:
            message += f"\n🌤️ <b>Key Factor:</b>\n{analysis.weather_effects[0]}\n"

        # Alert message
        message += f"\n{analysis.alert_message}\n"
        message += (
            f"\n<i>Source: "
            f"wunderground.com/history/daily/"
            f"{'in/lucknow' if analysis.station_id == 'VILK' else 'us/ny/new-york-city'}/"
            f"{analysis.station_id}</i>"
        )

        return self.send_message(message)

    def send_full_report(
        self,
        all_metrics: Dict[str, "WeatherMetrics"],
        all_analyses: Dict[str, "TradingAnalysis"]
    ) -> bool:
        """
        Saare stations ki combined trading summary report bhejo.
        GitHub Actions mein har run ke baad bhejta hai.
        """
        run_time = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

        report = (
            f"📊 <b>POLYMARKET WEATHER TRADING REPORT</b>\n"
            f"⏰ {run_time}\n"
            f"{'═' * 38}\n\n"
        )

        for station_id, analysis in all_analyses.items():
            metrics = all_metrics.get(station_id)
            if not metrics:
                continue

            # Anomaly indicator
            anomaly_str = ""
            if analysis.anomaly_pct is not None:
                anomaly_str = (
                    f"📈 +{analysis.anomaly_pct}% anomaly"
                    if analysis.anomaly_pct > 0
                    else f"📉 {analysis.anomaly_pct}% anomaly"
                )

            # Forecast trend
            forecast_str = ""
            if metrics.forecast_highs:
                valid_f = [t for t in metrics.forecast_highs if t]
                if valid_f:
                    forecast_str = (
                        f"Next 3d: "
                        f"{' / '.join(str(t) for t in valid_f[:3])}"
                        f"{analysis.temp_unit}"
                    )

            report += (
                f"{'─' * 38}\n"
                f"📍 <b>{analysis.city}</b> ({station_id})\n\n"
                f"  🌡️ T-Max Today: "
                f"<b>{analysis.today_high}{analysis.temp_unit}</b>\n"
                f"  💧 Humidity: {metrics.humidity}%\n"
                f"  💨 Wind: {metrics.wind_speed} {metrics.wind_unit} "
                f"({metrics.wind_dir_text})\n"
                f"  ☁️  Cloud: {metrics.cloud_cover}%\n"
                f"  💦 Dew Point: {metrics.dew_point}{analysis.temp_unit}\n"
                f"  📅 {forecast_str}\n"
                f"  📊 Hist. Avg: {analysis.historical_avg}{analysis.temp_unit} "
                f"{anomaly_str}\n\n"
                f"  🎯 Threshold: "
                f"{analysis.threshold_low}° - {analysis.threshold_high}"
                f"{analysis.temp_unit}\n"
                f"  {analysis.alert_level.value}\n\n"
                f"  🤖 Signal: <b>{analysis.signal.value}</b>\n"
                f"  📈 Score: {analysis.signal_score}/100 "
                f"[{analysis.confidence*100:.0f}% confidence]\n\n"
            )

            if analysis.bullish_factors:
                report += f"  ✅ <i>{analysis.bullish_factors[0]}</i>\n"
            if analysis.bearish_factors:
                report += f"  ❌ <i>{analysis.bearish_factors[0]}</i>\n"

            report += "\n"

        report += (
            f"{'═' * 38}\n"
            f"⚡ <i>Auto-generated | GitHub Actions</i>\n"
            f"🔗 <a href='https://polymarket.com'>Polymarket</a>"
        )

        return self.send_message(report)

        def send_startup_message(self) -> bool:
        """GitHub Actions run start hone par notification"""
        message = (
            f"🚀 <b>Weather Monitor Started</b>\n"
            f"<code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            f"📍 VILK (Lucknow) | KLGA (New York)\n\n"
            f"<i>Polymarket Weather Trading Bot active hai!</i>"
        )
        return self.send_message(message)
            f"🚀 <b>Weather Monitor Started</b>\n"
            f"⏰ {datetime.now().strftime('%
