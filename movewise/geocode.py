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

import requests


@lru_cache(maxsize=128)
def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """Geocode an address using the OpenStreetMap Nominatim API.

    This function sends a GET request to the public Nominatim service to
    convert a free‑form address into geographic coordinates. Results are
    cached in memory to avoid repeated network calls for the same query.

    Args:
        address: A free‑form location description to geocode.

    Returns:
        A tuple ``(latitude, longitude)`` if the geocoding succeeds, or
        ``None`` if no result is found or an error occurs.
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address, "format": "json", "limit": 1}
    headers = {"User-Agent": "movewise_app"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data:
            try:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                return lat, lon
            except (KeyError, ValueError, TypeError):
                return None
    except Exception:
        return None
    return None