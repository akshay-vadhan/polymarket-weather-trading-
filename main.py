#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════╗
║   POLYMARKET WEATHER TRADING ANALYTICS - MAIN ENTRY POINT        ║
║   Stations: VILK (Lucknow, °C) | KLGA (New York, °F)            ║
║   Features: Live Data | Forecast | Historical | Trade Signals     ║
║   Alerts: Telegram Bot | GitHub Actions Logs                      ║
╚═══════════════════════════════════════════════════════════════════╝

Usage:
    python main.py                    # Full run (default)
    python main.py --mode quick       # Historical data skip karo
    python main.py --mode signal      # Sirf trading signals
    python main.py --no-telegram      # Telegram alerts band karo
    python main.py --export-csv       # CSV files save karo
    python main.py --test-telegram    # Telegram connection test karo
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

from dotenv import load_dotenv

# ─────────────────────────────────────────────────
#              LOGGING SETUP
# ─────────────────────────────────────────────────

def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    GitHub Actions aur local dono ke liye
    clean logging configure karo.
    """
    log_format = (
        "%(asctime)s | %(levelname)-8s | "
        "%(module)-20s | %(message)s"
    )
    logging.basicConfig(
        level    = getattr(logging, level.upper(), logging.INFO),
        format   = log_format,
        datefmt  = "%Y-%m-%d %H:%M:%S",
        handlers = [
            logging.StreamHandler(sys.stdout),
        ]
    )
    # Requests library ka verbose logging band karo
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    return logging.getLogger("main")


# ─────────────────────────────────────────────────
#              IMPORTS (after logging setup)
# ─────────────────────────────────────────────────

load_dotenv()

try:
    from src.weather_fetcher   import WeatherAPIClient
    from src.analytics_engine  import (
        WeatherDataProcessor,
        TradingSignalEngine,
        WeatherMetrics,
        TradingAnalysis,
        AlertLevel
    )
    from src.telegram_notifier import TelegramNotifier
    from src.report_generator  import ReportGenerator

except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("   pip install -r requirements.txt chalaiye")
    sys.exit(1)


# ─────────────────────────────────────────────────
#              CONFIG LOADER
# ─────────────────────────────────────────────────

def load_config() -> dict:
    """
    stations.json se config load karo.
    Environment variables se thresholds override karo.
    """
    config_path = Path("config/stations.json")

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file nahi mili: {config_path}\n"
            "Project structure check karo."
        )

    with open(config_path, "r") as f:
        config = json.load(f)

    # Environment variables se threshold override
    env_overrides = {
        "VILK": {
            "threshold_low" : os.getenv("VILK_THRESHOLD_LOW"),
            "threshold_high": os.getenv("VILK_THRESHOLD_HIGH"),
        },
        "KLGA": {
            "threshold_low" : os.getenv("KLGA_THRESHOLD_LOW"),
            "threshold_high": os.getenv("KLGA_THRESHOLD_HIGH"),
        }
    }

    for station_id, overrides in env_overrides.items():
        if station_id in config.get("trade_boundaries", {}):
            for key, val in overrides.items():
                if val is not None:
                    config["trade_boundaries"][station_id][key] = float(val)

    return config


# ─────────────────────────────────────────────────
#              CORE PIPELINE
# ─────────────────────────────────────────────────

class WeatherTradingPipeline:
    """
    Main orchestrator class.
    Data fetch → Process → Analyze → Report → Alert
    """

    def __init__(self, config: dict, args: argparse.Namespace):
        self.config    = config
        self.args      = args
        self.logger    = logging.getLogger("pipeline")

        # Components initialize karo
        self.api_client  = WeatherAPIClient()
        self.processor   = WeatherDataProcessor()
        self.signal_eng  = TradingSignalEngine()
        self.notifier    = TelegramNotifier()
        self.reporter    = ReportGenerator()

        # Results store karne ke liye
        self.raw_data    : Dict[str, dict]             = {}
        self.all_metrics : Dict[str, WeatherMetrics]   = {}
        self.all_analyses: Dict[str, TradingAnalysis]  = {}

    # ── Step 1: Fetch Data ────────────────────────

    def fetch_data(self):
        """
        VILK aur KLGA dono ke liye data fetch karo.
        Mode ke hisaab se historical data skip ho sakta hai.
        """
        self.logger.info("=" * 60)
        self.logger.info("STEP 1: WEATHER DATA FETCHING")
        self.logger.info("=" * 60)

        stations_config = self.config["stations"]

        if self.args.mode == "quick":
            # Quick mode: historical data skip
            self.logger.info("Quick mode: Historical data skip ho raha hai")

            for station_id, cfg in stations_config.items():
                self.logger.info(f"Fetching: {cfg['name']}")

                current_data  = self.api_client.get_current_and_today(
                    station_id, cfg["unit_group"]
                )
                forecast_data = self.api_client.get_forecast(
                    station_id, cfg["unit_group"], days=3
                )

                self.raw_data[station_id] = {
                    "config"     : cfg,
                    "current"    : current_data,
                    "forecast"   : forecast_data,
                    "historical" : [],          # Empty in quick mode
                    "fetch_time" : datetime.now().isoformat()
                }

        else:
            # Full mode: saara data
            self.raw_data = self.api_client.get_multi_station_data(
                stations_config
            )

        # Fetch summary
        for station_id, data in self.raw_data.items():
            has_current    = data.get("current") is not None
            has_forecast   = data.get("forecast") is not None
            hist_count     = len(data.get("historical", []))

            self.logger.info(
                f"  {station_id}: Current={'✅' if has_current else '❌'} | "
                f"Forecast={'✅' if has_forecast else '❌'} | "
                f"Historical={hist_count} records"
            )

    # ── Step 2: Process Metrics ──────────────────

    def process_metrics(self):
        """
        Raw data ko WeatherMetrics objects mein convert karo.
        Physics calculations (Heat Index, Wind Chill etc.) apply karo.
        """
        self.logger.info("=" * 60)
        self.logger.info("STEP 2: METRICS PROCESSING")
        self.logger.info("=" * 60)

        trade_boundaries = self.config["trade_boundaries"]

        for station_id, raw in self.raw_data.items():
            trade_config = trade_boundaries.get(station_id, {})

            self.logger.info(f"Processing: {station_id}")
            metrics = self.processor.process_station_data(
                station_id  = station_id,
                raw_data    = raw,
                trade_config= trade_config
            )
            self.all_metrics[station_id] = metrics

            self.logger.info(
                f"  T-Max: {metrics.today_high}{metrics.temp_unit} | "
                f"Humidity: {metrics.humidity}% | "
                f"Wind: {metrics.wind_speed} {metrics.wind_unit} {metrics.wind_dir_text} | "
                f"Anomaly: {metrics.anomaly_score}%"
            )

    # ── Step 3: Trading Analysis ─────────────────

    def run_analysis(self):
        """
        Trading signals generate karo.
        Score-based system: -100 (Strong Avoid) to +100 (Strong Buy).
        """
        self.logger.info("=" * 60)
        self.logger.info("STEP 3: TRADING SIGNAL ANALYSIS")
        self.logger.info("=" * 60)

        trade_boundaries = self.config["trade_boundaries"]

        for station_id, metrics in self.all_metrics.items():
            trade_config = trade_boundaries.get(station_id, {})

            self.logger.info(f"Analyzing: {station_id}")
            analysis = self.signal_eng.analyze(
                metrics      = metrics,
                trade_config = trade_config,
                station_id   = station_id
            )
            self.all_analyses[station_id] = analysis

            self.logger.info(
                f"  Signal: {analysis.signal.value} | "
                f"Score: {analysis.signal_score}/100 | "
                f"Confidence: {analysis.confidence*100:.0f}% | "
                f"Alert: {analysis.alert_level.value}"
            )

    # ── Step 4: Generate Reports ─────────────────

    def generate_reports(self):
        """
        GitHub Actions logs mein Pandas tables print karo.
        Optional: CSV files export karo.
        """
        self.logger.info("=" * 60)
        self.logger.info("STEP 4: REPORT GENERATION")
        self.logger.info("=" * 60)

        # Terminal mein saari tables print karo
        self.reporter.print_all_tables(
            self.all_metrics,
            self.all_analyses
        )

        # CSV export (agar flag diya ho)
        if self.args.export_csv:
            self.logger.info("CSV export kar raha hai...")
            saved_files = self.reporter.export_to_csv(
                self.all_metrics,
                self.all_analyses,
                output_dir="data/exports"
            )
            for f in saved_files:
                self.logger.info(f"  ✅ Saved: {f}")

    # ── Step 5: Send Alerts ──────────────────────

    def send_alerts(self):
        """
        Telegram par alerts aur summary report bhejo.
        --no-telegram flag se skip ho sakta hai.
        """
        self.logger.info("=" * 60)
        self.logger.info("STEP 5: TELEGRAM NOTIFICATIONS")
        self.logger.info("=" * 60)

        if self.args.no_telegram:
            self.logger.info(
                "Telegram disabled (--no-telegram flag). Skipping."
            )
            return

        # Individual alerts (sirf WATCH ya upar ke liye)
        alert_sent_count = 0
        for station_id, analysis in self.all_analyses.items():
            metrics = self.all_metrics.get(station_id)

            if analysis.alert_level != AlertLevel.CLEAR:
                self.logger.info(
                    f"Alert bhej raha hai: {station_id} - "
                    f"{analysis.alert_level.value}"
                )
                success = self.notifier.send_alert(analysis, metrics)
                if success:
                    alert_sent_count += 1

        # Full summary report (har run ke baad)
        self.logger.info("Full summary report bhej raha hai...")
        self.notifier.send_full_report(self.all_metrics, self.all_analyses)

        self.logger.info(
            f"Telegram: {alert_sent_count} alerts + 1 summary sent"
        )

    # ── Complete Pipeline ────────────────────────

    def run(self):
        """
        Complete pipeline execute karo.
        Step by step: Fetch → Process → Analyze → Report → Alert
        """
        start_time = datetime.now()

        self.logger.info("\n" + "█" * 60)
        self.logger.info("  POLYMARKET WEATHER TRADING ANALYTICS v2.0")
        self.logger.info(f"  Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"  Mode: {self.args.mode.upper()}")
        self.logger.info("█" * 60 + "\n")

        try:
            # Step 1: Data Fetch
            self.fetch_data()

            # Step 2: Process Metrics
            self.process_metrics()

            # Step 3: Trade Analysis
            if self.args.mode != "data-only":
                self.run_analysis()

            # Step 4: Reports
            self.generate_reports()

            # Step 5: Alerts
            if self.args.mode not in ["data-only", "signal"]:
                self.send_alerts()
            elif self.args.mode == "signal":
                # Signal mode mein sirf critical alerts
                for station_id, analysis in self.all_analyses.items():
                    metrics = self.all_metrics.get(station_id)
                    if analysis.alert_level in [AlertLevel.CRITICAL, AlertLevel.WARNING]:
                        self.notifier.send_alert(analysis, metrics)

        except KeyboardInterrupt:
            self.logger.info("\n⛔ User ne stop kiya.")
            sys.exit(0)

        except ValueError as e:
            self.logger.error(f"Configuration Error: {e}")
            sys.exit(1)

        except Exception as e:
            self.logger.error(f"Unexpected error: {e}", exc_info=True)

            # GitHub Actions failure notification
            if os.getenv("GITHUB_ACTIONS") == "true":
                error_msg = (
                    f"🔴 <b>GitHub Actions Run FAILED</b>\n"
                    f"Error: <code>{str(e)[:200]}</code>\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}"
                )
                self.notifier.send_message(error_msg)

            sys.exit(1)

        finally:
            end_time  = datetime.now()
            duration  = (end_time - start_time).seconds
            self.logger.info(
                f"\n✅ Pipeline complete | "
                f"Duration: {duration}s | "
                f"Ended: {end_time.strftime('%H:%M:%S')}"
            )


# ─────────────────────────────────────────────────
#         TELEGRAM TEST FUNCTION
# ─────────────────────────────────────────────────

def test_telegram_connection(notifier: TelegramNotifier):
    """
    Telegram bot connection test karo.
    python main.py --test-telegram se run karo.
    """
    logger = logging.getLogger("telegram_test")
    logger.info("Telegram connection test kar raha hai...")

    test_msg = (
        f"🧪 <b>Telegram Connection Test</b>\n\n"
        f"✅ Bot successfully connected!\n"
        f"📍 Stations: VILK (Lucknow) | KLGA (New York)\n"
        f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"<i>Polymarket Weather Trading Bot active hai!</i>"
    )

    success = notifier.send_message(test_msg)

    if success:
        logger.info("✅ Telegram test successful! Message sent.")
    else:
        logger.error(
            "❌ Telegram test failed!\n"
            "   TELEGRAM_BOT_TOKEN aur TELEGRAM_CHAT_ID check karo."
        )
    return success


# ─────────────────────────────────────────────────
#         ARGUMENT PARSER
# ─────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    """CLI arguments define karo"""

    parser = argparse.ArgumentParser(
        description="Polymarket Weather Trading Analytics Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Run Modes:
  full        → Saara data + analysis + alerts (default)
  quick       → Historical skip, fast run
  signal      → Sirf signals, critical alerts bhejo
  data-only   → Sirf data fetch aur display karo

Examples:
  python main.py
  python main.py --mode quick --no-telegram
  python main.py --mode signal --export-csv
  python main.py --test-telegram
  python main.py --log-level DEBUG
        """
    )

    parser.add_argument(
        "--mode",
        choices=["full", "quick", "signal", "data-only"],
        default=os.getenv("RUN_MODE", "full"),
        help="Run mode (default: full)"
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        default=False,
        help="Telegram notifications disable karo"
    )
    parser.add_argument(
        "--export-csv",
        action="store_true",
        default=False,
        help="Data CSV files mein export karo"
    )
    parser.add_argument(
        "--test-telegram",
        action="store_true",
        default=False,
        help="Telegram connection test karo aur exit"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    parser.add_argument(
        "--station",
        choices=["VILK", "KLGA", "both"],
        default="both",
        help="Specific station ya both (default: both)"
    )

    return parser.parse_args()


# ─────────────────────────────────────────────────
#         ENVIRONMENT VALIDATION
# ─────────────────────────────────────────────────

def validate_environment(logger: logging.Logger) -> bool:
    """
    Required environment variables check karo.
    GitHub Actions mein Secrets se aate hain.
    """
    required_vars = {
        "VISUAL_CROSSING_API_KEY": "Visual Crossing API key",
    }
    optional_vars = {
        "TELEGRAM_BOT_TOKEN" : "Telegram bot token (alerts ke liye)",
        "TELEGRAM_CHAT_ID"   : "Telegram chat ID (alerts ke liye)",
    }

    all_ok = True

    for var, description in required_vars.items():
        val = os.getenv(var, "")
        if not val or val == "your_api_key_here":
            logger.error(
                f"❌ Missing required: {var} ({description})\n"
                f"   .env file ya GitHub Secrets mein set karo"
            )
            all_ok = False
        else:
            logger.info(f"✅ {var}: Set ({val[:8]}...)")

    for var, description in optional_vars.items():
        val = os.getenv(var, "")
        if not val or "your_" in val:
            logger.warning(f"⚠️  Optional not set: {var} ({description})")
        else:
            logger.info(f"✅ {var}: Set")

    return all_ok


# ─────────────────────────────────────────────────
#         MAIN ENTRY POINT
# ─────────────────────────────────────────────────

def main():
    """
    Main entry point.
    Argument parsing → Validation → Pipeline execution
    """
    # 1. Arguments parse karo
    args = parse_args()

    # 2. Logging setup
    logger = setup_logging(args.log_level)

    # 3. GitHub Actions environment detect karo
    is_github_actions = os.getenv("GITHUB_ACTIONS", "false") == "true"
    if is_github_actions:
        logger.info("🔧 GitHub Actions environment detected")

    # 4. Telegram test mode
    if args.test_telegram:
        notifier = TelegramNotifier()
        success  = test_telegram_connection(notifier)
        sys.exit(0 if success else 1)

    # 5. Environment validate karo
    logger.info("Environment variables check kar raha hai...")
    if not validate_environment(logger):
        logger.error(
            "\n❌ Environment setup incomplete!\n"
            "   1. .env.example ko copy karke .env banao\n"
            "   2. API keys fill karo\n"
            "   3. GitHub Secrets mein bhi set karo"
        )
        sys.exit(1)

    # 6. Config load karo
    try:
        config = load_config()
        logger.info(
            f"Config loaded: "
            f"{len(config['stations'])} stations | "
            f"Thresholds: "
            f"VILK={config['trade_boundaries']['VILK']['threshold_low']}-"
            f"{config['trade_boundaries']['VILK']['threshold_high']}°C | "
            f"KLGA={config['trade_boundaries']['KLGA']['threshold_low']}-"
            f"{config['trade_boundaries']['KLGA']['threshold_high']}°F"
        )
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    # 7. Single station filter (agar --station diya ho)
    if args.station != "both":
        config["stations"] = {
            args.station: config["stations"][args.station]
        }
        logger.info(f"Single station mode: {args.station}")

    # 8. Pipeline run karo
    pipeline = WeatherTradingPipeline(config=config, args=args)
    pipeline.run()


if __name__ == "__main__":
    main()
