import logging
import networkx as nx
import osmnx as ox
from shapely.geometry import MultiPoint, Polygon, Point, mapping
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
        
        if len(coords) < 3:
            # Fallback: too few nodes, draw a circle buffer representing nominal distance
            # walk_minutes * (walk_speed_kmh * 1000 / 60) gives meters
            # A rough conversion to degrees: 111,000 meters per degree
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
