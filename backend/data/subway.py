import json
import logging
import requests
from backend.config import CACHE_DIR, SUBWAY_STATIONS_URL

STATIONS_CACHE_PATH = CACHE_DIR / "stations.json"

logger = logging.getLogger(__name__)

def fetch_stations(force_refresh=False):
    """
    Fetch subway stations from NY Open Data and cache them.
    """
    if not force_refresh and STATIONS_CACHE_PATH.exists():
        try:
            with open(STATIONS_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading subway stations cache: {e}. Re-fetching...")

    logger.info("Fetching subway stations from NY Open Data...")
    try:
        # SODA API call. Limit to 1000 to get all NYC subway stations (~470)
        response = requests.get(SUBWAY_STATIONS_URL, params={"$limit": 1000}, timeout=15)
        response.raise_for_status()
        stations = response.json()
        
        # Clean and format the station coordinates
        for station in stations:
            station["station_name"] = station.get("stop_name", "")
            
            lat_str = station.get("gtfs_latitude")
            lon_str = station.get("gtfs_longitude")
            
            if lat_str is not None:
                station["latitude"] = float(lat_str)
            if lon_str is not None:
                station["longitude"] = float(lon_str)
                
        # Save to cache
        with open(STATIONS_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(stations, f, indent=2)
            
        logger.info(f"Successfully cached {len(stations)} subway stations.")
        return stations
    except Exception as e:
        logger.error(f"Failed to fetch subway stations: {e}")
        # Fallback to empty list or cached file if it exists
        if STATIONS_CACHE_PATH.exists():
            with open(STATIONS_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

def get_stations_by_line(line_char: str):
    """
    Get all stations that serve a specific line (e.g. 'A', 'C', '3').
    """
    stations = fetch_stations()
    filtered = []
    line_upper = line_char.upper()
    
    for s in stations:
        # 'daytime_routes' usually lists the lines served, e.g. "A C" or "1 2 3"
        routes_str = s.get("daytime_routes", "")
        routes = [r.strip().upper() for r in routes_str.replace(",", " ").split() if r.strip()]
        if line_upper in routes:
            filtered.append(s)
            
    return filtered

def get_all_lines():
    """
    Get sorted list of all unique subway lines.
    """
    stations = fetch_stations()
    lines = set()
    for s in stations:
        routes_str = s.get("daytime_routes", "")
        routes = [r.strip().upper() for r in routes_str.replace(",", " ").split() if r.strip()]
        lines.update(routes)
    return sorted(list(lines))
