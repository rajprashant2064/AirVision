"""
AirVision - API Provider Configuration

Supported providers:
1. Open-Meteo: No API key required.
2. OpenWeather: API key required.

API keys are stored locally in backend/provider_config.json.
Never expose this file publicly or commit it to Git.
"""

import json
import os
from pathlib import Path

import requests


# ---------------------------------------------------------
# FILE CONFIGURATION
# ---------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BACKEND_DIR / "provider_config.json"

SUPPORTED_PROVIDERS = {
    "open_meteo": {
        "name": "Open-Meteo",
        "requires_key": False,
    },
    "openweather": {
        "name": "OpenWeather",
        "requires_key": True,
    },
}

DEFAULT_CONFIG = {
    "provider": "open_meteo",
    "openweather_api_key": "",
}


# ---------------------------------------------------------
# CONFIGURATION STORAGE
# ---------------------------------------------------------

def load_config():
    """Load saved provider settings from the local JSON file."""

    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as file:
            saved = json.load(file)

        return {
            "provider": saved.get("provider", "open_meteo"),
            "openweather_api_key": saved.get(
                "openweather_api_key", ""
            ),
        }

    except (OSError, json.JSONDecodeError):
        return DEFAULT_CONFIG.copy()


def save_config(provider, api_key=None):
    """Validate and save provider settings."""

    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError("Unsupported API provider.")

    current = load_config()

    # Preserve the existing key if no replacement was supplied.
    if api_key is None:
        api_key = current.get("openweather_api_key", "")

    api_key = api_key.strip()

    if provider == "openweather" and not api_key:
        if not current.get("openweather_api_key"):
            raise ValueError(
                "Enter an OpenWeather API key before selecting "
                "OpenWeather."
            )

        api_key = current["openweather_api_key"]

    updated = {
        "provider": provider,
        "openweather_api_key": api_key,
    }

    # Write the file locally. Do not return the full key to the UI.
    temporary_file = CONFIG_FILE.with_suffix(".tmp")

    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(updated, file, indent=4)

    os.replace(temporary_file, CONFIG_FILE)

    return get_public_config()


def get_public_config():
    """Return safe configuration details without exposing the key."""

    config = load_config()
    key = config.get("openweather_api_key", "")

    return {
        "provider": config["provider"],
        "provider_name": SUPPORTED_PROVIDERS[
            config["provider"]
        ]["name"],
        "requires_key": SUPPORTED_PROVIDERS[
            config["provider"]
        ]["requires_key"],
        "key_configured": bool(key),
        "masked_key": (
            f"••••••{key[-4:]}" if key else ""
        ),
    }


# ---------------------------------------------------------
# PROVIDER CONNECTION TESTS
# ---------------------------------------------------------

def test_provider(provider, api_key=None):
    """
    Test a provider with a real API request.

    Returns a success message or a safe error message.
    API keys are never included in the returned result.
    """

    if provider not in SUPPORTED_PROVIDERS:
        return {
            "success": False,
            "message": "Unsupported provider.",
        }

    config = load_config()

    if api_key is None:
        api_key = config.get("openweather_api_key", "")

    if provider == "open_meteo":
        url = "https://air-quality-api.open-meteo.com/v1/air-quality"

        params = {
            "latitude": 28.6139,
            "longitude": 77.2090,
            "current": "pm2_5,pm10,nitrogen_dioxide",
        }

    else:
        if not api_key:
            return {
                "success": False,
                "message": "Enter an OpenWeather API key first.",
            }

        url = "https://api.openweathermap.org/data/2.5/weather"

        params = {
            "lat": 28.6139,
            "lon": 77.2090,
            "appid": api_key,
            "units": "metric",
        }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=15,
        )

        if response.ok:
            return {
                "success": True,
                "message": (
                    f"{SUPPORTED_PROVIDERS[provider]['name']} "
                    "connection successful."
                ),
            }

        if provider == "openweather" and response.status_code == 401:
            message = (
                "OpenWeather rejected the API key. Check that it is "
                "correct and activated."
            )
        elif response.status_code == 429:
            message = (
                "The provider rate limit was reached. Try again later."
            )
        else:
            message = (
                f"Provider returned HTTP {response.status_code}. "
                "Check provider availability and account access."
            )

        return {
            "success": False,
            "message": message,
        }

    except requests.Timeout:
        return {
            "success": False,
            "message": "Connection timed out. Try again.",
        }

    except requests.RequestException:
        return {
            "success": False,
            "message": "Could not connect to the provider.",
        }
