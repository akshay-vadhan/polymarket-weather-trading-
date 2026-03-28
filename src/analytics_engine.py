"""
╔═══════════════════════════════════════════════════════════════╗
║  Analytics Engine - Trading Signal Generator                  ║
║  Anomaly Detection, Wind/Humidity Analysis, Trade Signals     ║
╚═══════════════════════════════════════════════════════════════╝
"""

import math
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────
#              ENUMS & DATACLASSES
# ─────────────────────────────────────────────────

class TradeSignal(Enum):
    """Trading recommendation levels"""
    STRONG_BUY     = "🟢 STRONG BUY"
    BUY            = "🔵 BUY"
    NEUTRAL        = "🟡 NEUTRAL"
    AVOID          = "🔴 AVOID"
    STRONG_AVOID   = "⛔ STRONG AVOID"
    INSUFFICIENT   = "⚪ INSUFFICIENT DATA"


class AlertLevel(Enum):
    """Alert severity levels"""
    CRITICAL = "🚨 CRITICAL"
    WARNING  = "⚠️  WARNING"
    WATCH    = "👁️  WATCH"
    CLEAR    = "✅ CLEAR"


@dataclass
class WeatherMetrics:
    """Ek station ke liye processed weather metrics"""
    station_id: str
    city: str
    temp_unit: str
    wind_unit: str

    # Current readings
    current_temp: Optional[float] = None
    feels_like: Optional[float] = None
    today_high: Optional[float] = None
    today_low: Optional[float] = None

    # Atmospheric
    humidity: Optional[float] = None
    dew_point: Optional[float] = None
    cloud_cover: Optional[float] = None
    pressure: Optional[float] = None
    visibility: Optional[float] = None

    # Wind
    wind_speed: Optional[float] = None
    wind_dir_deg: Optional[float] = None
    wind_dir_text: str = "N/A"
    wind_gust: Optional[float] = None

    # Forecast
    forecast_highs: List[float] = field(default_factory=list)
    forecast_lows: List[float] = field(default_factory=list)
    forecast_dates: List[str] = field(default_factory=list)
    forecast_conditions: List[str] = field(default_factory=list)
    forecast_humidity: List[float] = field(default_factory=list)
    forecast_wind: List[float] = field(default_factory=list)
    forecast_cloudcover: List[float] = field(default_factory=list)

    # Historical
    historical_avg_high: Optional[float] = None
    historical_max_high: Optional[float] = None
    historical_min_high: Optional[float] = None
    historical_records: List[dict] = field(default_factory=list)

    # Computed
    real_feel: Optional[float] = None
    real_feel_type: str = ""   # "Wind Chill" ya "Heat Index"
    anomaly_score: Optional[float] = None   # % above/below historical avg
    conditions: str = ""


@dataclass
class TradingAnalysis:
    """Complete trading analysis result"""
    station_id: str
    city: str
    signal: TradeSignal
    alert_level: AlertLevel
    confidence: float          # 0.0 - 1.0
    signal_score: float        # -100 to +100

    # Key reasons
    bullish_factors: List[str] = field(default_factory=list)
    bearish_factors: List[str] = field(default_factory=list)
    weather_effects: List[str] = field(default_factory=list)

    # Threshold analysis
    threshold_low: float = 0.0
    threshold_high: float = 0.0
    today_high: Optional[float] = None
    best_forecast_high: Optional[float] = None
    historical_avg: Optional[float] = None
    anomaly_pct: Optional[float] = None

    # Alert details
    alert_message: str = ""
    temp_unit: str = "°C"


# ─────────────────────────────────────────────────
#          WEATHER PHYSICS CALCULATIONS
# ─────────────────────────────────────────────────

class WeatherPhysics:
    """
    Temperature par weather metrics ka asar.
    VILK aur KLGA ke liye specific analysis.
    """

    @staticmethod
    def celsius_to_fahrenheit(c: float) -> float:
        return round((c * 9 / 5) + 32, 2)

    @staticmethod
    def fahrenheit_to_celsius(f: float) -> float:
        return round((f - 32) * 5 / 9, 2)

    @staticmethod
    def wind_direction_text(degrees: Optional[float]) -> str:
        """Degrees se compass direction text"""
        if degrees is None:
            return "N/A"
        directions = [
            "N",   "NNE", "NE", "ENE",
            "E",   "ESE", "SE", "SSE",
            "S",   "SSW", "SW", "WSW",
            "W",   "WNW", "NW", "NNW"
        ]
        return directions[round(degrees / 22.5) % 16]

    @staticmethod
    def heat_index_fahrenheit(temp_f: float, humidity: float) -> float:
        """
        Rothfusz Equation - Heat Index (°F).
        Valid: temp >= 80°F, humidity >= 40%
        """
        if temp_f < 80 or humidity < 40:
            return temp_f
        hi = (
            -42.379
            + 2.04901523 * temp_f
            + 10.14333127 * humidity
            - 0.22475541 * temp_f * humidity
            - 0.00683783 * temp_f ** 2
            - 0.05481717 * humidity ** 2
            + 0.00122874 * temp_f ** 2 * humidity
            + 0.00085282 * temp_f * humidity ** 2
            - 0.00000199 * temp_f ** 2 * humidity ** 2
        )
        return round(hi, 1)

    @staticmethod
    def heat_index_celsius(temp_c: float, humidity: float) -> float:
        """Heat Index Celsius mein (VILK ke liye)"""
        if temp_c < 27 or humidity < 40:
            return temp_c
        # Steadman simplified formula for Celsius
        hi = (
            -8.78469475556
            + 1.61139411 * temp_c
            + 2.33854883889 * humidity
            - 0.14611605 * temp_c * humidity
            - 0.012308094 * temp_c ** 2
            - 0.0164248277778 * humidity ** 2
            + 0.002211732 * temp_c ** 2 * humidity
            + 0.00072546 * temp_c * humidity ** 2
            - 0.000003582 * temp_c ** 2 * humidity ** 2
        )
        return round(hi, 1)

    @staticmethod
    def wind_chill_fahrenheit(temp_f: float, wind_mph: float) -> float:
        """
        NWS Wind Chill Formula (°F).
        Valid: temp <= 50°F, wind >= 3 mph
        """
        if temp_f > 50 or wind_mph < 3:
            return temp_f
        wc = (
            35.74
            + 0.6215 * temp_f
            - 35.75 * wind_mph ** 0.16
            + 0.4275 * temp_f * wind_mph ** 0.16
        )
        return round(wc, 1)

    @staticmethod
    def wind_chill_celsius(temp_c: float, wind_kph: float) -> float:
        """
        Wind Chill Celsius mein (VILK ke liye).
        Valid: temp <= 10°C, wind >= 4.8 kph
        """
        if temp_c > 10 or wind_kph < 4.8:
            return temp_c
        wc = (
            13.12
            + 0.6215 * temp_c
            - 11.37 * wind_kph ** 0.16
            + 0.3965 * temp_c * wind_kph ** 0.16
        )
        return round(wc, 1)

    @staticmethod
    def dew_point_depression(temp: float, dew_point: float) -> float:
        """
        Dew Point Depression = Temp - Dew Point.
        Zyada depression = dry air = potentially higher max temp.
        """
        return round(temp - dew_point, 2)

    @staticmethod
    def cloud_cover_effect(cloud_pct: float) -> Tuple[float, str]:
        """
        Cloud cover ka temperature par estimated asar.
        Returns (delta_temp, description)
        """
        if cloud_pct <= 10:
            return (+2.0, "Clear sky: Max radiation, significant warming (+2°)")
        elif cloud_pct <= 30:
            return (+1.0, "Mostly clear: Good solar heating (+1°)")
        elif cloud_pct <= 60:
            return (0.0, "Partly cloudy: Neutral effect (0°)")
        elif cloud_pct <= 80:
            return (-1.5, "Mostly cloudy: Reduced heating (-1.5°)")
        else:
            return (-3.0, "Overcast: Strong cooling effect (-3°)")

    @staticmethod
    def wind_cooling_effect(wind_speed: float, unit: str = "mph") -> Tuple[float, str]:
        """
        Wind speed ka T-Max par estimated cooling asar.
        Sea breeze aur land breeze effects (KLGA ke liye relevant).
        """
        if unit == "kph":
            wind_speed = wind_speed * 0.621371  # Convert to mph

        if wind_speed < 5:
            return (0.0, "Calm: No wind cooling, max temp unaffected")
        elif wind_speed < 10:
            return (-0.5, "Light breeze: Minor cooling (-0.5°)")
        elif wind_speed < 20:
            return (-1.5, "Moderate wind: Notable cooling (-1.5°)")
        elif wind_speed < 30:
            return (-3.0, "Strong wind: Significant cooling (-3°)")
        else:
            return (-5.0, "Very strong wind: Major cooling (-5°)")

    @staticmethod
    def humidity_effect_on_tmax(humidity: float,
                                 temp: float,
                                 unit: str = "C") -> Tuple[float, str]:
        """
        High humidity afternoon temperatures ko suppress karta hai
        (evaporative cooling effect).
        """
        if unit == "F":
            # Convert to C for calculation
            temp = (temp - 32) * 5 / 9

        if humidity < 30:
            return (+1.5, f"Very dry air (RH={humidity}%): High evaporation, max temp boost (+1.5°)")
        elif humidity < 50:
            return (+0.5, f"Dry air (RH={humidity}%): Slight max temp boost (+0.5°)")
        elif humidity < 70:
            return (0.0, f"Moderate humidity (RH={humidity}%): Neutral effect")
        elif humidity < 85:
            return (-1.0, f"High humidity (RH={humidity}%): Evaporative cooling (-1°)")
        else:
            return (-2.0, f"Very high humidity (RH={humidity}%): Strong suppression (-2°)")

    @staticmethod
    def klga_sea_breeze_analysis(
        wind_dir_deg: Optional[float],
        wind_speed: float,
        month: int
    ) -> str:
        """
        KLGA ke liye Sea Breeze analysis.
        LaGuardia Long Island Sound ke paas hai.
        South/Southeast winds = sea breeze = temperature cooling.
        """
        if wind_dir_deg is None:
            return "Wind direction unknown - sea breeze effect unclear"

        direction = WeatherPhysics.wind_direction_text(wind_dir_deg)

        # Sea breeze directions (Long Island Sound se)
        sea_breeze_dirs = {"S", "SE", "SSE", "ESE", "E"}
        land_breeze_dirs = {"N", "NW", "NNW", "WNW", "W"}

        if direction in sea_breeze_dirs:
            cooling = -2.0 if month in [5, 6, 7, 8, 9] else -1.0
            return (
                f"🌊 SEA BREEZE ACTIVE ({direction} @ {wind_speed}mph): "
                f"Long Island Sound se thandak aa rahi hai. "
                f"T-Max pe estimated {cooling}°F effect. "
                f"Trading implication: BEARISH for high temp contracts."
            )
        elif direction in land_breeze_dirs:
            warming = +1.5 if month in [11, 12, 1, 2, 3] else +0.5
            return (
                f"🏙️  LAND BREEZE ({direction} @ {wind_speed}mph): "
                f"Continental air, drier & warmer. "
                f"T-Max pe estimated +{warming}°F effect. "
                f"Trading implication: BULLISH for high temp contracts."
            )
        else:
            return (
                f"➡️  NEUTRAL WIND ({direction} @ {wind_speed}mph): "
                f"Sea breeze effect minimal. Standard temperature pattern."
            )

    @staticmethod
    def vilk_wind_analysis(
        wind_dir_deg: Optional[float],
        wind_speed: float,
        month: int
    ) -> str:
        """
        VILK (Lucknow) ke liye wind analysis.
        Hot westerly winds (loo) = extreme heat.
        Easterly winds = moisture, cooling.
        """
        if wind_dir_deg is None:
            return "Wind direction unknown"

        direction = WeatherPhysics.wind_direction_text(wind_dir_deg)

        # Loo (hot dry western winds) - NW to SW
        loo_directions = {"W", "WNW", "WSW", "NW", "NNW"}
        # Moisture bearing easterlies
        east_dirs = {"E", "ENE", "ESE", "NE", "SE"}

        if direction in loo_directions and month in [3, 4, 5, 6]:
            return (
                f"🌪️  LOO WINDS ACTIVE ({direction} @ {wind_speed}km/h): "
                f"Rajasthan se garam, sukhha hawa aa raha hai. "
                f"T-Max mein +3°C se +5°C ki baddhotri expected. "
                f"Trading implication: STRONGLY BULLISH for high temp contracts!"
            )
        elif direction in east_dirs:
            return (
                f"💧 EASTERLY MOISTURE ({direction} @ {wind_speed}km/h): "
                f"Bay of Bengal se nami aa sakti hai. "
                f"T-Max suppressed, cloud formation possible. "
                f"Trading implication: BEARISH for high temp contracts."
            )
        else:
            return (
                f"➡️  NEUTRAL WINDS ({direction} @ {wind_speed}km/h): "
                f"Standard temperature pattern expected."
            )


# ─────────────────────────────────────────────────
#          DATA PROCESSOR
# ─────────────────────────────────────────────────

class WeatherDataProcessor:
    """
    Raw API data ko WeatherMetrics mein convert karo
    """

    def __init__(self):
        self.physics = WeatherPhysics()

    def process_station_data(
        self,
        station_id: str,
        raw_data: dict,
        trade_config: dict
    ) -> WeatherMetrics:
        """Raw API data se WeatherMetrics banao"""

        config = raw_data["config"]
        current_raw = raw_data.get("current", {})
        forecast_raw = raw_data.get("forecast", {})
        historical_raw = raw_data.get("historical", [])

        metrics = WeatherMetrics(
            station_id=station_id,
            city=config["city"],
            temp_unit=config["temp_unit"],
            wind_unit=config["wind_unit"]
        )

        # ── Current Conditions ──────────────────────
        if current_raw:
            curr = current_raw.get("currentConditions", {})
            days = current_raw.get("days", [{}])
            today = days[0] if days else {}

            metrics.current_temp = curr.get("temp")
            metrics.feels_like   = curr.get("feelslike")
            metrics.today_high   = today.get("tempmax")
            metrics.today_low    = today.get("tempmin")
            metrics.humidity     = curr.get("humidity")
            metrics.dew_point    = curr.get("dew")
            metrics.cloud_cover  = curr.get("cloudcover")
            metrics.pressure     = curr.get("pressure")
            metrics.visibility   = curr.get("visibility")
            metrics.wind_speed   = curr.get("windspeed")
            metrics.wind_dir_deg = curr.get("winddir")
            metrics.wind_gust    = curr.get("windgust")
            metrics.conditions   = today.get("conditions", "")
            metrics.wind_dir_text = self.physics.wind_direction_text(
                metrics.wind_dir_deg
            )

            # Real Feel calculate karo
            if metrics.current_temp and metrics.wind_speed and metrics.humidity:
                unit = config["unit_group"]

                if unit == "us":  # Fahrenheit (KLGA)
                    if metrics.current_temp <= 50:
                        metrics.real_feel = self.physics.wind_chill_fahrenheit(
                            metrics.current_temp, metrics.wind_speed
                        )
                        metrics.real_feel_type = "Wind Chill"
                    elif metrics.current_temp >= 80:
                        metrics.real_feel = self.physics.heat_index_fahrenheit(
                            metrics.current_temp, metrics.humidity
                        )
                        metrics.real_feel_type = "Heat Index"
                    else:
                        metrics.real_feel = metrics.feels_like
                        metrics.real_feel_type = "Standard"

                else:  # Celsius (VILK)
                    if metrics.current_temp <= 10:
                        metrics.real_feel = self.physics.wind_chill_celsius(
                            metrics.current_temp, metrics.wind_speed
                        )
                        metrics.real_feel_type = "Wind Chill"
                    elif metrics.current_temp >= 27:
                        metrics.real_feel = self.physics.heat_index_celsius(
                            metrics.current_temp, metrics.humidity
                        )
                        metrics.real_feel_type = "Heat Index"
                    else:
                        metrics.real_feel = metrics.feels_like
                        metrics.real_feel_type = "Standard"

        # ── Forecast Data ───────────────────────────
        if forecast_raw and "days" in forecast_raw:
            for day in forecast_raw["days"]:
                metrics.forecast_highs.append(day.get("tempmax"))
                metrics.forecast_lows.append(day.get("tempmin"))
                metrics.forecast_dates.append(day.get("datetime", ""))
                metrics.forecast_conditions.append(
                    day.get("conditions", "N/A")
                )
                metrics.forecast_humidity.append(
                    day.get("humidity", 0)
                )
                metrics.forecast_wind.append(
                    day.get("windspeed", 0)
                )
                metrics.forecast_cloudcover.append(
                    day.get("cloudcover", 0)
                )

        # ── Historical Analysis ─────────────────────
        if historical_raw:
            valid_temps = [
                r["tempmax"] for r in historical_raw
                if r.get("tempmax") is not None
            ]
            if valid_temps:
                metrics.historical_avg_high  = round(
                    sum(valid_temps) / len(valid_temps), 1
                )
                metrics.historical_max_high  = max(valid_temps)
                metrics.historical_min_high  = min(valid_temps)
                metrics.historical_records   = historical_raw

                # Anomaly score
                if metrics.today_high and metrics.historical_avg_high:
                    metrics.anomaly_score = round(
                        ((metrics.today_high - metrics.historical_avg_high)
                         / metrics.historical_avg_high) * 100,
                        1
                    )

        return metrics


# ─────────────────────────────────────────────────
#          TRADING SIGNAL ENGINE
# ─────────────────────────────────────────────────

class TradingSignalEngine:
    """
    Weather metrics se Polymarket trading signals generate karo.
    Score-based system: -100 (Strong Avoid) to +100 (Strong Buy).
    """

    def __init__(self):
        self.physics = WeatherPhysics()

    def analyze(
        self,
        metrics: WeatherMetrics,
        trade_config: dict,
        station_id: str
    ) -> TradingAnalysis:
        """
        Complete trading analysis generate karo.
        Multiple factors ka weighted score calculate karo.
        """

        threshold_low  = trade_config["threshold_low"]
        threshold_high = trade_config["threshold_high"]
        threshold_mid  = (threshold_low + threshold_high) / 2
        alert_zone     = trade_config["alert_zone"]
        month          = datetime.now().month

        score = 0.0
        bullish_factors = []
        bearish_factors = []
        weather_effects = []
        confidence_factors = []

        # ══════════════════════════════════════════
        # FACTOR 1: Current T-Max vs Threshold
        # Weight: 30 points
        # ══════════════════════════════════════════
        if metrics.today_high is not None:
            confidence_factors.append(1.0)
            diff = metrics.today_high - threshold_mid

            if diff >= (threshold_high - threshold_mid):
                score += 30
                bullish_factors.append(
                    f"Today's High ({metrics.today_high}{metrics.temp_unit}) "
                    f"exceeds threshold HIGH ({threshold_high}{metrics.temp_unit}) "
                    f"by {abs(diff - (threshold_high-threshold_mid)):.1f}° ✅"
                )
            elif diff > 0:
                score += (diff / (threshold_high - threshold_mid)) * 30
                bullish_factors.append(
                    f"Today's High ({metrics.today_high}{metrics.temp_unit}) "
                    f"above midpoint, approaching threshold ↗"
                )
            elif diff > -(threshold_mid - threshold_low):
                score -= (abs(diff) / (threshold_mid - threshold_low)) * 20
                bearish_factors.append(
                    f"Today's High ({metrics.today_high}{metrics.temp_unit}) "
                    f"below threshold midpoint ↘"
                )
            else:
                score -= 25
                bearish_factors.append(
                    f"Today's High ({metrics.today_high}{metrics.temp_unit}) "
                    f"significantly below threshold ({threshold_low}{metrics.temp_unit}) ❌"
                )

        # ══════════════════════════════════════════
        # FACTOR 2: 3-Day Forecast Analysis
        # Weight: 25 points
        # ══════════════════════════════════════════
        valid_forecast = [
            t for t in metrics.forecast_highs if t is not None
        ]
        if valid_forecast:
            confidence_factors.append(1.0)
            best_forecast = max(valid_forecast)
            avg_forecast  = sum(valid_forecast) / len(valid_forecast)

            if best_forecast >= threshold_high:
                score += 25
                bullish_factors.append(
                    f"Forecast peak ({best_forecast}{metrics.temp_unit}) "
                    f"exceeds upper threshold ✅"
                )
            elif best_forecast >= threshold_mid:
                ratio = (best_forecast - threshold_mid) / (threshold_high - threshold_mid)
                score += ratio * 25
                bullish_factors.append(
                    f"Forecast trending towards threshold "
                    f"({best_forecast}{metrics.temp_unit}) ↗"
                )
            else:
                score -= 20
                bearish_factors.append(
                    f"Forecast peak ({best_forecast}{metrics.temp_unit}) "
                    f"below threshold ❌"
                )
        else:
            confidence_factors.append(0.3)
            best_forecast = None

        # ══════════════════════════════════════════
        # FACTOR 3: Historical Anomaly
        # Weight: 20 points
        # ══════════════════════════════════════════
        if metrics.historical_avg_high is not None:
            confidence_factors.append(1.0)

            # Historical probability
            hist_above = sum(
                1 for r in metrics.historical_records
                if r.get("tempmax", 0) >= threshold_mid
            )
            hist_prob = hist_above / len(metrics.historical_records) if metrics.historical_records else 0

            if hist_prob >= 0.7:
                score += 20
                bullish_factors.append(
                    f"Historical data: {hist_above}/{len(metrics.historical_records)} "
                    f"years above threshold ({hist_prob*100:.0f}% probability) ✅"
                )
            elif hist_prob >= 0.4:
                score += hist_prob * 20
                bullish_factors.append(
                    f"Historical mixed: {hist_prob*100:.0f}% years above threshold ↔"
                )
            else:
                score -= 15
                bearish_factors.append(
                    f"Historical data weak: only {hist_prob*100:.0f}% years "
                    f"above threshold ❌"
                )

            # Anomaly detection
            if metrics.anomaly_score is not None:
                if metrics.anomaly_score > 5:
                    score += 5
                    bullish_factors.append(
                        f"Positive anomaly: +{metrics.anomaly_score}% "
                        f"above historical average 📈"
                    )
                elif metrics.anomaly_score < -5:
                    score -= 5
                    bearish_factors.append(
                        f"Negative anomaly: {metrics.anomaly_score}% "
                        f"below historical average 📉"
                    )
        else:
            confidence_factors.append(0.5)

        # ══════════════════════════════════════════
        # FACTOR 4: Wind Effect Analysis
        # Weight: 10 points
        # ══════════════════════════════════════════
        if metrics.wind_speed is not None:
            confidence_factors.append(1.0)

            unit_str = "mph" if metrics.temp_unit == "°F" else "kph"
            wind_delta, wind_desc = self.physics.wind_cooling_effect(
                metrics.wind_speed, unit_str
            )

            weather_effects.append(f"Wind Effect: {wind_desc}")

            if station_id == "KLGA":
                sea_breeze_analysis = self.physics.klga_sea_breeze_analysis(
                    metrics.wind_dir_deg,
                    metrics.wind_speed,
                    month
                )
                weather_effects.append(sea_breeze_analysis)

                # Sea breeze = bearish
                if "SEA BREEZE ACTIVE" in sea_breeze_analysis:
                    score -= 10
                    bearish_factors.append(
                        f"Sea breeze cooling effect active "
                        f"({metrics.wind_dir_text} winds) ❄️"
                    )
                elif "LAND BREEZE" in sea_breeze_analysis:
                    score += 10
                    bullish_factors.append(
                        f"Land breeze warming effect "
                        f"({metrics.wind_dir_text} winds) 🔥"
                    )

            elif station_id == "VILK":
                vilk_wind = self.physics.vilk_wind_analysis(
                    metrics.wind_dir_deg,
                    metrics.wind_speed,
                    month
                )
                weather_effects.append(vilk_wind)

                if "LOO WINDS" in vilk_wind:
                    score += 15
                    bullish_factors.append(
                        f"Loo winds active ({metrics.wind_dir_text}) - "
                        f"extreme heat likely 🌪️🔥"
                    )
                elif "EASTERLY MOISTURE" in vilk_wind:
                    score -= 10
                    bearish_factors.append(
                        f"Easterly moisture reducing max temp 💧"
                    )

        # ══════════════════════════════════════════
        # FACTOR 5: Humidity & Cloud Cover
        # Weight: 10 points
        # ══════════════════════════════════════════
        if metrics.humidity is not None:
            confidence_factors.append(1.0)
            unit_str = "F" if metrics.temp_unit == "°F" else "C"
            temp_for_hum = metrics.today_high or metrics.current_temp or 0
            hum_delta, hum_desc = self.physics.humidity_effect_on_tmax(
                metrics.humidity, temp_for_hum, unit_str
            )
            weather_effects.append(f"Humidity Effect: {hum_desc}")
            score += hum_delta * 2  # Scaled

        if metrics.cloud_cover is not None:
            confidence_factors.append(0.8)
            cloud_delta, cloud_desc = self.physics.cloud_cover_effect(
                metrics.cloud_cover
            )
            weather_effects.append(f"Cloud Cover Effect: {cloud_desc}")

            if cloud_delta > 0:
                score += 5
                bullish_factors.append(
                    f"Low cloud cover ({metrics.cloud_cover:.0f}%): "
                    f"Good solar heating expected ☀️"
                )
            elif cloud_delta < -1:
                score -= 5
                bearish_factors.append(
                    f"High cloud cover ({metrics.cloud_cover:.0f}%): "
                    f"Reduced heating ☁️"
                )

        # ══════════════════════════════════════════
        # FACTOR 6: Dew Point Depression
        # Weight: 5 points
        # ══════════════════════════════════════════
        if metrics.dew_point is not None and metrics.current_temp is not None:
            confidence_factors.append(0.7)
            dpd = self.physics.dew_point_depression(
                metrics.current_temp, metrics.dew_point
            )

            if dpd > 15:
                score += 5
                bullish_factors.append(
                    f"High dew point depression ({dpd:.1f}°): "
                    f"Very dry air, heating potential high 🌵"
                )
                weather_effects.append(
                    f"Dew Point Depression: {dpd:.1f}° - "
                    f"Dry airmass, max temp unimpeded"
                )
            elif dpd < 5:
                score -= 3
                bearish_factors.append(
                    f"Low dew point depression ({dpd:.1f}°): "
                    f"Moist air, max temp suppressed 💧"
                )

        # ══════════════════════════════════════════
        # FINAL SCORE NORMALIZATION & SIGNAL
        # ══════════════════════════════════════════
        score = max(-100, min(100, score))

        if score >= 70:
            signal = TradeSignal.STRONG_BUY
        elif score >= 35:
            signal = TradeSignal.BUY
        elif score >= -20:
            signal = TradeSignal.NEUTRAL
        elif score >= -50:
            signal = TradeSignal.AVOID
        else:
            signal = TradeSignal.STRONG_AVOID

        # Confidence (0.0 - 1.0)
        confidence = (
            sum(confidence_factors) / len(confidence_factors)
            if confidence_factors else 0.5
        )

        # Alert Level
        if metrics.today_high is not None:
            diff_from_low = metrics.today_high - threshold_low
            diff_from_high = threshold_high - metrics.today_high

            if metrics.today_high >= threshold_high:
                alert_level   = AlertLevel.CRITICAL
                alert_message = (
                    f"🚨 CRITICAL: {metrics.city} T-Max "
                    f"({metrics.today_high}{metrics.temp_unit}) "
                    f"has BREACHED upper threshold "
                    f"({threshold_high}{metrics.temp_unit})!"
                )
            elif diff_from_high <= alert_zone:
                alert_level   = AlertLevel.WARNING
                alert_message = (
                    f"⚠️  WARNING: {metrics.city} T-Max "
                    f"({metrics.today_high}{metrics.temp_unit}) "
                    f"is only {diff_from_high:.1f}° below upper threshold "
                    f"({threshold_high}{metrics.temp_unit})!"
                )
            elif metrics.today_high >= threshold_low:
                alert_level   = AlertLevel.WATCH
                alert_message = (
                    f"👁️  WATCH: {metrics.city} T-Max "
                    f"({metrics.today_high}{metrics.temp_unit}) "
                    f"within threshold range "
                    f"({threshold_low} - {threshold_high}{metrics.temp_unit})"
                )
            else:
                alert_level   = AlertLevel.CLEAR
                alert_message = (
                    f"✅ CLEAR: {metrics.city} T-Max "
                    f"({metrics.today_high}{metrics.temp_unit}) "
                    f"below threshold range"
                )
        else:
            alert_level   = AlertLevel.CLEAR
            alert_message = f"Data pending for {metrics.city}"

        return TradingAnalysis(
            station_id       = station_id,
            city             = metrics.city,
            signal           = signal,
            alert_level      = alert_level,
            confidence       = round(confidence, 2),
            signal_score     = round(score, 1),
            bullish_factors  = bullish_factors,
            bearish_factors  = bearish_factors,
            weather_effects  = weather_effects,
            threshold_low    = threshold_low,
            threshold_high   = threshold_high,
            today_high       = metrics.today_high,
            best_forecast_high = max(valid_forecast) if valid_forecast else None,
            historical_avg   = metrics.historical_avg_high,
            anomaly_pct      = metrics.anomaly_score,
            alert_message    = alert_message,
            temp_unit        = metrics.temp_unit
        )
