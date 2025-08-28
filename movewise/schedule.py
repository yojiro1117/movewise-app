"""
Schedule calculation utilities for MoveWise.

This module constructs a time‑based itinerary given a visiting order,
travel durations, stay durations, and optional opening hours. It
produces arrival times for each stop and flags warnings when arrival
falls outside the specified opening interval.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time
from typing import List, Optional, Sequence, Tuple


@dataclass
class StopSchedule:
    index: int
    arrival: datetime
    departure: datetime
    status: str  # "ok", "warning", "closed"


def parse_time_string(t: str) -> time:
    """Parse a HH:MM formatted time string into a datetime.time object."""
    h, m = map(int, t.strip().split(":"))
    return time(hour=h, minute=m)


def schedule_route(
    route: Sequence[int],
    durations: Sequence[Sequence[float]],
    stay_durations: Sequence[int],
    open_hours: Sequence[Optional[Tuple[str, str]]],
    departure_time_str: str,
    tz_offset: int = 9,
) -> List[StopSchedule]:
    """Generate a schedule for a tour.

    Args:
        route: Visiting order as list of indices.
        durations: Matrix of travel durations (seconds).
        stay_durations: Stay durations at each location (minutes).
        open_hours: Optional list of (open_time, close_time) strings per location
            in HH:MM format. ``None`` indicates no opening hours.
        departure_time_str: Departure time as HH:MM string (local time).
        tz_offset: Offset from UTC in hours (default JST, UTC+9).

    Returns:
        A list of ``StopSchedule`` objects containing arrival time,
        departure time, and a status indicator.
    """
    # Convert departure_time_str to datetime (assumes today). We'll set date to today.
    today = datetime.now().date()
    dep_time = parse_time_string(departure_time_str)
    current_time = datetime.combine(today, dep_time)

    schedule: List[StopSchedule] = []
    for idx, loc_index in enumerate(route):
        arrival_time = current_time
        # Determine status based on opening hours
        status = "ok"
        open_spec = open_hours[loc_index] if loc_index < len(open_hours) else None
        if open_spec:
            open_str, close_str = open_spec
            open_time = parse_time_string(open_str)
            close_time = parse_time_string(close_str)
            # Convert to datetime for comparison (same date)
            open_dt = datetime.combine(today, open_time)
            close_dt = datetime.combine(today, close_time)
            if arrival_time < open_dt:
                status = "warning"
            elif arrival_time > close_dt:
                status = "closed"
            else:
                status = "ok"
        # Departure time = arrival + stay duration
        stay_minutes = stay_durations[loc_index] if loc_index < len(stay_durations) else 0
        departure_time = arrival_time + timedelta(minutes=stay_minutes)
        schedule.append(StopSchedule(index=loc_index, arrival=arrival_time, departure=departure_time, status=status))
        # Compute travel to next location, except for last
        if idx < len(route) - 1:
            next_loc = route[idx + 1]
            travel_seconds = durations[loc_index][next_loc]
            current_time = departure_time + timedelta(seconds=travel_seconds)
    return schedule
