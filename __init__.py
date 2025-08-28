"""
MoveWise package initialization.

This package provides core functionality for the MoveWise route planning
application. Components include geocoding, routing, optimisation,
schedule calculation, and map visualisation.

Modules:
    geocode     – Functions to geocode addresses using Nominatim.
    routing     – Route distance/time matrix generation via OSRM and fallbacks.
    optimisation – Nearest neighbour and 2‑opt heuristics for tour optimisation.
    schedule    – Schedule generation considering stay durations and
                   opening hours.
    visualisation – Folium based map creation utilities.

The code in this package is designed for educational and demonstration
purposes. It does not guarantee perfect accuracy and should not be used
for mission critical tasks without thorough validation.
"""

__all__ = [
    "geocode",
    "routing",
    "optimisation",
    "schedule",
    "visualisation",
]