import logging
import networkx as nx
import osmnx as ox
from shapely.geometry import MultiPoint, Polygon, Point, mapping, LineString
from shapely import concave_hull
from backend.config import DEFAULT_WALK_SPEED_KMH

logger = logging.getLogger(__name__)

def update_edge_times(G, walk_speed_kmh):
    """
    Calculate and set the 'time' attribute on all edges based on walk_speed_kmh.
    """
    # Speed in meters per minute
    walk_speed_m_per_min = (walk_speed_kmh * 1000) / 60
    for u, v, k, data in G.edges(data=True, keys=True):
        data["time"] = data["length"] / walk_speed_m_per_min

def compute_isochrone(G, lat, lng, walk_minutes, walk_speed_kmh=DEFAULT_WALK_SPEED_KMH):
    """
    Compute a single walking isochrone polygon for a given lat/lng.
    Returns a GeoJSON-like dictionary of the polygon geometry.
    """
    try:
        # Update graph edge travel times
        update_edge_times(G, walk_speed_kmh)
        
        # Find nearest graph node (Note: X=longitude, Y=latitude)
        center_node = ox.nearest_nodes(G, X=lng, Y=lat)
        
        # Get reachable subgraph
        subgraph = nx.ego_graph(G, center_node, radius=walk_minutes, distance="time")
        
        # Extract coordinates of reachable nodes
        coords = [(data["x"], data["y"]) for node, data in subgraph.nodes(data=True)]
        
        # Enrich coords with edge midpoints and geometries to keep street segments covered
        for u, v, k, data in subgraph.edges(data=True, keys=True):
            mx = (subgraph.nodes[u]["x"] + subgraph.nodes[v]["x"]) / 2
            my = (subgraph.nodes[u]["y"] + subgraph.nodes[v]["y"]) / 2
            coords.append((mx, my))
            if "geometry" in data:
                for x, y in data["geometry"].coords:
                    coords.append((x, y))

        if len(coords) < 3:
            # Fallback: too few nodes, draw a circle buffer representing nominal distance
            dist_meters = walk_minutes * (walk_speed_kmh * 1000 / 60)
            deg_buffer = dist_meters / 111000.0
            polygon = Point(lng, lat).buffer(deg_buffer)
        else:
            mp = MultiPoint(coords)
            # ratio=0.3 is optimal for urban walking contours. 
            # 0.0 is tightest concave hull, 1.0 is convex hull.
            polygon = concave_hull(mp, ratio=0.3, allow_holes=False)
            
            # Ensure it is a Polygon (if collinear, it might be a LineString or Point)
            if not isinstance(polygon, Polygon):
                polygon = polygon.buffer(0.0001)  # tiny buffer to make it a polygon
                
        # Snapping buffer: Union with buffer around pin coordinate to ensure it overlaps street node
        from backend.geo.spatial import haversine_distance
        from shapely import union
        center_node_lat = G.nodes[center_node]["y"]
        center_node_lng = G.nodes[center_node]["x"]
        dist_to_center = haversine_distance(lat, lng, center_node_lat, center_node_lng)
        buffer_dist_deg = (dist_to_center + 15.0) / 111000.0
        pin_buffer = Point(lng, lat).buffer(buffer_dist_deg)
        polygon = union(polygon, pin_buffer)

        # Return as GeoJSON dictionary
        return mapping(polygon)
    except Exception as e:
        logger.error(f"Error computing isochrone: {e}")
        # Return fallback buffer
        dist_meters = walk_minutes * (walk_speed_kmh * 1000 / 60)
        deg_buffer = dist_meters / 111000.0
        polygon = Point(lng, lat).buffer(deg_buffer)
        return mapping(polygon)

def compute_multi_ring_isochrone(G, lat, lng, ring_minutes=[5, 10, 15], walk_speed_kmh=DEFAULT_WALK_SPEED_KMH):
    """
    Compute multiple concentric isochrone rings.
    Returns a dictionary mapping minutes to GeoJSON geometries.
    """
    results = {}
    for mins in sorted(ring_minutes):
        results[mins] = compute_isochrone(G, lat, lng, mins, walk_speed_kmh)
    return results

def compute_isochrone_from_path(G, path_nodes, walk_minutes, walk_speed_kmh=DEFAULT_WALK_SPEED_KMH, pin_coords=None):
    """
    Compute a single walking isochrone polygon along a path of nodes.
    Returns a GeoJSON-like dictionary of the polygon geometry.
    """
    try:
        if not path_nodes:
            return None

        # Update graph edge travel times
        update_edge_times(G, walk_speed_kmh)
        
        # Get reachable nodes using multi-source Dijkstra
        lengths = nx.multi_source_dijkstra_path_length(G, path_nodes, cutoff=walk_minutes, weight="time")
        
        # Extract coordinates of reachable nodes
        coords = [(G.nodes[node]["x"], G.nodes[node]["y"]) for node in lengths]
        
        # Enrich coords with edge midpoints and geometries to keep street segments covered
        for u, v, k, data in G.edges(data=True, keys=True):
            if u in lengths and v in lengths:
                mx = (G.nodes[u]["x"] + G.nodes[v]["x"]) / 2
                my = (G.nodes[u]["y"] + G.nodes[v]["y"]) / 2
                coords.append((mx, my))
                if "geometry" in data:
                    for x, y in data["geometry"].coords:
                        coords.append((x, y))

        if len(coords) < 3:
            # Fallback: draw a buffered line/points representing the path
            dist_meters = walk_minutes * (walk_speed_kmh * 1000 / 60)
            deg_buffer = dist_meters / 111000.0
            
            # If path_nodes has at least 2 nodes, we can construct a LineString
            if len(path_nodes) >= 2:
                path_coords = [(G.nodes[n]["x"], G.nodes[n]["y"]) for n in path_nodes]
                polygon = LineString(path_coords).buffer(deg_buffer)
            else:
                # Fallback to single center point (first node)
                node = path_nodes[0]
                polygon = Point(G.nodes[node]["x"], G.nodes[node]["y"]).buffer(deg_buffer)
        else:
            mp = MultiPoint(coords)
            polygon = concave_hull(mp, ratio=0.3, allow_holes=False)
            
            if not isinstance(polygon, Polygon):
                polygon = polygon.buffer(0.0001)  # tiny buffer to make it a polygon
                
        # Snapping buffer: Union with buffer around pin coordinate to ensure it overlaps street node
        if pin_coords and path_nodes:
            from backend.geo.spatial import haversine_distance
            from shapely import union
            pin_lat, pin_lng = pin_coords
            
            min_dist = 999999.0
            for node in path_nodes:
                node_lat = G.nodes[node]["y"]
                node_lng = G.nodes[node]["x"]
                d = haversine_distance(pin_lat, pin_lng, node_lat, node_lng)
                if d < min_dist:
                    min_dist = d
                    
            buffer_dist_deg = (min_dist + 15.0) / 111000.0
            pin_buffer = Point(pin_lng, pin_lat).buffer(buffer_dist_deg)
            polygon = union(polygon, pin_buffer)

        return mapping(polygon)
    except Exception as e:
        logger.error(f"Error computing path isochrone: {e}")
        # Fallback buffer around path
        dist_meters = walk_minutes * (walk_speed_kmh * 1000 / 60)
        deg_buffer = dist_meters / 111000.0
        try:
            path_coords = [(G.nodes[n]["x"], G.nodes[n]["y"]) for n in path_nodes]
            if len(path_coords) >= 2:
                polygon = LineString(path_coords).buffer(deg_buffer)
            else:
                polygon = Point(path_coords[0][0], path_coords[0][1]).buffer(deg_buffer)
            return mapping(polygon)
        except Exception:
            return None

def compute_multi_ring_isochrone_from_path(G, path_nodes, ring_minutes=[5, 10, 15], walk_speed_kmh=DEFAULT_WALK_SPEED_KMH, pin_coords=None):
    """
    Compute multiple concentric isochrone rings along a path of nodes.
    Returns a dictionary mapping minutes to GeoJSON geometries.
    """
    results = {}
    for mins in sorted(ring_minutes):
        geom = compute_isochrone_from_path(G, path_nodes, mins, walk_speed_kmh, pin_coords)
        if geom:
            results[mins] = geom
    return results
