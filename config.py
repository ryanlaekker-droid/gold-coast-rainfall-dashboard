"""
Central configuration for the Gold Coast rainfall dashboard.

Everything that might need changing lives here. No settings anywhere else.
"""

from pathlib import Path

# --- Location -----------------------------------------------------------

LATITUDE = -28.1644
LONGITUDE = 153.5047
LOCATION_NAME = "Gold Coast Airport (Coolangatta)"
LOCAL_TZ = "Australia/Brisbane"          # AEST, no daylight saving

# --- The decision rule --------------------------------------------------

THRESHOLD_MM = 10.0
WINDOW_HOURS = 24

# --- Forecast horizon ---------------------------------------------------

FORECAST_DAYS = 10
PAST_DAYS = 1                            # so tonight's window is complete

# --- Open-Meteo endpoints -----------------------------------------------

ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 30

ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"

# --- Models -------------------------------------------------------------

ENSEMBLE_MODEL = {
    "id": "ecmwf_ifs025",
    "label": "ECMWF ensemble",
    "centre": "ECMWF",
    "note": "51 members, 0.25 degree grid",
}

# Independent forecasting centres. ECMWF's deterministic run is deliberately
# excluded: it shares a centre and model with the ensemble above, so counting
# it would inflate apparent agreement.
DETERMINISTIC_MODELS = [
    {"id": "gfs_global", "label": "GFS", "centre": "NOAA, United States"},
    {"id": "ukmo_global_deterministic_10km", "label": "UKMO",
     "centre": "Met Office, United Kingdom"},
    {"id": "icon_global", "label": "ICON", "centre": "DWD, Germany"},
]

# Kept here so they can be switched on by moving one line up into the list
# above. Verified unavailable at this location on 9 August 2026.
UNAVAILABLE_MODELS = [
    {"id": "bom_access_global", "label": "ACCESS-G", "centre": "BOM, Australia",
     "reason": "Open-Meteo returned only null values on all three routes"},
    {"id": "kma_gdps", "label": "GDPS", "centre": "KMA, South Korea",
     "reason": "Open-Meteo returned only null values"},
]

# --- Files --------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
LATEST_FILE = DATA_DIR / "latest.json"

# --- Links shown at the bottom of the dashboard -------------------------

REFERENCE_LINKS = [
    {"label": "BOM Coolangatta detailed forecast",
     "url": "https://www.bom.gov.au/places/qld/coolangatta/forecast/detailed/"},
    {"label": "BOM Boyd St drainage channel (graph)",
     "url": "https://www.bom.gov.au/fwo/IDQ65388/IDQ65388.540842.plt.shtml"},
    {"label": "BOM Boyd St drainage channel (table)",
     "url": "https://www.bom.gov.au/fwo/IDQ65388/IDQ65388.540842.tbl.shtml"},
    {"label": "BOM Australian Water Outlook",
     "url": "https://awo.bom.gov.au/"},
    {"label": "OzForecast Coolangatta",
     "url": "https://ozforecast.com.au/cgi-bin/weather.cgi?station=Coolangatta.QLD"},
    {"label": "Meteologix ECMWF ensemble, Gold Coast",
     "url": "https://meteologix.com/au/weather/2165087-gold-coast"},
]

# --- Map basemap --------------------------------------------------------

# Global satellite imagery, no API key. If tiles do not appear, set
# MAP_TILES to None and the map falls back to a plain street basemap.
MAP_TILES = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
             "World_Imagery/MapServer/tile/{z}/{y}/{x}")
MAP_ATTRIBUTION = "Imagery: Esri, Maxar, Earthstar Geographics"
MAP_ZOOM = 9.2

# --- Daily table convention ---------------------------------------------

# "rain_day"  fixed 09:00 to 09:00 AEST windows, labelled by start day.
#             Consistent and comparable; matches the Australian rain day.
# "peak"      the wettest window ending each day. More sensitive, but the
#             end time floats and day labels can be misleading.
DAILY_WINDOW_MODE = "rain_day"
RAIN_DAY_START_HOUR = 9

# --- BOM table ----------------------------------------------------------

# The BOM table stops after the last 3-hourly step that carries a rainfall
# amount, since later steps show only chance of any rain. This caps it in
# case BOM ever publishes amounts further ahead.
BOM_MAX_STEPS = 20