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
        # ログインフォーム（日本語）
        st.markdown("### ログイン")
        email = st.text_input("認証用メールアドレスを入力してください:", value="")
        if st.button("ログイン"):
            # When no allowed email is configured in secrets, permit any non‑empty email.  Otherwise
            # require an exact (case‑insensitive) match with the configured allowed email.  Trim
            # whitespace on both sides to avoid accidental mismatch.
            entered = email.strip()
            allowed_stripped = allowed.strip().lower()
            if (not allowed_stripped and entered) or (entered.lower() == allowed_stripped and entered):
                st.session_state["authenticated"] = True
            else:
                    st.error("アクセスが拒否されました。このアプリを使用する権限がありません。")
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
    st.title("🚶 MoveWise ルートプランナー")
    # Authentication
    if not authenticate():
        st.stop()
    st.success("ログインに成功しました。")
    # Input form
    with st.form("route_form"):
        st.subheader("ルートパラメータ")
        n_places = st.number_input("地点数", min_value=2, max_value=20, value=3, step=1)
        names: List[str] = []
        addresses: List[str] = []
        stay_durations: List[int] = []
        open_hours: List[Optional[tuple]] = []

        # Add explicit start location fields to allow users to specify a departure point
        st.markdown("#### 出発地点")
        start_name = st.text_input("出発地点 名称", key="start_name")
        start_addr = st.text_input(
            "出発地点 住所", key="start_addr", help="住所が不明な場合、名称のみ入力してください"
        )
        # If only a name is provided for the start, fall back to a more commonly searched address (e.g. station)
        if not start_addr.strip() and start_name.strip():
            # Define simple fallback mappings from place names to well‑known landmarks/stations
            fallback_map = {
                "博多": "博多駅",
                "天神": "天神駅",
                "梅田": "梅田駅",
                "なんば": "難波駅",
                "札幌": "札幌駅",
                "仙台": "仙台駅",
                "京都": "京都駅",
                "大阪": "大阪駅",
                "名古屋": "名古屋駅",
                "東京": "東京駅",
            }
            start_addr = fallback_map.get(start_name.strip(), start_name.strip())

        # Input fields for each stop
        for i in range(int(n_places)):
            # Use an expander for each location to reduce vertical scrolling when many locations are added
            with st.expander(f"地点 {i+1}", expanded=True if int(n_places) <= 3 else False):
                # Place name and address on the same row to reduce vertical scrolling
                col_name, col_addr = st.columns([1, 3])
                with col_name:
                    name = st.text_input("名称", key=f"name_{i}")
                with col_addr:
                    addr = st.text_input("住所", key=f"addr_{i}")
                # If address is left empty but a name is provided, fall back to a commonly searched alternative
                if not addr.strip() and name.strip():
                    fallback_map = {
                        "博多": "博多駅",
                        "天神": "天神駅",
                        "梅田": "梅田駅",
                        "なんば": "難波駅",
                        "札幌": "札幌駅",
                        "仙台": "仙台駅",
                        "京都": "京都駅",
                        "大阪": "大阪駅",
                        "名古屋": "名古屋駅",
                        "東京": "東京駅",
                    }
                    addr = fallback_map.get(name.strip(), name.strip())
                stay = st.number_input(
                    "滞在時間（分）", min_value=0, max_value=600, value=30, key=f"stay_{i}"
                )
                # Opening and closing hours side‑by‑side
                col_open_from, col_open_to = st.columns(2)
                with col_open_from:
                    open_from = st.text_input("開店時刻 (HH:MM)", value="", key=f"open_from_{i}")
                with col_open_to:
                    open_to = st.text_input("閉店時刻 (HH:MM)", value="", key=f"open_to_{i}")
                names.append(name)
                addresses.append(addr)
                stay_durations.append(int(stay))
                if open_from.strip() and open_to.strip():
                    open_hours.append((open_from.strip(), open_to.strip()))
                else:
                    open_hours.append(None)

        # Insert start location at beginning if provided
        if start_name.strip() or start_addr.strip():
            names = [start_name] + names
            addresses = [start_addr] + addresses
            stay_durations = [0] + stay_durations
            open_hours = [None] + open_hours

        depart_time = st.text_input("出発時刻 (HH:MM)", value="09:00")
        # Use a radio button instead of a selectbox to display all transport mode options clearly
        mode = st.radio(
            "移動手段",
            [
                "徒歩",
                "車（有料道路なし）",
                "車（有料道路使用）",
                "車（一部有料道路）",
                "公共交通機関",
            ],
            horizontal=True,
        )
        threshold = st.slider(
            "時間差がこの割合以内なら距離最小化を優先 (%)",
            min_value=0,
            max_value=50,
            value=10,
        )
        user_line_id = st.text_input(
            "LINEユーザーID（任意）", value="", help="入力すると、行程表をLINEに送信します。"
        )
        generate = st.form_submit_button("プランを生成")

    if generate:
        with st.spinner("住所のジオコーディング中…"):
            coords = geocode_addresses(addresses)
            if coords is None:
                st.error("一部の住所がジオコーディングできませんでした。入力を確認してください。")
                st.stop()
        # Determine mode key
            # 移動手段に応じてキーを決定（日本語に対応）
            if mode.startswith("徒歩"):
                mode_key = "walk"
            elif mode.startswith("車"):
                mode_key = "drive"
            else:
                mode_key = "transit"
        with st.spinner("ルートとスケジュールを計算中…"):
            result = compute_routes_and_select(coords, stay_durations, open_hours, depart_time, mode_key, threshold)
        route = result["route"]
        schedule = result["schedule"]
        criterion = result["criterion"]
        total_duration_s = result["total_duration_s"]
        dist_matrix = result["dist_matrix"]
        dur_matrix = result["dur_matrix"]
        # Compute toll cost if car
        toll_cost = 0.0
        # 車の場合に「なし」が含まれていない場合は有料道路料金を計算する
        if mode_key == "drive" and ("なし" not in mode):
            toll_cost = total_toll_cost(route, coords)
        # Display summary
        # 日本語の最適化基準名を組み立て
        crit_jp = "距離" if criterion == "distance" else "時間"
        st.success(f"{crit_jp}で最適化されました。総移動時間: {int(total_duration_s//3600)}時間 {int((total_duration_s%3600)//60)}分")
        if toll_cost > 0:
            st.info(f"推定有料道路料金: ¥{int(toll_cost)}")
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
        st.text_area("行程表", itinerary_text, height=200)
        # Send via LINE
        if user_line_id.strip():
            if send_line_message(user_line_id.strip(), itinerary_text):
                st.success("行程表をLINEに送信しました。")
            else:
                st.error("行程表のLINE送信に失敗しました。LINEの認証情報とユーザーIDを確認してください。")


if __name__ == "__main__":
    main()