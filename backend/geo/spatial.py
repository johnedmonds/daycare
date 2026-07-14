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

_daycare_nodes_cache = None

def get_daycare_nodes(G, daycares):
    """
    Get a cached mapping of daycare keys to their nearest network nodes.
    """
    global _daycare_nodes_cache
    if _daycare_nodes_cache is None:
        import osmnx as ox
        logger.info("Computing nearest network nodes for all daycares...")
        # Only compute for daycares with valid coordinates
        valid_daycares = [d for d in daycares if d.get("latitude") is not None and d.get("longitude") is not None]
        if valid_daycares:
            lats = [d["latitude"] for d in valid_daycares]
            lngs = [d["longitude"] for d in valid_daycares]
            nodes = ox.nearest_nodes(G, X=lngs, Y=lats)
            _daycare_nodes_cache = {}
            for d, node in zip(valid_daycares, nodes):
                key = d.get("dcid") or d.get("permit_number") or f"{d['latitude']}_{d['longitude']}"
                _daycare_nodes_cache[key] = int(node)
        else:
            _daycare_nodes_cache = {}
        logger.info("Computing daycare network nodes complete.")
    return _daycare_nodes_cache

def network_walk_time(G, start_lat, start_lng, end_lat, end_lng, walk_speed_kmh):
    """
    Calculate the actual walk time in minutes between two points using the OSM network.
    If no path is found, falls back to estimate_walk_time.
    """
    import osmnx as ox
    import networkx as nx
    
    try:
        start_node = ox.nearest_nodes(G, X=start_lng, Y=start_lat)
        end_node = ox.nearest_nodes(G, X=end_lng, Y=end_lat)
        
        walk_speed_m_per_min = (walk_speed_kmh * 1000) / 60
        path_len = nx.shortest_path_length(G, start_node, end_node, weight="length")
        
        net_time = path_len / walk_speed_m_per_min
        
        # Add straight-line offset from actual coordinates to the network nodes
        node_start_data = G.nodes[start_node]
        node_end_data = G.nodes[end_node]
        
        offset_start = haversine_distance(start_lat, start_lng, node_start_data["y"], node_start_data["x"])
        offset_end = haversine_distance(end_lat, end_lng, node_end_data["y"], node_end_data["x"])
        
        return net_time + (offset_start + offset_end) / walk_speed_m_per_min
    except Exception as e:
        logger.debug(f"Network routing failed, falling back to straight-line estimate: {e}")
        return estimate_walk_time(start_lat, start_lng, end_lat, end_lng, walk_speed_kmh)

def find_daycares_in_isochrones(daycares, G, sources_dict, walk_time_mins, walk_speed_kmh):
    """
    Filter daycares to find which ones are reachable within walk_time_mins from any source.
    Returns list of daycares with matching metadata:
      - 'nearest_source_id'
      - 'walk_ring_mins' (5, 10, or 15)
      - 'network_walk_time' (the actual calculated walk time in minutes)
    """
    import osmnx as ox
    import networkx as nx
    
    # Speed in meters per minute
    walk_speed_m_per_min = (walk_speed_kmh * 1000) / 60
    # Maximum network search distance (m)
    max_dist = walk_time_mins * walk_speed_m_per_min
    
    # Lazy load daycare nodes cache
    daycare_nodes = get_daycare_nodes(G, daycares)
    
    # Pre-calculate reachable nodes and their distances for each source
    source_reachables = {}
    for source_id, coords in sources_dict.items():
        try:
            n_source = ox.nearest_nodes(G, X=coords[1], Y=coords[0])
            node_data = G.nodes[n_source]
            offset_start = haversine_distance(coords[0], coords[1], node_data["y"], node_data["x"])
            
            # Dijkstra path lengths in meters
            lengths = nx.single_source_dijkstra_path_length(G, source=n_source, cutoff=max_dist, weight="length")
            source_reachables[source_id] = {
                "n_source": n_source,
                "offset_start": offset_start,
                "lengths": lengths
            }
        except Exception as e:
            logger.error(f"Error computing reachable nodes for source {source_id}: {e}")
            
    matched = []
    for d in daycares:
        lat = d.get("latitude")
        lng = d.get("longitude")
        if lat is None or lng is None:
            continue
            
        dc_key = d.get("dcid") or d.get("permit_number") or f"{lat}_{lng}"
        n_dc = daycare_nodes.get(dc_key)
        if n_dc is None:
            continue
            
        best_source = None
        best_time = 999.0
        
        try:
            node_dc_data = G.nodes[n_dc]
            offset_end = haversine_distance(lat, lng, node_dc_data["y"], node_dc_data["x"])
        except Exception:
            offset_end = 0.0
            
        for source_id, reach in source_reachables.items():
            lengths = reach["lengths"]
            if n_dc in lengths:
                net_len = lengths[n_dc]
                net_time = net_len / walk_speed_m_per_min
                offset_time = (reach["offset_start"] + offset_end) / walk_speed_m_per_min
                total_time = net_time + offset_time
                
                if total_time <= walk_time_mins:
                    if total_time < best_time:
                        best_time = total_time
                        best_source = source_id
                        
        if best_source is not None:
            # Determine which walk ring (5, 10, 15) it belongs to
            if best_time <= 5.0:
                ring = 5
            elif best_time <= 10.0:
                ring = 10
            else:
                ring = 15
                
            d_copy = dict(d)
            d_copy["nearest_source_id"] = best_source
            d_copy["walk_ring_mins"] = ring
            d_copy["network_walk_time"] = round(best_time, 2)
            matched.append(d_copy)
            
    return matched

def calculate_added_commute_time(
    G,
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
    
    # CASE 2: Near Home
    if nearest_source_id == "home" and home_coords and home_station_coords:
        w_home_to_daycare = network_walk_time(G, home_coords[0], home_coords[1], d_lat, d_lng, walk_speed_kmh)
        w_daycare_to_station = network_walk_time(G, d_lat, d_lng, home_station_coords[0], home_station_coords[1], walk_speed_kmh)
        w_home_to_station = network_walk_time(G, home_coords[0], home_coords[1], home_station_coords[0], home_station_coords[1], walk_speed_kmh)
        
        added = w_home_to_daycare + w_daycare_to_station - w_home_to_station
        return max(0.0, round(added, 1))
        
    # CASE 3: Near Work
    if nearest_source_id == "work" and work_coords and work_station_coords:
        w_station_to_daycare = network_walk_time(G, work_station_coords[0], work_station_coords[1], d_lat, d_lng, walk_speed_kmh)
        w_daycare_to_work = network_walk_time(G, d_lat, d_lng, work_coords[0], work_coords[1], walk_speed_kmh)
        w_station_to_work = network_walk_time(G, work_station_coords[0], work_station_coords[1], work_coords[0], work_coords[1], walk_speed_kmh)
        
        added = w_station_to_daycare + w_daycare_to_work - w_station_to_work
        return max(0.0, round(added, 1))
        
    return None
