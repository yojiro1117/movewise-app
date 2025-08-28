"""
Geocoding utilities for MoveWise.

This module provides a thin wrapper around the `geopy` library to
convert free‑form addresses into geographic coordinates. It uses
OpenStreetMap's Nominatim service via geopy's API. A small cache is
maintained in memory to avoid repeated queries for the same address.

Example usage:

    from movewise.geocode import geocode_address
    lat, lon = geocode_address("Tokyo Tower")

The geocode function returns ``None`` if the address cannot be
geocoded.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Tuple

try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderServiceError
except ImportError:
    Nominatim = None  # type: ignore

_geocoder: Optional[Nominatim] = None

def _get_geocoder() -> Nominatim:
    """Return a singleton Nominatim geocoder instance."""
    global _geocoder
    if _geocoder is None:
        if Nominatim is None:
            raise RuntimeError(
                "geopy is required for geocoding. Please install it via pip install geopy."
            )
        # Provide a custom user agent to comply with Nominatim's usage policy.
        _geocoder = Nominatim(user_agent="movewise_app")
    return _geocoder


@lru_cache(maxsize=128)
def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """Geocode an address and return (latitude, longitude) or ``None``.

    To reduce API calls, results are cached in memory. If a timeout
    occurs, the request is retried once. Errors are swallowed and
    ``None`` is returned.

    Args:
        address: Free form text to geocode.

    Returns:
        A tuple of (lat, lon) if geocoding succeeds, otherwise ``None``.
    """
    geocoder = _get_geocoder()
    try:
        location = geocoder.geocode(address, timeout=10)
        if location:
            return location.latitude, location.longitude
    except (GeocoderTimedOut, GeocoderServiceError):
        # retry once
        try:
            location = geocoder.geocode(address, timeout=20)
            if location:
                return location.latitude, location.longitude
        except Exception:
            return None
    except Exception:
        return None
    return None
