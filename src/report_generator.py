"""
╔═══════════════════════════════════════════════════════════════╗
║  Report Generator - Pandas Tables & GitHub Logs              ║
║  Clean terminal output aur structured data tables            ║
╚═══════════════════════════════════════════════════════════════╝
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from .analytics_engine import WeatherMetrics, TradingAnalysis

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Pandas DataFrames se clean terminal tables aur
    GitHub Actions logs ke liye structured output banata hai.
    """

    # ─────────────────────────────────────────────
    #         CURRENT CONDITIONS TABLE
    # ─────────────────────────────────────────────

    def build_current_conditions_table(
        self,
        all_metrics: Dict[str, "WeatherMetrics"]
    ) -> pd.DataFrame:
        """
        Dono stations ke live conditions ek table mein.
        GitHub logs mein clearly dikhega.
        """
        rows = []

        for station_id, m in all_metrics.items():
            rows.append({
                "Station"        : f"{m.city} ({station_id})",
                "Current Temp"   : f"{m.current_temp}{m.temp_unit}" if m.current_temp else "N/A",
                "Real Feel"      : f"{m.real_feel}{m.temp_unit} [{m.real_feel_type}]" if m.real_feel else "N/A",
                "T-Max Today"    : f"{m.today_high}{m.temp_unit}" if m.today_high else "N/A",
                "T-Min Today"    : f"{m.today_low}{m.temp_unit}" if m.today_low else "N/A",
                "Humidity %"     : f"{m.humidity}%" if m.humidity else "N/A",
                "Dew Point"      : f"{m.dew_point}{m.temp_unit}" if m.dew_point else "N/A",
                "Wind"           : f"{m.wind_speed} {m.wind_unit} {m.wind_dir_text}" if m.wind_speed else "N/A",
                "Wind Gust"      : f"{m.wind_gust} {m.wind_unit}" if m.wind_gust else "N/A",
                "Cloud Cover %"  : f"{m.cloud_cover}%" if m.cloud_cover else "N/A",
                "Conditions"     : m.conditions or "N/A",
            })

        df = pd.DataFrame(rows)
        df = df.set_index("Station")
        return df

    # ─────────────────────────────────────────────
    #         FORECAST TABLE
    # ─────────────────────────────────────────────

    def build_forecast_table(
        self,
        all_metrics: Dict[str, "WeatherMetrics"]
    ) -> pd.DataFrame:
        """
        3-day forecast comparison table - dono stations side by side.
        """
        rows = []

        for station_id, m in all_metrics.items():
            for i, date in enumerate(m.forecast_dates[:4]):
                # Date format
                try:
                    date_obj = datetime.strptime(date, "%Y-%m-%d")
                    date_label = date_obj.strftime("%a %b %d")
                    if date_obj.date() == datetime.now().date():
                        date_label = f"TODAY ({date_label})"
                except ValueError:
                    date_label = date

                rows.append({
                    "Station"      : f"{m.city} ({station_id})",
                    "Date"         : date_label,
                    "Forecast High": f"{m.forecast_highs[i]}{m.temp_unit}" if i < len(m.forecast_highs) and m.forecast_highs[i] else "N/A",
                    "Forecast Low" : f"{m.forecast_lows[i]}{m.temp_unit}"  if i < len(m.forecast_lows)  and m.forecast_lows[i]  else "N/A",
                    "Humidity %"   : f"{m.forecast_humidity[i]}%"          if i < len(m.forecast_humidity)  else "N/A",
                    "Wind Speed"   : f"{m.forecast_wind[i]} {m.wind_unit}" if i < len(m.forecast_wind)      else "N/A",
                    "Cloud Cover"  : f"{m.forecast_cloudcover[i]}%"        if i < len(m.forecast_cloudcover) else "N/A",
                    "Conditions"   : m.forecast_conditions[i][:30]         if i < len(m.forecast_conditions) else "N/A",
                })

        df = pd.DataFrame(rows)
        df = df.set_index(["Station", "Date"])
        return df

    # ─────────────────────────────────────────────
    #         HISTORICAL COMPARISON TABLE
    # ─────────────────────────────────────────────

    def build_historical_table(
        self,
        all_metrics: Dict[str, "WeatherMetrics"],
        all_analyses: Dict[str, "TradingAnalysis"]
    ) -> pd.DataFrame:
        """
        Past 5 years ka historical data + threshold comparison.
        Anomaly detection ke liye critical.
        """
        rows = []

        for station_id, m in all_metrics.items():
            analysis = all_analyses.get(station_id)
            threshold = (
                (analysis.threshold_low + analysis.threshold_high) / 2
                if analysis else None
            )

            for record in m.historical_records:
                tempmax = record.get("tempmax")

                # Threshold comparison
                vs_threshold = "N/A"
                if tempmax is not None and threshold is not None:
                    diff = tempmax - threshold
                    vs_threshold = (
                        f"+{diff:.1f}° ABOVE ✅"
                        if diff >= 0
                        else f"{diff:.1f}° BELOW ❌"
                    )

                rows.append({
                    "Station"       : f"{m.city} ({station_id})",
                    "Year"          : record.get("year"),
                    "Date"          : record.get("date"),
                    "T-Max"         : f"{tempmax}{m.temp_unit}" if tempmax else "N/A",
                    "T-Min"         : f"{record.get('tempmin')}{m.temp_unit}" if record.get("tempmin") else "N/A",
                    "Humidity %"    : f"{record.get('humidity')}%" if record.get("humidity") else "N/A",
                    "Wind Speed"    : f"{record.get('windspeed')} {m.wind_unit}" if record.get("windspeed") else "N/A",
                    "Cloud Cover"   : f"{record.get('cloudcover')}%" if record.get("cloudcover") else "N/A",
                    "Conditions"    : str(record.get("conditions", "N/A"))[:25],
                    "vs Threshold"  : vs_threshold,
                })

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.set_index(["Station", "Year"])
        return df

    # ─────────────────────────────────────────────
    #         TRADING SIGNAL TABLE
    # ─────────────────────────────────────────────

    def build_trading_signal_table(
        self,
        all_metrics: Dict[str, "WeatherMetrics"],
        all_analyses: Dict[str, "TradingAnalysis"]
    ) -> pd.DataFrame:
        """
        Final trading signals - sabse important table.
        Portfolio decision ke liye core output.
        """
        rows = []

        for station_id, analysis in all_analyses.items():
            metrics = all_metrics.get(station_id)

            # Historical probability calculate karo
            hist_prob = "N/A"
            if metrics and metrics.historical_records:
                above = sum(
                    1 for r in metrics.historical_records
                    if r.get("tempmax", 0) >= analysis.threshold_low
                )
                hist_prob = f"{(above / len(metrics.historical_records)) * 100:.0f}%"

            # Anomaly display
            anomaly_display = "N/A"
            if analysis.anomaly_pct is not None:
                sign = "+" if analysis.anomaly_pct > 0 else ""
                anomaly_display = f"{sign}{analysis.anomaly_pct}%"

            rows.append({
                "Station"         : f"{analysis.city} ({station_id})",
                "T-Max Today"     : f"{analysis.today_high}{analysis.temp_unit}" if analysis.today_high else "N/A",
                "Best Forecast"   : f"{analysis.best_forecast_high}{analysis.temp_unit}" if analysis.best_forecast_high else "N/A",
                "Hist. Average"   : f"{analysis.historical_avg}{analysis.temp_unit}" if analysis.historical_avg else "N/A",
                "Anomaly"         : anomaly_display,
                "Hist. Prob."     : hist_prob,
                "Threshold Range" : f"{analysis.threshold_low}° - {analysis.threshold_high}{analysis.temp_unit}",
                "Alert Level"     : analysis.alert_level.value,
                "Trade Signal"    : analysis.signal.value,
                "Score (/100)"    : f"{analysis.signal_score}",
                "Confidence"      : f"{analysis.confidence * 100:.0f}%",
            })

        df = pd.DataFrame(rows)
        df = df.set_index("Station")
        return df

    # ─────────────────────────────────────────────
    #         WEATHER EFFECTS TABLE
    # ─────────────────────────────────────────────

    def build_weather_effects_table(
        self,
        all_analyses: Dict[str, "TradingAnalysis"]
    ) -> pd.DataFrame:
        """
        Wind, humidity, cloud cover ke temperature effects.
        Trading reasoning clearly samajhne ke liye.
        """
        rows = []

        for station_id, analysis in all_analyses.items():
            # Bullish factors
            for factor in analysis.bullish_factors:
                rows.append({
                    "Station"   : f"{analysis.city} ({station_id})",
                    "Type"      : "✅ BULLISH",
                    "Factor"    : factor,
                })

            # Bearish factors
            for factor in analysis.bearish_factors:
                rows.append({
                    "Station"   : f"{analysis.city} ({station_id})",
                    "Type"      : "❌ BEARISH",
                    "Factor"    : factor,
                })

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.set_index(["Station", "Type"])
        return df

    # ─────────────────────────────────────────────
    #         PRINT ALL TABLES
    # ─────────────────────────────────────────────

    def print_all_tables(
        self,
        all_metrics: Dict[str, "WeatherMetrics"],
        all_analyses: Dict[str, "TradingAnalysis"]
    ):
        """
        GitHub Actions logs mein saari tables print karo.
        pd.set_option se full width display hoga.
        """
        # Pandas display settings
        pd.set_option("display.max_columns",     None)
        pd.set_option("display.max_rows",        None)
        pd.set_option("display.width",           None)
        pd.set_option("display.max_colwidth",    60)
        pd.set_option("display.colheader_justify", "left")

        separator = "═" * 80
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

        print(f"\n{separator}")
        print(f"  POLYMARKET WEATHER TRADING ANALYTICS")
        print(f"  Stations: VILK (Lucknow) | KLGA (New York)")
        print(f"  Generated: {timestamp}")
        print(f"{separator}\n")

        # ── Table 1: Current Conditions ─────────
        print("📡 TABLE 1: LIVE CURRENT CONDITIONS")
        print("─" * 80)
        df_current = self.build_current_conditions_table(all_metrics)
        if not df_current.empty:
            print(df_current.to_string())
        else:
            print("  ⚠️  No current data available")
        print()

        # ── Table 2: Forecast ───────────────────
        print("📅 TABLE 2: 3-DAY FORECAST")
        print("─" * 80)
        df_forecast = self.build_forecast_table(all_metrics)
        if not df_forecast.empty:
            print(df_forecast.to_string())
        else:
            print("  ⚠️  No forecast data available")
        print()

        # ── Table 3: Historical ─────────────────
        print("📊 TABLE 3: HISTORICAL SAME-DATE DATA (Past 5 Years)")
        print("─" * 80)
        df_historical = self.build_historical_table(all_metrics, all_analyses)
        if not df_historical.empty:
            print(df_historical.to_string())
        else:
            print("  ⚠️  No historical data available")
        print()

        # ── Table 4: Weather Effects ────────────
        print("🌤️  TABLE 4: WEATHER EFFECTS ANALYSIS")
        print("─" * 80)
        df_effects = self.build_weather_effects_table(all_analyses)
        if not df_effects.empty:
            print(df_effects.to_string())
        else:
            print("  ⚠️  No effects data available")
        print()

        # ── Table 5: Trading Signals ────────────
        print("🎯 TABLE 5: TRADING SIGNALS - FINAL DECISION")
        print("═" * 80)
        df_signals = self.build_trading_signal_table(all_metrics, all_analyses)
        if not df_signals.empty:
            print(df_signals.to_string())
        else:
            print("  ⚠️  No signal data available")
        print(f"\n{separator}")

        # ── Weather Logic Notes ─────────────────
        print("\n📝 WEATHER EFFECTS LOGIC NOTES:")
        print("─" * 80)
        for station_id, analysis in all_analyses.items():
            print(f"\n  [{analysis.city} - {station_id}]")
            for effect in analysis.weather_effects:
                print(f"  → {effect}")

        print(f"\n{separator}\n")

    # ─────────────────────────────────────────────
    #         EXPORT TO CSV (OPTIONAL)
    # ─────────────────────────────────────────────

    def export_to_csv(
        self,
        all_metrics: Dict[str, "WeatherMetrics"],
        all_analyses: Dict[str, "TradingAnalysis"],
        output_dir: str = "data"
    ):
        """
        Data ko CSV mein save karo (local analysis ke liye).
        GitHub Actions artifacts mein upload bhi ho sakta hai.
        """
        import os
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M")

        tables = {
            f"current_{timestamp}"   : self.build_current_conditions_table(all_metrics),
            f"forecast_{timestamp}"  : self.build_forecast_table(all_metrics),
            f"historical_{timestamp}": self.build_historical_table(all_metrics, all_analyses),
            f"signals_{timestamp}"   : self.build_trading_signal_table(all_metrics, all_analyses),
        }

        saved_files = []
        for name, df in tables.items():
            if not df.empty:
                filepath = f"{output_dir}/{name}.csv"
                df.to_csv(filepath)
                saved_files.append(filepath)
                logger.info(f"CSV saved: {filepath}")

        return saved_files
