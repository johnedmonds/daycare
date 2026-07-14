import math
import logging
from shapely.geometry import shape, Point

logger = logging.getLogger(__name__)

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two points on the Earth in meters.
    """
    R = 6371000  # Radius of Earth in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def estimate_walk_time(lat1, lon1, lat2, lon2, walk_speed_kmh):
    """
    Estimate walk time in minutes using Haversine distance and a grid factor (1.3)
    to account for typical urban street networks.
    """
    dist_meters = haversine_distance(lat1, lon1, lat2, lon2)
    # Convert speed to meters per minute
    speed_m_per_min = (walk_speed_kmh * 1000) / 60
    # Apply 1.3 grid factor for real walking distance
    return (dist_meters * 1.3) / speed_m_per_min

def find_daycares_in_isochrones(daycares, isochrones_dict):
    """
    Filter daycares to find which ones lie inside any computed isochrone.
    isochrones_dict structure:
    {
       "source_id": {
          "5": geojson_geom,
          "10": geojson_geom,
          "15": geojson_geom
       }
    }
    Returns list of daycares with matching metadata:
      - 'nearest_source_id' (e.g. station GTFS ID, 'home', or 'work')
      - 'walk_ring_mins' (the smallest isochrone ring containing the daycare)
    """
    matched = []
    
    # Load shapely shapes once for efficiency
    shapes = []
    for source_id, rings in isochrones_dict.items():
        for mins_str, geojson in rings.items():
            try:
                poly = shape(geojson)
                shapes.append((source_id, int(mins_str), poly))
            except Exception as e:
                logger.error(f"Error parsing isochrone shape for {source_id}: {e}")
                
    for d in daycares:
        lat = d.get("latitude")
        lng = d.get("longitude")
        if lat is None or lng is None:
            continue
            
        pt = Point(lng, lat)
        best_source = None
        best_mins = 999
        
        for source_id, mins, poly in shapes:
            if poly.contains(pt):
                if mins < best_mins:
                    best_mins = mins
                    best_source = source_id
                    
        if best_source is not None:
            d_copy = dict(d)
            d_copy["nearest_source_id"] = best_source
            d_copy["walk_ring_mins"] = best_mins
            matched.append(d_copy)
            
    return matched

def calculate_added_commute_time(
    daycare, 
    nearest_source_id, 
    home_coords=None, 
    work_coords=None, 
    home_station_coords=None, 
    work_station_coords=None,
    walk_speed_kmh=4.0
):
    """
    Estimate the added commute time in minutes for a daycare.
    
    1. For a daycare near a commute station:
       added_time = 2 * walk(station -> daycare) + train_wait (4 mins)
       
    2. For a daycare near home (source_id == 'home'):
       added_time = walk(home -> daycare) + walk(daycare -> home_station) - walk(home -> home_station)
       
    3. For a daycare near work (source_id == 'work'):
       added_time = walk(work_station -> daycare) + walk(daycare -> work) - walk(work_station -> work)
    """
    d_lat = daycare.get("latitude")
    d_lng = daycare.get("longitude")
    
    # Average train wait time (headway/2 during rush hour)
    TRAIN_WAIT = 4.0
    
    # CASE 2: Near Home
    if nearest_source_id == "home" and home_coords and home_station_coords:
        w_home_to_daycare = estimate_walk_time(home_coords[0], home_coords[1], d_lat, d_lng, walk_speed_kmh)
        w_daycare_to_station = estimate_walk_time(d_lat, d_lng, home_station_coords[0], home_station_coords[1], walk_speed_kmh)
        w_home_to_station = estimate_walk_time(home_coords[0], home_coords[1], home_station_coords[0], home_station_coords[1], walk_speed_kmh)
        
        added = w_home_to_daycare + w_daycare_to_station - w_home_to_station
        return max(0.0, round(added, 1))
        
    # CASE 3: Near Work
    if nearest_source_id == "work" and work_coords and work_station_coords:
        w_station_to_daycare = estimate_walk_time(work_station_coords[0], work_station_coords[1], d_lat, d_lng, walk_speed_kmh)
        w_daycare_to_work = estimate_walk_time(d_lat, d_lng, work_coords[0], work_coords[1], walk_speed_kmh)
        w_station_to_work = estimate_walk_time(work_station_coords[0], work_station_coords[1], work_coords[0], work_coords[1], walk_speed_kmh)
        
        added = w_station_to_daycare + w_daycare_to_work - w_station_to_work
        return max(0.0, round(added, 1))
        
    # CASE 1: Commute Station (or fallback if coordinates missing)
    # We need the station coordinates. We can get them from the nearest station object.
    # If not provided, we fall back to the estimated walk time from the daycare's nearest source id.
    # The caller should pass the station coordinates as home_station_coords or work_station_coords if available.
    return None
