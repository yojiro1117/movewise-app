# MoveWise

MoveWise is an end‑to‑end route planning application built with
Streamlit. It allows a user to input between two and twenty stops
(names/addresses), specify stay durations and optional opening hours,
choose a transport mode (walking, driving with or without tolls, or
public transport) and a departure time. The app geocodes the
addresses, computes an approximate optimal tour using a combination
of nearest‑neighbour and 2‑opt heuristics, generates a detailed
schedule including arrival and departure times at each location, and
produces an interactive map via Folium. When the mode involves
driving with tolls, a rudimentary toll calculation can be applied
(integration with a national toll database is stubbed out and left
for future work). Finally, the itinerary can be pushed to the
user’s LINE account via the LINE Messaging API.

## Features

* **Geocoding** of free‑form addresses via OpenStreetMap’s Nominatim.
* **Routing** using OSRM where available with fallback to Haversine‑based
  estimates.
* **Tour optimisation** using nearest neighbour for initial
  solution and 2‑opt for local improvement.
* **Schedule generation** taking into account stay durations
  and optional opening hours with warnings for early/late
  arrivals.
* **Interactive map** built with Folium, showing numbered markers
  and the route polyline.
* **LINE integration** to send the itinerary to a specified user ID.
* **Configurable distance/time threshold** to favour distance
  minimisation when travel‑time differences are small.
* **Streamlit Secrets** for sensitive credentials (Google OAuth,
  allowed email, LINE channel secret and access token).

## Installation

Clone the repository and install the dependencies with pip:

```bash
git clone https://github.com/yourusername/movewise.git
cd movewise
pip install -r requirements.txt
```

You will also need to create a `.streamlit/secrets.toml` file with
the following keys:

```toml
GOOGLE_CLIENT_ID = "your-google-client-id"
GOOGLE_CLIENT_SECRET = "your-google-client-secret"
ALLOWED_EMAIL = "you@example.com"
LINE_CHANNEL_SECRET = "your-line-channel-secret"
LINE_CHANNEL_ACCESS_TOKEN = "your-line-channel-access-token"
```

These values are required for authentication and to push messages
via LINE. In the provided implementation the Google client details
are not yet used; authentication is simulated via an email check.

## Running locally

To run the app locally for development:

```bash
streamlit run movewise/app.py
```

Visit `http://localhost:8501` in your browser. When prompted,
enter the email address specified in your `ALLOWED_EMAIL` secret to
access the application.

## Deployment to Streamlit Cloud

1. Create a new repository on GitHub and push the contents of this
   project to it.
2. Sign in to [Streamlit Cloud](https://share.streamlit.io/) and
   create a new app pointing to your repository and to the file
   `movewise/app.py`.
3. In the Streamlit Cloud settings, add the same keys as in
   `.streamlit/secrets.toml` via the Secrets manager.
4. Deploy the app. When you visit the provided URL you will be
   prompted to authenticate using your email; upon success you can
   generate plans and send itineraries via LINE.

## Limitations and future work

* **Google OAuth**: The current implementation uses a simple
  email check for authentication. Integrating full Google OAuth is
  planned but requires setting up an OAuth consent screen and
  implementing the flow in Streamlit.
* **Public transport**: At present only walking and driving modes
  are implemented. Public transport support (GTFS import, HTML
  scraping, manual entry) remains to be developed.
* **Toll calculation**: The function `total_toll_cost` returns zero
  because a national toll database is not bundled. Replace the
  contents of `movewise/data/tolls.csv` with a comprehensive list
  and implement the lookup logic.
* **Robust error handling**: Network errors and API limits are
  currently handled in a basic manner. Production use should
  include retry logic and caching.
* **UI enhancements**: Additional validation, better form layout,
  and progress indicators would improve user experience.

## Tests

Unit tests are provided under the `tests/` directory. To run them:

```bash
pytest
```

The tests verify the correctness of the optimisation heuristics,
Haversine distance calculations, and a small simulation to ensure
that the pipeline runs end‑to‑end without errors.

---

© 2025 MoveWise. This project is provided for educational purposes and
does not carry any warranty. Use at your own risk.
