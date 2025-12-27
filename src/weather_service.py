#!/usr/bin/env python3
"""
Weather Service - Fetch weather data from OpenWeatherMap API
Used to pause motion detection during rain
"""

import requests
import time
from datetime import datetime
from typing import Optional, Dict, Any
from .logger import get_logger

logger = get_logger(__name__)


class WeatherService:
    """Service to check weather conditions via OpenWeatherMap API"""

    # Weather condition codes that indicate rain (pause motion detection)
    # https://openweathermap.org/weather-conditions
    # Note: Snow codes (600-622) excluded - snow is OK for bird photos
    RAIN_CODES = {
        # Thunderstorm
        200, 201, 202, 210, 211, 212, 221, 230, 231, 232,
        # Drizzle
        300, 301, 302, 310, 311, 312, 313, 314, 321,
        # Rain
        500, 501, 502, 503, 504, 511, 520, 521, 522, 531,
    }

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize weather service

        Args:
            config: Weather config dict with api_key, latitude, longitude
        """
        self.api_key = config.get('api_key', '')
        self.latitude = config.get('latitude', 0)
        self.longitude = config.get('longitude', 0)
        self.check_interval = config.get('check_interval_minutes', 10) * 60  # Convert to seconds
        self.enabled = config.get('enabled', False)

        self.last_check_time = 0
        self.last_weather_data: Optional[Dict] = None
        self.is_raining = False
        self.weather_description = "Unknown"
        self.temperature = None

        if self.enabled and self.api_key:
            logger.info(f"Weather service initialized - Location: ({self.latitude}, {self.longitude})")
        elif self.enabled:
            logger.warning("Weather service enabled but no API key configured")
        else:
            logger.info("Weather service disabled")

    def should_check_weather(self) -> bool:
        """Check if enough time has passed since last weather check"""
        if not self.enabled or not self.api_key:
            return False
        return time.time() - self.last_check_time >= self.check_interval

    def check_weather(self) -> bool:
        """
        Fetch current weather from OpenWeatherMap API

        Returns:
            True if raining/precipitating, False otherwise
        """
        if not self.enabled or not self.api_key:
            return False

        try:
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {
                'lat': self.latitude,
                'lon': self.longitude,
                'appid': self.api_key,
                'units': 'imperial'  # Fahrenheit
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            self.last_weather_data = data
            self.last_check_time = time.time()

            # Extract weather info
            weather_list = data.get('weather', [])
            if weather_list:
                weather = weather_list[0]
                weather_id = weather.get('id', 0)
                self.weather_description = weather.get('description', 'Unknown').title()

                # Check if weather code indicates rain/precipitation
                self.is_raining = weather_id in self.RAIN_CODES
            else:
                self.is_raining = False
                self.weather_description = "Unknown"

            # Get temperature
            main = data.get('main', {})
            self.temperature = main.get('temp')

            # Log weather status
            rain_status = "RAINING" if self.is_raining else "Clear"
            temp_str = f"{self.temperature:.1f}°F" if self.temperature else "N/A"
            logger.info(f"[WEATHER] {rain_status} - {self.weather_description}, {temp_str}")

            return self.is_raining

        except requests.exceptions.RequestException as e:
            logger.error(f"[WEATHER] API request failed: {e}")
            return self.is_raining  # Return last known state
        except Exception as e:
            logger.error(f"[WEATHER] Error checking weather: {e}")
            return self.is_raining

    def get_status(self) -> Dict[str, Any]:
        """Get current weather status for UI display"""
        return {
            'enabled': self.enabled,
            'is_raining': self.is_raining,
            'description': self.weather_description,
            'temperature': self.temperature,
            'last_check': datetime.fromtimestamp(self.last_check_time).strftime('%H:%M:%S') if self.last_check_time else 'Never',
            'paused': self.is_raining and self.enabled
        }

    def update_config(self, config: Dict[str, Any]):
        """Update weather service configuration"""
        self.api_key = config.get('api_key', self.api_key)
        self.latitude = config.get('latitude', self.latitude)
        self.longitude = config.get('longitude', self.longitude)
        self.check_interval = config.get('check_interval_minutes', 10) * 60
        self.enabled = config.get('enabled', self.enabled)

        if self.enabled:
            logger.info(f"[WEATHER] Config updated - Enabled, checking every {self.check_interval // 60} minutes")
        else:
            logger.info("[WEATHER] Config updated - Disabled")
