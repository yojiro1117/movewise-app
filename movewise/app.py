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
    """
    Compute time‑ and distance‑based routes and select the best based on a threshold.

    This helper computes distance and duration matrices using a single travel mode
    (walk or drive). It then applies nearest‑neighbour and 2‑opt heuristics to
    generate two candidate routes: one optimised for travel time and one for
    travel distance. If the difference between these candidates is within
    ``threshold_pct`` percent, the distance‑optimised route is selected;
    otherwise the time‑optimised route is chosen. A schedule is then created
    using the selected route and duration matrix.

    Args:
        coords: List of (lat, lon) coordinates, including the start location.
        stay_durations: List of stay durations in minutes for each stop (start
            location should have duration 0).
        open_hours: List of optional (open_from, open_to) tuples as strings
            ("HH:MM"). ``None`` indicates no opening hours for that stop.
        depart_time: Departure time from the start location as an "HH:MM" string.
        mode_key: Travel mode key used for all legs ("walk" or "drive").
        threshold_pct: Percentage threshold for selecting the distance‑optimised
            route when its total duration differs only slightly from the time‑
            optimised route.

    Returns:
        A dictionary containing the selected route, generated schedule, chosen
        optimisation criterion ("time" or "distance"), total travel duration
        in seconds and the distance/duration matrices used.
    """
    # Compute matrices for the single mode
    dist_matrix, dur_matrix = compute_distance_matrix(coords, mode_key)
    # Build time‑minimising route and improve with 2‑opt
    time_route = nearest_neighbor(dur_matrix, start=0)
    time_route = two_opt(time_route, dur_matrix)
    # Build distance‑minimising route and improve
    dist_route = nearest_neighbor(dist_matrix, start=0)
    dist_route = two_opt(dist_route, dist_matrix)

    # Helper to compute total travel duration for a given route
    def total_duration(route):
        return sum(dur_matrix[route[i]][route[i + 1]] for i in range(len(route) - 1))

    t_time = total_duration(time_route)
    t_dist = total_duration(dist_route)
    # Decide which route to choose based on the threshold
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
    # Build schedule using the duration matrix and chosen route
    schedule = schedule_route(selected_route, dur_matrix, stay_durations, open_hours, depart_time)
    return {
        "route": selected_route,
        "schedule": schedule,
        "criterion": criterion,
        "total_duration_s": total_duration(selected_route),
        "dist_matrix": dist_matrix,
        "dur_matrix": dur_matrix,
    }


def compute_sequential_schedule(
    coords: List[tuple],
    stay_durations: List[int],
    open_hours: List[Optional[tuple]],
    depart_time_str: str,
    modes_selected: List[str],
) -> dict:
    """
    Compute a schedule for a fixed sequence of stops using individual modes per leg.

    When different transport modes are selected for each leg, the route order is
    taken as provided (start, stop1, stop2, ...). For each consecutive pair of
    locations, the travel time is computed using the corresponding mode. The
    arrival and departure times are then calculated sequentially from the
    initial departure time and stay durations. Opening hours are respected when
    provided: if arrival occurs before the opening time, the status of that stop
    will be "早すぎ"; if arrival occurs after the closing time it will be
    "営業時間外". Otherwise the status is "ok". Stay durations are applied
    regardless of status.

    Args:
        coords: List of (lat, lon) coordinates, including the start location at
            index 0 and subsequent stops in order.
        stay_durations: Stay durations in minutes for each location. The start
            location should have a stay duration of 0.
        open_hours: List of optional (open_from, open_to) tuples for each stop
            (excluding the start) or None when no hours are defined.
        depart_time_str: Starting departure time as an "HH:MM" string.
        modes_selected: List of transport mode labels for each leg. The length
            should be equal to ``len(coords) - 1``. Each entry corresponds to
            the leg leading to that stop (start -> stop1, stop1 -> stop2, etc.).

    Returns:
        A dictionary containing the route (a simple sequential list of indices),
        a schedule list with arrival/departure/status for each location, and
        total travel time in seconds.
    """
    from movewise.schedule import Stop
    # Map Japanese mode labels to internal keys
    def mode_to_key(label: str) -> str:
        if label.startswith("徒歩"):
            return "walk"
        elif label.startswith("車"):
            return "drive"
        else:
            return "walk"  # treat public transport as walking for fallback

    # Parse departure time
    depart_dt = datetime.datetime.combine(datetime.date.today(), datetime.datetime.strptime(depart_time_str, "%H:%M").time())
    schedule = []
    # Start location: arrival = depart = depart_dt
    start_stop = Stop(index=0, arrival=depart_dt, departure=depart_dt, status="ok")
    schedule.append(start_stop)
    current_depart = depart_dt
    total_travel_s = 0.0
    for leg_idx in range(1, len(coords)):
        mode_label = modes_selected[leg_idx - 1]
        mode_key = mode_to_key(mode_label)
        # Compute duration for this leg (use 2 points)
        # compute_distance_matrix returns a 2x2 matrix; we take [0][1]
        _, dur_matrix_leg = compute_distance_matrix(coords[leg_idx - 1 : leg_idx + 1], mode_key)
        travel_s = dur_matrix_leg[0][1]
        total_travel_s += travel_s
        # Arrival time
        arrival_dt = current_depart + datetime.timedelta(seconds=travel_s)
        # Determine status based on opening hours of this stop
        status = "ok"
        open_pair = open_hours[leg_idx]
        if open_pair is not None:
            open_from_str, open_to_str = open_pair
            try:
                open_from_dt = datetime.datetime.combine(arrival_dt.date(), datetime.datetime.strptime(open_from_str, "%H:%M").time())
                open_to_dt = datetime.datetime.combine(arrival_dt.date(), datetime.datetime.strptime(open_to_str, "%H:%M").time())
                if arrival_dt < open_from_dt:
                    status = "早すぎ"
                elif arrival_dt > open_to_dt:
                    status = "営業時間外"
            except Exception:
                status = "ok"
        # Departure time from this stop
        stay_minutes = stay_durations[leg_idx]
        departure_dt = arrival_dt + datetime.timedelta(minutes=stay_minutes)
        schedule.append(Stop(index=leg_idx, arrival=arrival_dt, departure=departure_dt, status=status))
        current_depart = departure_dt
    route = list(range(len(coords)))
    return {
        "route": route,
        "schedule": schedule,
        "criterion": "custom",
        "total_duration_s": total_travel_s,
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
        # 入力地点数
        n_places = st.number_input("地点数", min_value=2, max_value=20, value=3, step=1)
        # 各種入力を保持するリスト
        names: List[str] = []
        addresses: List[str] = []
        stay_durations: List[int] = []
        open_hours: List[Optional[tuple]] = []
        modes_selected: List[str] = []  # 各地点に到達するまでの移動手段

        # 出発地点情報と出発時刻を入力
        st.markdown("#### 出発地点")
        start_name = st.text_input("出発地点 名称", key="start_name")
        start_addr = st.text_input(
            "出発地点 住所", key="start_addr", help="住所が不明な場合、名称のみ入力してください"
        )
        # グローバルの出発時刻を出発地点の下に配置
        depart_time = st.text_input("出発時刻 (HH:MM)", value="09:00")
        # 出発地点の名称のみの場合は有名な駅名に変換する
        if not start_addr.strip() and start_name.strip():
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

        # 各目的地の入力
        for i in range(int(n_places)):
            with st.expander(f"地点 {i+1}", expanded=True if int(n_places) <= 3 else False):
                # 名称・住所を同じ行に
                col_name, col_addr = st.columns([1, 3])
                with col_name:
                    name = st.text_input("名称", key=f"name_{i}")
                with col_addr:
                    addr = st.text_input("住所", key=f"addr_{i}")
                # 住所が空欄の場合は名称から推測した候補を使う
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
                # 滞在時間
                stay = st.number_input(
                    "滞在時間（分）", min_value=0, max_value=600, value=30, key=f"stay_{i}"
                )
                # 営業時間（任意）を左右に配置し、ヘルプを表示
                # ユーザーが混乱しないよう、ラベルを具体的に「営業開始時刻」「営業終了時刻」と表現し、ツールチップで目的を説明する。
                col_open_from, col_open_to = st.columns(2)
                with col_open_from:
                    open_from = st.text_input(
                        "営業開始時刻 (HH:MM)",
                        value="",
                        key=f"open_from_{i}",
                        help="その施設の営業開始時刻。到着が営業時間より前の場合はステータスが\"早すぎ\"と表示されます。未入力可"
                    )
                with col_open_to:
                    open_to = st.text_input(
                        "営業終了時刻 (HH:MM)",
                        value="",
                        key=f"open_to_{i}",
                        help="その施設の営業終了時刻。到着が営業時間より後の場合はステータスが\"営業時間外\"と表示されます。未入力可"
                    )
                # この地点までの移動手段選択肢（前の地点からこの地点への移動）
                mode = st.radio(
                    "移動手段（この地点まで）",
                    [
                        "徒歩",
                        "車（有料道路なし）",
                        "車（有料道路使用）",
                        "車（一部有料道路）",
                        "公共交通機関",
                    ],
                    horizontal=True,
                    key=f"mode_{i}",
                )
                names.append(name)
                addresses.append(addr)
                stay_durations.append(int(stay))
                if open_from.strip() and open_to.strip():
                    open_hours.append((open_from.strip(), open_to.strip()))
                else:
                    open_hours.append(None)
                modes_selected.append(mode)

        # 出発地点が指定されていれば先頭に追加
        if start_name.strip() or start_addr.strip():
            names = [start_name] + names
            addresses = [start_addr] + addresses
            stay_durations = [0] + stay_durations
            open_hours = [None] + open_hours
            # 出発地点から最初の地点への移動手段はユーザーが地点1で指定したものを利用
            # modes_selected の先頭は地点1への移動手段として使われる
        # グローバルではなく各地点でモードを選んでいるため、ここでは削除
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
        # Geocode all addresses
        with st.spinner("住所のジオコーディング中…"):
            coords = geocode_addresses(addresses)
            if coords is None:
                st.error("一部の住所がジオコーディングできませんでした。入力を確認してください。")
                st.stop()
        # Determine if all modes are the same
        all_same_mode = len(set(modes_selected)) == 1
        if all_same_mode:
            # Use optimisation heuristics when all selected modes are identical
            # Map the single mode label to an internal key
            first_mode = modes_selected[0] if modes_selected else "徒歩"
            if first_mode.startswith("徒歩"):
                mode_key = "walk"
            elif first_mode.startswith("車"):
                mode_key = "drive"
            else:
                # Public transport fallback uses walking profile
                mode_key = "walk"
            with st.spinner("ルートとスケジュールを計算中…"):
                result = compute_routes_and_select(
                    coords,
                    stay_durations,
                    open_hours,
                    depart_time,
                    mode_key,
                    threshold,
                )
            route = result["route"]
            schedule = result["schedule"]
            criterion = result["criterion"]
            total_duration_s = result["total_duration_s"]
            # Compute toll cost if driving and tolls may apply
            toll_cost = 0.0
            if mode_key == "drive" and ("なし" not in first_mode):
                toll_cost = total_toll_cost(route, coords)
            # Display summary for optimised route
            crit_jp = "距離" if criterion == "distance" else "時間"
            st.success(
                f"{crit_jp}で最適化されました。総移動時間: {int(total_duration_s // 3600)}時間 {int((total_duration_s % 3600) // 60)}分"
            )
            if toll_cost > 0:
                st.info(f"推定有料道路料金: ¥{int(toll_cost)}")
        else:
            # Compute schedule sequentially for multi‑modal legs
            with st.spinner("ルートとスケジュールを計算中…"):
                result = compute_sequential_schedule(
                    coords,
                    stay_durations,
                    open_hours,
                    depart_time,
                    modes_selected,
                )
            route = result["route"]
            schedule = result["schedule"]
            total_duration_s = result["total_duration_s"]
            # For sequential schedule, there is no optimised criterion
            toll_cost = 0.0
            # Compute toll cost only for those legs marked as driving with tolls
            for leg_idx, mode_label in enumerate(modes_selected):
                if mode_label.startswith("車") and ("なし" not in mode_label):
                    # compute toll cost for this leg (placeholder always 0)
                    pass
            st.success(
                f"カスタムルートで計算しました。総移動時間: {int(total_duration_s // 3600)}時間 {int((total_duration_s % 3600) // 60)}分"
            )
        # Display schedule table
        table_data = []
        for i, stop in enumerate(schedule, start=1):
            name = names[stop.index] if stop.index < len(names) else f"Stop {stop.index+1}"
            row = {
                "順番": i,
                "名称": name,
                "到着時刻": stop.arrival.strftime("%H:%M"),
                "出発時刻": stop.departure.strftime("%H:%M"),
                "ステータス": stop.status,
            }
            table_data.append(row)
        st.table(table_data)
        # Display map with the computed route
        fol_map = create_folium_map(route, coords, names)
        folium_static(fol_map, width=700, height=500)
        # Itinerary text (English function still used for consistency)
        itinerary_text = format_schedule_text(schedule, names, total_duration_s, toll_cost)
        st.text_area("行程表", itinerary_text, height=200)
        # Optionally send itinerary via LINE
        if user_line_id.strip():
            if send_line_message(user_line_id.strip(), itinerary_text):
                st.success("行程表をLINEに送信しました。")
            else:
                st.error("行程表のLINE送信に失敗しました。LINEの認証情報とユーザーIDを確認してください。")


if __name__ == "__main__":
    main()