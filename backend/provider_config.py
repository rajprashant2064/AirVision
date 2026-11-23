"""AirVision API provider configuration.

Open-Meteo is the default provider and does not require an API key.
For cloud deployment, configure AIRVISION_PROVIDER and OPENWEATHER_API_KEY
as environment variables. Do not store secrets in source code.

Local development can continue using backend/provider_config.json.
On Vercel, the filesystem is not persistent, so provider settings are read
from environment variables and cannot be saved through the dashboard.
"""

import json
import os
from pathlib import Path

import requests


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


def _is_vercel():
    """Return True when running inside a Vercel deployment."""
    return os.getenv("VERCEL", "").lower() == "1"


def load_config():
    """Load provider configuration, preferring cloud environment variables."""
    saved = DEFAULT_CONFIG.copy()

    # Local JSON settings are useful during development.
    if not _is_vercel() and CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
            saved["provider"] = data.get("provider", "open_meteo")
            saved["openweather_api_key"] = data.get("openweather_api_key", "")
        except (OSError, json.JSONDecodeError):
            pass

    # Environment variables take precedence in both local and cloud runs.
    provider = os.getenv("AIRVISION_PROVIDER", "").strip().lower()
    api_key = os.getenv("OPENWEATHER_API_KEY")

    if provider in SUPPORTED_PROVIDERS:
        saved["provider"] = provider
    if api_key is not None:
        saved["openweather_api_key"] = api_key.strip()

    if saved["provider"] not in SUPPORTED_PROVIDERS:
        saved["provider"] = "open_meteo"

    return saved


def save_config(provider, api_key=None):
    """Save provider settings locally; cloud settings must use env variables."""
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError("Unsupported API provider.")

    current = load_config()

    if api_key is None:
        api_key = current.get("openweather_api_key", "")

    if not isinstance(api_key, str):
        raise ValueError("API key must be text.")

    api_key = api_key.strip()

    if provider == "openweather" and not api_key:
        raise ValueError(
            "Enter an OpenWeather API key before selecting OpenWeather."
        )

    if _is_vercel():
        raise ValueError(
            "Provider settings cannot be saved from the dashboard on the cloud. "
            "Set AIRVISION_PROVIDER and OPENWEATHER_API_KEY in Vercel Environment Variables."
