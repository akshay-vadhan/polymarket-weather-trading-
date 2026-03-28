"""
╔═══════════════════════════════════════════════════════════════╗
║  Weather Data Fetcher - Visual Crossing API                   ║
║  Stations: VILK (Lucknow) & KLGA (New York)                   ║
╚═══════════════════════════════════════════════════════════════╝
"""

import os
import json
import time
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────
#              CONSTANTS
# ─────────────────────────────────────────────────

API_BASE_URL = (
    "https://weather.visualcrossing.com"
    "/VisualCrossingWebServices/rest/services/timeline"
)

# Visual Crossing elements jo humein chahiye
REQUIRED_ELEMENTS = (
    "datetime,tempmax,tempmin,temp,feelslike,"
    "humidity,dew,windspeed,winddir,windgust,"
    "cloudcover,conditions,icon,precipprob,"
    "pressure,visibility,uvindex,moonphase,"
    "sunrise,sunset,solarradiation"
)

CACHE_FILE = Path("data/historical_cache.json")
CACHE_EXPIRY_HOURS = 6  # Cache expiry time


# ─────────────────────────────────────────────────
#              CACHE MANAGER
# ─────────────────────────────────────────────────

class CacheManager:
    """
    API calls bachane ke liye local JSON cache.
    GitHub Actions mein har run fresh data lega.
    Local runs mein cache use hoga.
    """

    def __init__(self, cache_file: Path = CACHE_FILE):
        self.cache_file = cache_file
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Any] = self._load_cache()

    def _load_cache(self) -> dict:
        """Cache file se data load karo"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                logger.warning("Cache corrupt, naya cache bana raha hai...")
                return {}
        return {}

    def _save_cache(self):
        """Cache file mein data save karo"""
        try:
            with open(self.cache_file, "w") as f:
                json.dump(self._cache, f, indent=2)
        except IOError as e:
            logger.error(f"Cache save failed: {e}")

    def _make_key(self, station: str, data_type: str, date: str = "") -> str:
        """Unique cache key generate karo"""
        raw = f"{station}_{data_type}_{date}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def get(self, station: str, data_type: str, date: str = "") -> Optional[dict]:
        """Cache se data lo (agar expire nahi hua)"""
        key = self._make_key(station, data_type, date)
        entry = self._cache.get(key)

        if not entry:
            return None

        cached_time = datetime.fromisoformat(entry["timestamp"])
        if datetime.now() - cached_time > timedelta(hours=CACHE_EXPIRY_HOURS):
            logger.debug(f"Cache expired for {station}/{data_type}")
            return None

        logger.debug(f"Cache hit: {station}/{data_type}")
        return entry["data"]

    def set(self, station: str, data_type: str,
            data: dict, date: str = ""):
        """Cache mein data store karo"""
        key = self._make_key(station, data_type, date)
        self._cache[key] = {
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        self._save_cache()


# ─────────────────────────────────────────────────
#              WEATHER API CLIENT
# ─────────────────────────────────────────────────

class WeatherAPIClient:
    """
    Visual Crossing Weather API wrapper.
    VILK aur KLGA dono ke liye station-specific data fetch karta hai.
    """

    def __init__(self):
        self.api_key = os.getenv("VISUAL_CROSSING_API_KEY", "")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "PolymarketWeatherTrader/2.0"
        })
        self.cache = CacheManager()

        if not self.api_key or self.api_key == "your_api_key_here":
            raise ValueError(
                "❌ VISUAL_CROSSING_API_KEY environment variable set nahi hai!\n"
                "   https://www.visualcrossing.com/sign-up par free account banao."
            )

    # ── Low-level request ─────────────────────────

    def _request(
        self,
        station: str,
        date_from: str,
        date_to: Optional[str] = None,
        unit_group: str = "metric",
        include: str = "days,hours,current"
    ) -> Optional[dict]:
        """
        Core API request method.
        Retry logic aur detailed error handling ke saath.
        """
        endpoint_parts = [API_BASE_URL, station, date_from]
        if date_to:
            endpoint_parts.append(date_to)

        endpoint = "/".join(endpoint_parts)

        params = {
            "key": self.api_key,
            "unitGroup": unit_group,
            "elements": REQUIRED_ELEMENTS,
            "include": include,
            "contentType": "json",
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"API Request [{attempt+1}/{max_retries}]: "
                    f"{station} | {date_from}"
                    + (f" to {date_to}" if date_to else "")
                )
                resp = self.session.get(endpoint, params=params, timeout=20)

                # HTTP errors handle karo
                if resp.status_code == 401:
                    raise ValueError(
                        "Invalid API Key! .env file check karo."
                    )
                if resp.status_code == 429:
                    wait_time = 60 * (attempt + 1)
                    logger.warning(
                        f"Rate limit! {wait_time}s wait kar raha hai..."
                    )
                    time.sleep(wait_time)
                    continue
                if resp.status_code == 400:
                    logger.error(
                        f"Bad request - Station '{station}' check karo."
                    )
                    return None

                resp.raise_for_status()
                data = resp.json()
                logger.info(
                    f"✅ Data received: {station} | "
                    f"{len(data.get('days', []))} days"
                )
                return data

            except requests.exceptions.ConnectionError:
                logger.error(
                    f"Network error (attempt {attempt+1}). "
                    "Internet connection check karo."
                )
                if attempt < max_retries - 1:
                    time.sleep(5)
            except requests.exceptions.Timeout:
                logger.error(f"Timeout (attempt {attempt+1}). Retry...")
                if attempt < max_retries - 1:
                    time.sleep(10)
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP Error: {e}")
                return None
            except json.JSONDecodeError:
                logger.error("Invalid JSON response")
                return None

        logger.error(f"Sab retries fail - {station} ke liye data nahi mila")
        return None

    # ── Public Data Methods ────────────────────────

    def get_current_and_today(
        self, station: str, unit_group: str
    ) -> Optional[dict]:
        """Live current conditions + aaj ka data"""
        cached = self.cache.get(station, "current")
        if cached:
            return cached

        data = self._request(
            station=station,
            date_from="today",
            unit_group=unit_group,
            include="days,hours,current"
        )

        if data:
            self.cache.set(station, "current", data)
        return data

    def get_forecast(
        self, station: str, unit_group: str, days: int = 3
    ) -> Optional[dict]:
        """Agle N dinon ka forecast"""
        cached = self.cache.get(station, f"forecast_{days}d")
        if cached:
            return cached

        today = datetime.now()
        end_date = today + timedelta(days=days)

        data = self._request(
            station=station,
            date_from=today.strftime("%Y-%m-%d"),
            date_to=end_date.strftime("%Y-%m-%d"),
            unit_group=unit_group,
            include="days,hours"
        )

        if data:
            self.cache.set(station, f"forecast_{days}d", data)
        return data

    def get_historical_same_date(
        self,
        station: str,
        unit_group: str,
        target_month: int,
        target_day: int,
        years_back: int = 5
    ) -> List[dict]:
        """
        Past N years ke same date ka historical data.
        Anomaly detection ke liye use hoga.
        """
        current_year = datetime.now().year
        records = []

        for year in range(current_year - years_back, current_year):
            date_str = f"{year}-{target_month:02d}-{target_day:02d}"

            # Skip future dates
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                if date_obj > datetime.now():
                    continue
            except ValueError:
                continue

            cached = self.cache.get(station, "historical", date_str)
            if cached:
                records.append(cached)
                continue

            data = self._request(
                station=station,
                date_from=date_str,
                unit_group=unit_group,
                include="days"
            )

            if data and data.get("days"):
                day_data = data["days"][0]
                record = {
                    "year": year,
                    "date": date_str,
                    "tempmax": day_data.get("tempmax"),
                    "tempmin": day_data.get("tempmin"),
                    "humidity": day_data.get("humidity"),
                    "windspeed": day_data.get("windspeed"),
                    "winddir": day_data.get("winddir"),
                    "cloudcover": day_data.get("cloudcover"),
                    "dew": day_data.get("dew"),
                    "conditions": day_data.get("conditions", "N/A"),
                    "precipprob": day_data.get("precipprob", 0)
                }
                self.cache.set(station, "historical", record, date_str)
                records.append(record)

            time.sleep(0.4)  # Rate limiting

        return records

    def get_multi_station_data(
        self, stations_config: dict
    ) -> Dict[str, dict]:
        """
        Saare stations ka data ek saath fetch karo.
        Returns structured dict keyed by station ID.
        """
        results = {}

        for station_id, config in stations_config.items():
            logger.info(
                f"\n{'─'*50}\n"
                f"Fetching: {config['name']}\n"
                f"{'─'*50}"
            )
            unit_group = config["unit_group"]

            current_data = self.get_current_and_today(station_id, unit_group)
            forecast_data = self.get_forecast(station_id, unit_group, days=3)

            # Resolution date se target month/day nikalo
            res_date = datetime.strptime(
                config.get("polymarket_resolution_date", "2026-03-28"),
                "%Y-%m-%d"
            )
            historical_data = self.get_historical_same_date(
                station=station_id,
                unit_group=unit_group,
                target_month=res_date.month,
                target_day=res_date.day,
                years_back=5
            )

            results[station_id] = {
                "config": config,
                "current": current_data,
                "forecast": forecast_data,
                "historical": historical_data,
                "fetch_time": datetime.now().isoformat()
            }

            time.sleep(0.5)  # Between stations

        return results
