import logging

logger = logging.getLogger(__name__)

def order_stations_on_line(stations):
    """
    Sort stations by GTFS Stop ID. For NYC Subway lines (especially A, C, 3),
    GTFS stop IDs are assigned alphabetically/numerically along the route from 
    terminus to terminus, which handles branches (e.g. Rockaway branches) 
    correctly and prevents them from intermixing with the main route segment.
    """
    valid_stations = [
        s for s in stations 
        if s.get("latitude") is not None and s.get("longitude") is not None and s.get("gtfs_stop_id") is not None
    ]
    # Sort by gtfs_stop_id alphabetically
    return sorted(valid_stations, key=lambda s: s["gtfs_stop_id"])

def get_stations_between(stations, home_gtfs_id: str, work_gtfs_id: str):
    """
    Given a list of stations serving a line, find all stations between
    the Home station and the Work station (inclusive).
    """
    ordered = order_stations_on_line(stations)
    
    home_idx = -1
    work_idx = -1
    
    for i, s in enumerate(ordered):
        stop_id = s.get("gtfs_stop_id")
        if stop_id == home_gtfs_id:
            home_idx = i
        if stop_id == work_gtfs_id:
            work_idx = i
            
    if home_idx == -1 or work_idx == -1:
        logger.warning(f"Could not find home ({home_gtfs_id}) or work ({work_gtfs_id}) in stations list.")
        return []
        
    start_idx = min(home_idx, work_idx)
    end_idx = max(home_idx, work_idx)
    
    return ordered[start_idx : end_idx + 1]
