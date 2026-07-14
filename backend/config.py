import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "backend" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Subfolders in cache
ISOCHRONES_CACHE_DIR = CACHE_DIR / "isochrones"
ISOCHRONES_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Default configuration
DEFAULT_WALK_SPEED_KMH = 4.0  # stroller pace
WALK_SPEED_MIN_KMH = 2.0
WALK_SPEED_MAX_KMH = 6.0

# Bounding box for pre-fetching the walk network
# Covers Upper Manhattan (59th St / Central Park South) down to Brooklyn (Utica Ave / Nostrand Ave)
# Format: (left/west, bottom/south, right/east, top/north)
DEFAULT_BBOX = (-74.020, 40.660, -73.910, 40.780)

# MTA Subway Line Colors (hex codes)
MTA_COLORS = {
    # Blue: Eighth Avenue Local/Express
    "A": "#0039A6",
    "C": "#0039A6",
    "E": "#0039A6",
    # Red: Broadway-Seventh Avenue Local/Express
    "1": "#EE352E",
    "2": "#EE352E",
    "3": "#EE352E",
    # Orange: Sixth Avenue Local/Express
    "B": "#FF6319",
    "D": "#FF6319",
    "F": "#FF6319",
    "M": "#FF6319",
    # Lime Green: Crosstown Local
    "G": "#6CBE45",
    # Light Grey: Canarsie Local
    "L": "#A7A9AC",
    # Brown: Nassau Street Local/Express
    "J": "#996633",
    "Z": "#996633",
    # Yellow: Broadway Local/Express
    "N": "#FCCC0A",
    "Q": "#FCCC0A",
    "R": "#FCCC0A",
    "W": "#FCCC0A",
    # Purple: Flushing Local/Express
    "7": "#B933AD",
    # Dark Grey: Shuttles
    "S": "#808080"
}

# API Endpoints
SUBWAY_STATIONS_URL = "https://data.ny.gov/resource/39hk-dx4f.json"
DAYCARE_PROGRAMS_URL = "https://data.cityofnewyork.us/resource/gy3q-4tzp.json"
DAYCARE_INSPECTIONS_URL = "https://data.cityofnewyork.us/resource/dsg6-ifza.json"

