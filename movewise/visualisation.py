"""
Map visualisation utilities for MoveWise.

This module provides a helper function to build an interactive map
using the Folium library. It renders numbered markers for each stop
in the tour and draws the route as a polyline. The map can be
embedded directly in a Streamlit app via ``streamlit_folium``.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

import folium


def create_folium_map(
    route: Sequence[int],
    coords: Sequence[Tuple[float, float]],
    names: Sequence[str],
) -> folium.Map:
    """Create a Folium map with numbered markers and a polyline for the route.

    Args:
        route: Visiting order as list of indices.
        coords: List of (lat, lon) coordinates corresponding to indices.
        names: Names or labels for each location.

    Returns:
        A Folium Map object ready for display.
    """
    if not coords:
        return folium.Map(location=[0, 0], zoom_start=2)
    # Compute map centre as the mean of all coordinates
    avg_lat = sum(lat for lat, _ in coords) / len(coords)
    avg_lon = sum(lon for _, lon in coords) / len(coords)
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=12, tiles="OpenStreetMap")
    # Add markers
    for order, idx in enumerate(route, start=1):
        lat, lon = coords[idx]
        label = names[idx] if idx < len(names) else f"Stop {idx}"
        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(f"{order}. {label}", parse_html=True),
            icon=folium.DivIcon(html=f"<div style='font-size: 12px; color: white; background-color: #007bff; border-radius: 50%; width: 24px; height: 24px; text-align: center; line-height: 24px;'>{order}</div>")
        ).add_to(m)
    # Draw polyline for route
    poly_coords = [[coords[idx][0], coords[idx][1]] for idx in route]
    folium.PolyLine(poly_coords, color="blue", weight=4, opacity=0.6).add_to(m)
    return m
