import math
import json
from typing import List, Tuple, Dict, Any

import streamlit as st
import requests
from geopy.geocoders import Nominatim
from shapely.geometry import Polygon
import folium
from streamlit_folium import st_folium

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_MIRRORS = [
	"https://overpass-api.de/api/interpreter",
	"https://overpass.kumi.systems/api/interpreter",
	"https://overpass.openstreetmap.ru/api/interpreter",
]


def miles_to_meters(miles: float) -> float:
	return miles * 1609.344


def kilometers_to_meters(km: float) -> float:
	return km * 1000.0


def meters_to_sq_km(m2: float) -> float:
	return m2 / 1_000_000.0


def meters_to_sq_miles(m2: float) -> float:
	return m2 / 2_589_988.110336


def geocode_location(query: str) -> Tuple[float, float]:
	geolocator = Nominatim(user_agent="building-density-app")
	location = geolocator.geocode(query)
	if not location:
		raise ValueError("Location not found. Try a more specific address or coordinates.")
	return (location.latitude, location.longitude)


def parse_lat_lon_from_string(s: str) -> Tuple[float, float] | None:
	"""Try to parse a string like 'lat, lon' or 'lat lon' into floats within valid ranges."""
	try:
		clean = s.strip().replace(",", " ")
		parts = [p for p in clean.split() if p]
		if len(parts) != 2:
			return None
		lat_val = float(parts[0])
		lon_val = float(parts[1])
		if not (-90.0 <= lat_val <= 90.0 and -180.0 <= lon_val <= 180.0):
			return None
		return lat_val, lon_val
	except Exception:
		return None


def build_overpass_query(lat: float, lon: float, radius_m: float, timeout_s: int) -> str:
	query = f"""
	[out:json][timeout:{timeout_s}];
	(
		way["building"](around:{radius_m},{lat},{lon});
		rel["building"](around:{radius_m},{lat},{lon});
	);
	out tags geom;
	"""
	return query


def fetch_buildings(lat: float, lon: float, radius_m: float, endpoint: str, timeout_s: int, retries: int) -> List[Dict[str, Any]]:
	last_err: Exception | None = None
	for attempt in range(retries + 1):
		try:
			resp = requests.post(
				endpoint,
				data={"data": build_overpass_query(lat, lon, radius_m, timeout_s)},
				timeout=timeout_s + 30,
			)
			resp.raise_for_status()
			data = resp.json()
			return data.get("elements", [])
		except Exception as e:
			last_err = e
			# simple backoff
			try:
				import time
				time.sleep(min(2 ** attempt, 5))
			except Exception:
				pass
	if last_err:
		raise last_err
	return []


def element_to_polygon(element: Dict[str, Any]) -> Polygon | None:
	geom = element.get("geometry")
	if not geom:
		return None
	coords = [(pt["lon"], pt["lat"]) for pt in geom]
	if len(coords) >= 3 and (coords[0] != coords[-1]):
		coords.append(coords[0])
	try:
		polygon = Polygon(coords)
		if polygon.is_valid and polygon.area > 0:
			return polygon
	except Exception:
		return None
	return None


def count_buildings_and_polygons(elements: List[Dict[str, Any]]) -> Tuple[int, List[Polygon]]:
	polygons: List[Polygon] = []
	for el in elements:
		if el.get("type") in {"way", "relation"}:
			poly = element_to_polygon(el)
			if poly is not None:
				polygons.append(poly)
	return len(polygons), polygons


def compute_density(num_buildings: int, radius_m: float) -> Dict[str, float]:
	circle_area_m2 = math.pi * (radius_m ** 2)
	return {
		"per_sq_km": num_buildings / meters_to_sq_km(circle_area_m2) if circle_area_m2 > 0 else 0.0,
		"per_sq_mile": num_buildings / meters_to_sq_miles(circle_area_m2) if circle_area_m2 > 0 else 0.0,
		"area_sq_km": meters_to_sq_km(circle_area_m2),
		"area_sq_miles": meters_to_sq_miles(circle_area_m2),
	}


def make_map(lat: float, lon: float, radius_m: float, building_polygons: List[Polygon]) -> folium.Map:
	m = folium.Map(location=[lat, lon], zoom_start=14, control_scale=True)
	folium.Circle(
		location=[lat, lon],
		radius=radius_m,
		color="#1f77b4",
		fill=True,
		fill_opacity=0.05,
		weight=2,
	).add_to(m)
	for poly in building_polygons:
		try:
			folium.GeoJson(
				data=poly.__geo_interface__,
				style_function=lambda x: {"color": "#d62728", "weight": 1, "fillColor": "#ff9896", "fillOpacity": 0.5},
			).add_to(m)
		except Exception:
			pass
	folium.Marker([lat, lon], icon=folium.Icon(color="blue", icon="info-sign"), tooltip="Center").add_to(m)
	return m


def inject_styles() -> None:
	st.markdown(
		"""
		<style>
			:root {
				--primary: #1f77b4;
				--accent: #ff7f0e;
				--card-bg: #ffffff;
				--soft: #f5f7fb;
				--text: #0f172a;
				--muted: #475569;
			}
			/* App background */
			.stApp {
				background: linear-gradient(180deg, #f8fafc 0%, #f3f6fb 100%);
				color: var(--text);
			}
			/* Typography tweaks */
			h1, h2, h3, h4 { letter-spacing: 0.2px; }
			.block-container { padding-top: 1.2rem; }
			p, label, span { color: var(--muted); }
			/* Cards */
			.card {
				background: var(--card-bg);
				border: 1px solid rgba(2,6,23,0.06);
				box-shadow: 0 8px 24px rgba(2,6,23,0.06);
				border-radius: 14px;
				padding: 18px 16px;
			}
			/* Buttons */
			.stButton>button {
				background: var(--primary) !important;
				color: #fff !important;
				border: none !important;
				border-radius: 10px !important;
				padding: 10px 18px !important;
				font-weight: 700 !important;
				box-shadow: 0 6px 14px rgba(31,119,180,0.25) !important;
				border-color: var(--primary) !important;
			}
			/* Ensure inner label stays visible */
			.stButton>button span, .stButton>button p {
				color: #ffffff !important;
			}
			/* Hover/Focus/Active */
			.stButton>button:hover { filter: brightness(0.96); transform: translateY(-1px); }
			.stButton>button:focus, .stButton>button:active { outline: none !important; box-shadow: 0 0 0 3px rgba(31,119,180,0.25) !important; }
			/* Disabled state */
			.stButton>button:disabled {
				background: #9abfe0 !important;
				color: #ffffff !important;
				opacity: 0.85 !important;
			}
			/* Sidebar */
			aside[data-testid="stSidebar"] {
				background: linear-gradient(180deg, #ffffff 0%, #f7faff 100%);
				border-right: 1px solid rgba(2,6,23,0.06);
			}
			/* Inputs */
			[data-baseweb="input"] input, [data-baseweb="textarea"] textarea, .stNumberInput input, .stTextInput input, .stSelectbox div[role="button"] {
				border-radius: 10px !important;
				border: 1px solid rgba(2,6,23,0.12) !important;
			}
			/* Radio & select labels */
			[data-testid="stWidgetLabel"] p { color: var(--text); font-weight: 600; }
			/* Section headers */
			section>div>div>div>h2,
			section>div>div>div>h3 { position: relative; padding-left: 10px; }
			section>div>div>div>h2:before,
			section>div>div>div>h3:before {
				content: "";
				display: inline-block;
				width: 6px; height: 16px;
				background: var(--primary);
				border-radius: 4px;
				position: absolute; left: 0; top: 10px;
			}
			/* Metrics */
			[data-testid="stMetric"] {
				background: var(--soft);
				border: 1px solid rgba(2,6,23,0.06);
				border-radius: 12px;
				padding: 10px 12px;
			}
			/* Folium map container spacing */
			.folium-map { border-radius: 14px; overflow: hidden; border: 1px solid rgba(2,6,23,0.06); }
		</style>
		""",
		unsafe_allow_html=True,
	)


def main() -> None:
	st.set_page_config(page_title="Building Density Calculator", layout="wide")
	inject_styles()
	st.markdown("<span class='header-badge'>🏙️ Urban analytics</span>", unsafe_allow_html=True)
	st.title("Building Density Calculator")
	st.caption("Compute buildings and density within a radius using OpenStreetMap data.")

	with st.sidebar:
		st.header("Search Parameters")
		input_mode = st.radio("Input Mode", ["Address", "Coordinates"], index=0)
		address = ""
		lat = 37.4221
		lon = -122.0841
		if input_mode == "Address":
			address = st.text_input("Address or place", placeholder="e.g., Times Square or 37.7749, -122.4194")
		else:
			lat_text = st.text_input("Latitude", value=f"{lat}")
			lon_text = st.text_input("Longitude", value=f"{lon}")
			# Try parsing user-entered text; keep previous value if parsing fails
			try:
				lat = float(lat_text)
			except Exception:
				pass
			try:
				lon = float(lon_text)
			except Exception:
				pass

		units = st.selectbox("Radius Units", ["kilometers", "miles"], index=0)
		radius_value = st.number_input("Radius", min_value=0.1, max_value=50.0, value=1.0, step=0.1)
		# Use default Overpass settings (no UI)
		endpoint = OVERPASS_URL
		timeout_s = 120
		retries = 2
		force_refresh = False
		query_btn = st.button("Calculate", type="primary")

	# Determine center for live map based on current inputs
	center_lat, center_lon = lat, lon
	radius_m_from_inputs = kilometers_to_meters(radius_value) if units == "kilometers" else miles_to_meters(radius_value)
	if input_mode == "Address" and address.strip():
		# First, attempt to parse raw coordinates like "lat, lon"
		parsed_coords = parse_lat_lon_from_string(address)
		if parsed_coords is not None:
			center_lat, center_lon = parsed_coords
		else:
			try:
				center_lat, center_lon = geocode_location(address)
			except Exception:
				pass

	# Render live map (updates as inputs change). Overlays will be added after calculation.
	st.subheader("Map")
	polygons_to_show: List[Polygon] = []
	# Keep overlays after reruns if we have a previous calculation
	if "calc" in st.session_state and isinstance(st.session_state["calc"], dict):
		try:
			polygons_to_show = st.session_state["calc"].get("polygons", [])
		except Exception:
			polygons_to_show = []

	results_area = st.empty()

	if query_btn:
		try:
			# If address mode, ensure we use geocoded coordinates for calculation
			calc_lat, calc_lon = (center_lat, center_lon) if input_mode == "Address" else (lat, lon)
			# Validate ranges for coordinates in Coordinates mode
			if input_mode == "Coordinates":
				if not (-90.0 <= calc_lat <= 90.0 and -180.0 <= calc_lon <= 180.0):
					raise ValueError("Coordinates out of range. Latitude must be -90..90, Longitude -180..180.")
			# Build cache key and check
			if "cache" not in st.session_state:
				st.session_state["cache"] = {}
			cache_key = f"{endpoint}|{round(calc_lat,6)}|{round(calc_lon,6)}|{round(radius_m_from_inputs,2)}|{timeout_s}"
			cache_hit = False
			elements: List[Dict[str, Any]]
			if not force_refresh and cache_key in st.session_state["cache"]:
				cache_hit = True
				elements = st.session_state["cache"][cache_key]["elements"]
				queried_at = st.session_state["cache"][cache_key]["timestamp"]
			else:
				with st.spinner("Querying OpenStreetMap for buildings..."):
					elements = fetch_buildings(calc_lat, calc_lon, radius_m_from_inputs, endpoint, timeout_s, retries)
					import datetime as _dt
					queried_at = _dt.datetime.utcnow().isoformat() + "Z"
					st.session_state["cache"][cache_key] = {"elements": elements, "timestamp": queried_at}
			with st.spinner("Processing geometries..."):
				num_buildings, polygons = count_buildings_and_polygons(elements)
				stats = compute_density(num_buildings, radius_m_from_inputs)
				polygons_to_show = polygons

			# Persist results so they remain after reruns
			st.session_state["calc"] = {
				"num_buildings": num_buildings,
				"stats": stats,
				"polygons": polygons,
				"center_lat": calc_lat,
				"center_lon": calc_lon,
				"radius_m": radius_m_from_inputs,
				"endpoint": endpoint,
				"timeout_s": timeout_s,
				"retries": retries,
				"timestamp": queried_at,
				"cache_hit": cache_hit,
			}

			# Render results below (outside button) using session state
		except Exception as e:
			st.error(str(e))

	# If we have saved results, display them persistently
	if "calc" in st.session_state and isinstance(st.session_state["calc"], dict):
		_saved = st.session_state["calc"]
		with results_area.container():
			left, right = st.columns([1, 2])
			with left:
				st.markdown("<div class='card'>", unsafe_allow_html=True)
				st.subheader("Results")
				st.metric("Buildings found", f"{_saved['num_buildings']}")
				st.write(f"Search area: {_saved['stats']['area_sq_km']:.3f} sq km ({_saved['stats']['area_sq_miles']:.3f} sq mi)")
				st.write(f"Density: {_saved['stats']['per_sq_km']:.2f} buildings/sq km")
				st.write(f"Density: {_saved['stats']['per_sq_mile']:.2f} buildings/sq mi")
				with st.expander("Run metadata"):
					st.write(f"Endpoint: {_saved.get('endpoint','')}")
					st.write(f"Timeout: {_saved.get('timeout_s', 0)}s, Retries: {_saved.get('retries', 0)}")
					st.write(f"Queried at (UTC): {_saved.get('timestamp','')}")
					st.write(f"Cache hit: {_saved.get('cache_hit', False)}")
				st.caption("Note: OSM is community-sourced; completeness varies by location.")
				st.markdown("</div>", unsafe_allow_html=True)
			with right:
				m_results = make_map(_saved["center_lat"], _saved["center_lon"], _saved["radius_m"], _saved["polygons"])
				st_folium(m_results, width=None, height=600, key="results_map")

	# Draw the map with current center and radius, overlay polygons if available
	st.markdown("<div class='card'>", unsafe_allow_html=True)
	m = make_map(center_lat, center_lon, radius_m_from_inputs, polygons_to_show)
	st_folium(m, width=None, height=600, key="live_map")
	st.markdown("</div>", unsafe_allow_html=True)

	st.caption("Built with Streamlit, Folium, and OpenStreetMap data.")


if __name__ == "__main__":
	main() 