"""
Routing utilities for MoveWise.

This module wraps network calls to OSRM (Open Source Routing Machine)
to produce distance and duration matrices for a set of coordinates. If
OSRM is unavailable or fails for any pair, optional fallbacks include
GraphHopper (not implemented) and simple Haversine estimation with
mode‑specific speed factors. A rudimentary toll calculation based on
the provided toll database can be integrated for driving modes.

Example usage:

    coords = [(35.6586, 139.7454), (35.6895, 139.6917)]
    dist_mat, dur_mat = compute_distance_matrix(coords, mode="drive")

The functions in this module are designed for demonstration purposes
and may be subject to API limits. Use your own OSRM server in
production for reliability.
"""

from __future__ import annotations

import json
import math
from typing import List, Sequence, Tuple, Optional

import requests

EARTH_RADIUS_KM = 6371.0


def haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Compute the great‑circle distance between two coordinates in kilometers."""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def compute_osrm_table(coords: Sequence[Tuple[float, float]], profile: str) -> Optional[Tuple[List[List[float]], List[List[float]]]]:
    """Call OSRM table service to compute distance and duration matrices.

    Args:
        coords: List of (lat, lon) tuples.
        profile: OSRM profile ('driving' or 'foot').

    Returns:
        A tuple (distance_matrix_km, duration_matrix_s) if successful, otherwise ``None``.
    """
    if not coords:
        return None
    # OSRM expects lon,lat order and semicolon separated list
    locs = ";".join([f"{lon},{lat}" for lat, lon in coords])
    url = f"https://router.project-osrm.org/table/v1/{profile}/{locs}?annotations=distance,duration"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            # OSRM returns distances in meters and durations in seconds
            dist_matrix = [[d / 1000.0 if d is not None else float('inf') for d in row] for row in data.get("distances", [])]
            dur_matrix = [[t if t is not None else float('inf') for t in row] for row in data.get("durations", [])]
            return dist_matrix, dur_matrix
    except Exception:
        return None
    return None


def compute_haversine_matrix(coords: Sequence[Tuple[float, float]], speed_kmh: float) -> Tuple[List[List[float]], List[List[float]]]:
    """Compute distance and duration matrices using the Haversine formula.

    Args:
        coords: List of (lat, lon) tuples.
        speed_kmh: Assumed constant travel speed in km/h.

    Returns:
        Tuple of (distance_matrix_km, duration_matrix_s).
    """
    n = len(coords)
    dist_matrix = [[0.0] * n for _ in range(n)]
    dur_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            dist = haversine_distance(coords[i], coords[j])
            dist_matrix[i][j] = dist
            dur_matrix[i][j] = dist / speed_kmh * 3600.0
    return dist_matrix, dur_matrix


def compute_distance_matrix(coords: Sequence[Tuple[float, float]], mode: str) -> Tuple[List[List[float]], List[List[float]]]:
    """Compute distance and duration matrices given a set of coordinates and mode.

    This function attempts to use OSRM for accurate distances and durations.
    If OSRM fails, it falls back to a simple Haversine estimate with
    mode‑specific average speeds. GraphHopper integration could be
    added here as another fallback if desired.

    Args:
        coords: List of (lat, lon) coordinate tuples.
        mode: 'walk' for walking or 'drive' for car.

    Returns:
        Tuple of (distance_matrix_km, duration_matrix_s).
    """
    profile = 'driving' if mode == 'drive' else 'foot'
    matrices = compute_osrm_table(coords, profile)
    if matrices is not None:
        return matrices
    # OSRM failed; fallback to Haversine with speed assumption
    speed = 5.0 if mode == 'walk' else 40.0  # km/h
    return compute_haversine_matrix(coords, speed)


def total_toll_cost(route: Sequence[int], coords: Sequence[Tuple[float, float]], toll_db_path: str = None) -> float:
    """Compute the estimated toll cost for a driving route.

    This is a placeholder implementation. In a real implementation
    ``toll_db_path`` would be an SQLite or CSV file describing each
    expressway segment and its fee. The function would look up the
    segments traversed between two points and sum their fees.

    Args:
        route: Order of indices representing the path.
        coords: List of (lat, lon) coordinates.
        toll_db_path: Path to a toll database (CSV or SQLite). Unused here.

    Returns:
        Estimated total toll cost in JPY.
    """
    # This demo implementation returns 0 for all segments. In your own
    # deployment you should integrate a national toll database as
    # described in the specification.
    return 0.0
