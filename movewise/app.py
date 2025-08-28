"""
Streamlit application for MoveWise route planning.

This script defines the user interface and orchestrates the
underlying modules to geocode addresses, compute routes, optimise
visits, build a schedule, display an interactive map, and send the
itinerary via LINE. Authentication is implemented using a simple
email check against a value stored in Streamlit's secrets.

To run this app locally for development, install the requirements
listed in ``requirements.txt`` and execute:

    streamlit run movewise/app.py

In production on Streamlit Cloud the secrets must be set as per
``.streamlit/secrets.toml``.
"""

from __future__ import annotations

import datetime
from typing import List, Optional

import streamlit as st
from streamlit_folium import folium_static

import os
import sys
# Ensure the package modules can be imported when run as a script. When the app is executed
# as a standalone script (e.g., via `streamlit run movewise/app.py`), Python may not
# automatically add the package directories to `sys.path`. Add both the current
# directory and its parent to the module search path so that `movewise` and its
# submodules can be imported correctly.
current_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(current_dir)
if current_dir not in sys.path:
    sys.path.append(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from movewise.geocode import geocode_address
from movewise.routing import compute_distance_matrix, total_toll_cost
from movewise.optimisation import nearest_neighbor, two_opt
from movewise.schedule import schedule_route
from movewise.visualisation import create_folium_map

# pandas is no longer used in this version
import requests


def authenticate() -> bool:
    """Authenticate the user using a simple email check.

    The allowed email is retrieved from Streamlit secrets under
    ``ALLOWED_EMAIL``. In production this should be replaced with
    proper Google OAuth as per the specification.
    """
    allowed = st.secrets.get("ALLOWED_EMAIL", "")
    # Initialise the authentication state the first time this function runs.
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    # Only display the login form if the user is not yet authenticated.
    if not st.session_state["authenticated"]:
        st.markdown("### Login")
        email = st.text_input("Enter your email to authenticate:", value="")
        if st.button("Login"):
            # When no allowed email is configured in secrets, permit any non‑empty email.  Otherwise
            # require an exact (case‑insensitive) match with the configured allowed email.  Trim
            # whitespace on both sides to avoid accidental mismatch.
            entered = email.strip()
            allowed_stripped = allowed.strip().lower()
            if (not allowed_stripped and entered) or (entered.lower() == allowed_stripped and entered):
                st.session_state["authenticated"] = True
            else:
                st.error("Access denied. You are not authorised to use this app.")
    # Return the current authentication state so callers can proceed accordingly.
    return st.session_state.get("authenticated", False)


def geocode_addresses(addresses: List[str]) -> Optional[List[tuple]]:
    """Geocode a list of addresses into coordinates.

    Returns ``None`` if any address fails to geocode.
    """
    coords = []
    for addr in addresses:
        res = geocode_address(addr)
        if res is None:
            return None
        coords.append(res)
    return coords


def compute_routes_and_select(
    coords: List[tuple],
    stay_durations: List[int],
    open_hours: List[Optional[tuple]],
    depart_time: str,
    mode_key: str,
    threshold_pct: int,
) -> dict:
    """Compute time- and distance-based routes and select the best based on threshold."""
    # Compute matrices
    dist_matrix, dur_matrix = compute_distance_matrix(coords, mode_key)
    # Build time-minimising route
    time_route = nearest_neighbor(dur_matrix, start=0)
    time_route = two_opt(time_route, dur_matrix)
    # Build distance-minimising route
    dist_route = nearest_neighbor(dist_matrix, start=0)
    dist_route = two_opt(dist_route, dist_matrix)
    # Compute total durations for each route
    def total_duration(route):
        return sum(dur_matrix[route[i]][route[i + 1]] for i in range(len(route) - 1))
    t_time = total_duration(time_route)
    t_dist = total_duration(dist_route)
    # Decide which to choose
    if t_time == 0:
        selected_route = time_route
        criterion = "time"
    else:
        diff_pct = abs(t_time - t_dist) / t_time * 100.0
        if diff_pct <= threshold_pct:
            selected_route = dist_route
            criterion = "distance"
        else:
            selected_route = time_route
            criterion = "time"
    # Build schedule using durations
    schedule = schedule_route(selected_route, dur_matrix, stay_durations, open_hours, depart_time)
    return {
        "route": selected_route,
        "schedule": schedule,
        "criterion": criterion,
        "total_duration_s": total_duration(selected_route),
        "dist_matrix": dist_matrix,
        "dur_matrix": dur_matrix,
    }


def format_schedule_text(schedule, names, total_duration_s, toll_cost) -> str:
    """Format itinerary text for display or messaging."""
    lines = ["Your itinerary:\n"]
    for i, stop in enumerate(schedule, start=1):
        name = names[stop.index] if stop.index < len(names) else f"Stop {stop.index+1}"
        arr = stop.arrival.strftime("%H:%M")
        dep = stop.departure.strftime("%H:%M")
        status = stop.status
        status_text = "" if status == "ok" else f" ({status})"
        lines.append(f"{i}. {name}: arrive {arr}, depart {dep}{status_text}")
    total_h = int(total_duration_s // 3600)
    total_m = int((total_duration_s % 3600) // 60)
    lines.append(f"\nTotal travel time: {total_h}h {total_m}m")
    if toll_cost > 0:
        lines.append(f"Total toll cost: ¥{int(toll_cost)}")
    return "\n".join(lines)


def send_line_message(user_id: str, message: str) -> bool:
    """Send a text message via LINE Messaging API.

    The channel access token and secret must be provided via secrets. The
    user_id should be the target LINE user ID (recipient). This
    function returns True if the API request succeeds.
    """
    access_token = st.secrets.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not access_token:
        st.error("LINE access token not configured in secrets.")
        return False
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message,
            }
        ],
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def main():
    st.set_page_config(page_title="MoveWise", layout="wide")
    st.title("🚶 MoveWise Route Planner")
    # Authentication
    if not authenticate():
        st.stop()
    st.success("Logged in successfully.")
    # Input form
    with st.form("route_form"):
        st.subheader("Route parameters")
        n_places = st.number_input("Number of locations", min_value=2, max_value=20, value=3, step=1)
        names: List[str] = []
        addresses: List[str] = []
        stay_durations: List[int] = []
        open_hours: List[Optional[tuple]] = []
        for i in range(int(n_places)):
            st.markdown(f"#### Location {i+1}")
            name = st.text_input(f"Name", key=f"name_{i}")
            addr = st.text_input(f"Address", key=f"addr_{i}")
            stay = st.number_input("Stay duration (minutes)", min_value=0, max_value=600, value=30, key=f"stay_{i}")
            open_from = st.text_input("Open from (HH:MM)", value="", key=f"open_from_{i}")
            open_to = st.text_input("Open to (HH:MM)", value="", key=f"open_to_{i}")
            names.append(name)
            addresses.append(addr)
            stay_durations.append(int(stay))
            if open_from.strip() and open_to.strip():
                open_hours.append((open_from.strip(), open_to.strip()))
            else:
                open_hours.append(None)
        depart_time = st.text_input("Departure time (HH:MM)", value="09:00")
        mode = st.selectbox(
            "Mode of transport",
            ["Walk", "Car (no tolls)", "Car (use tolls)", "Car (some tolls)", "Public Transport"],
        )
        threshold = st.slider("Force distance minimisation if travel time difference is within (%)", min_value=0, max_value=50, value=10)
        user_line_id = st.text_input("Your LINE user ID (optional)", value="", help="If provided, the itinerary will be sent via LINE when generated.")
        generate = st.form_submit_button("Generate Plan")

    if generate:
        with st.spinner("Geocoding addresses..."):
            coords = geocode_addresses(addresses)
        if coords is None:
            st.error("One or more addresses could not be geocoded. Please check your inputs.")
            st.stop()
        # Determine mode key
        if mode.startswith("Walk"):
            mode_key = "walk"
        elif mode.startswith("Car"):
            mode_key = "drive"
        else:
            mode_key = "transit"
        with st.spinner("Computing routes and schedule..."):
            result = compute_routes_and_select(coords, stay_durations, open_hours, depart_time, mode_key, threshold)
        route = result["route"]
        schedule = result["schedule"]
        criterion = result["criterion"]
        total_duration_s = result["total_duration_s"]
        dist_matrix = result["dist_matrix"]
        dur_matrix = result["dur_matrix"]
        # Compute toll cost if car
        toll_cost = 0.0
        if mode_key == "drive" and "no tolls" not in mode.lower():
            toll_cost = total_toll_cost(route, coords)
        # Display summary
        st.success(f"Optimised by {criterion}. Total travel time: {int(total_duration_s//3600)}h {int((total_duration_s%3600)//60)}m")
        if toll_cost > 0:
            st.info(f"Estimated toll cost: ¥{int(toll_cost)}")
        # Display schedule table
        table_data = []
        for i, stop in enumerate(schedule, start=1):
            name = names[stop.index] if stop.index < len(names) else f"Stop {stop.index+1}"
            row = {
                "Order": i,
                "Name": name,
                "Arrival": stop.arrival.strftime("%H:%M"),
                "Departure": stop.departure.strftime("%H:%M"),
                "Status": stop.status,
            }
            table_data.append(row)
        # Display schedule as a table directly; pandas is no longer required.
        st.table(table_data)
        # Display map
        fol_map = create_folium_map(route, coords, names)
        folium_static(fol_map, width=700, height=500)
        # Itinerary text
        itinerary_text = format_schedule_text(schedule, names, total_duration_s, toll_cost)
        st.text_area("Itinerary", itinerary_text, height=200)
        # Send via LINE
        if user_line_id.strip():
            if send_line_message(user_line_id.strip(), itinerary_text):
                st.success("Itinerary sent via LINE successfully.")
            else:
                st.error("Failed to send itinerary via LINE. Check your LINE credentials and user ID.")


if __name__ == "__main__":
    main()