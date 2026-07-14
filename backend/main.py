import logging
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Tuple, Dict, Any

from backend.config import CACHE_DIR, DEFAULT_WALK_SPEED_KMH, DEFAULT_BBOX
from backend.data.subway import fetch_stations, get_stations_by_line, get_all_lines
from backend.data.daycare import fetch_daycares, filter_daycares
from backend.data.network import load_walk_network
from backend.geo.isochrone import compute_multi_ring_isochrone
from backend.geo.routing import get_stations_between, order_stations_on_line
from backend.geo.spatial import (
    find_daycares_in_isochrones, 
    calculate_added_commute_time, 
    estimate_walk_time
)

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="NYC Daycare Commute Finder API")

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global in-memory storage for the walking graph
# Loaded on startup or lazy-loaded
G_walk = None

@app.on_event("startup")
def startup_event():
    global G_walk
    try:
        # Load walking network. This will download on first run if cache missing.
        G_walk = load_walk_network()
        # Prime the cache for stations and daycares
        fetch_stations()
        fetch_daycares()
        logger.info("Application startup and data warming complete.")
    except Exception as e:
        logger.error(f"Error during startup: {e}")

class SearchRequest(BaseModel):
    line: str
    home_station_id: str
    work_station_id: str
    walk_time_mins: int  # 5, 10, or 15
    walk_speed_kmh: float = DEFAULT_WALK_SPEED_KMH
    home_coords: Optional[Tuple[float, float]] = None  # (lat, lng)
    work_coords: Optional[Tuple[float, float]] = None  # (lat, lng)
    accepts_infants_only: bool = False

@app.get("/api/lines")
def get_lines():
    """
    Get all unique subway lines available.
    """
    try:
        lines = get_all_lines()
        # Filter to make sure we only return main lines (1-7, A-G, J, L, N, Q, R, S, W, Z)
        valid_lines = sorted([l for l in lines if len(l) == 1 or l in ("SIR",)])
        return {"lines": valid_lines}
    except Exception as e:
        logger.error(f"Error in /api/lines: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stations")
def get_stations(line: str = Query(..., description="Subway line character, e.g. A, C, 3")):
    """
    Get all stations serving a line, ordered geographically (North to South).
    """
    try:
        stations = get_stations_by_line(line)
        if not stations:
            raise HTTPException(status_code=404, detail=f"No stations found for line {line}")
        
        ordered = order_stations_on_line(stations)
        return {
            "line": line,
            "stations": [
                {
                    "gtfs_stop_id": s.get("gtfs_stop_id"),
                    "station_name": s.get("station_name"),
                    "latitude": s.get("latitude"),
                    "longitude": s.get("longitude"),
                    "daytime_routes": s.get("daytime_routes")
                }
                for s in ordered
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /api/stations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search")
def search_daycares(req: SearchRequest):
    """
    Core search route:
    1. Finds stations on route
    2. Generates isochrones for route stations + home/work pins
    3. Finds daycares in those isochrones
    4. Calculates added commute time
    """
    global G_walk
    if G_walk is None:
        try:
            G_walk = load_walk_network()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Walking network not loaded: {e}")

    try:
        # 1. Get stations along the commute route
        stations_on_line = get_stations_by_line(req.line)
        route_stations = get_stations_between(stations_on_line, req.home_station_id, req.work_station_id)
        
        if not route_stations:
            raise HTTPException(status_code=400, detail="Invalid home or work station IDs for selected line")
            
        # Create lookups
        stations_by_id = {s["gtfs_stop_id"]: s for s in route_stations}
        home_station = stations_by_id.get(req.home_station_id)
        work_station = stations_by_id.get(req.work_station_id)
        
        home_station_coords = (home_station["latitude"], home_station["longitude"]) if home_station else None
        work_station_coords = (work_station["latitude"], work_station["longitude"]) if work_station else None

        # 2. Determine travel rings
        # Generate 5, 10, 15 minute rings depending on user's walk limit
        rings_to_generate = [5]
        if req.walk_time_mins >= 10:
            rings_to_generate.append(10)
        if req.walk_time_mins >= 15:
            rings_to_generate.append(15)

        # 3. Compute isochrones for all points
        isochrones_dict = {}
        
        # Route stations isochrones
        for station in route_stations:
            stop_id = station["gtfs_stop_id"]
            lat, lng = station["latitude"], station["longitude"]
            isochrones_dict[stop_id] = compute_multi_ring_isochrone(
                G_walk, lat, lng, 
                ring_minutes=rings_to_generate, 
                walk_speed_kmh=req.walk_speed_kmh
            )
            
        # Home pin isochrone
        if req.home_coords:
            isochrones_dict["home"] = compute_multi_ring_isochrone(
                G_walk, req.home_coords[0], req.home_coords[1], 
                ring_minutes=rings_to_generate, 
                walk_speed_kmh=req.walk_speed_kmh
            )
            
        # Work pin isochrone
        if req.work_coords:
            isochrones_dict["work"] = compute_multi_ring_isochrone(
                G_walk, req.work_coords[0], req.work_coords[1], 
                ring_minutes=rings_to_generate, 
                walk_speed_kmh=req.walk_speed_kmh
            )

        # 4. Fetch and filter daycares
        all_daycares = fetch_daycares()
        filtered_daycares = filter_daycares(all_daycares, accepts_infants_only=req.accepts_infants_only)
        
        # Find which daycares lie in the isochrones
        matched_daycares = find_daycares_in_isochrones(filtered_daycares, isochrones_dict)

        # 5. Calculate added commute times and enrich daycare results
        results = []
        for dc in matched_daycares:
            nearest_source = dc["nearest_source_id"]
            
            # Determine added time
            added_time = None
            
            if nearest_source == "home":
                added_time = calculate_added_commute_time(
                    dc, "home", 
                    home_coords=req.home_coords,
                    home_station_coords=home_station_coords,
                    walk_speed_kmh=req.walk_speed_kmh
                )
            elif nearest_source == "work":
                added_time = calculate_added_commute_time(
                    dc, "work", 
                    work_coords=req.work_coords,
                    work_station_coords=work_station_coords,
                    walk_speed_kmh=req.walk_speed_kmh
                )
            else:
                # Nearest source is a subway station on the route
                station = stations_by_id.get(nearest_source)
                if station:
                    # added_time = 2 * walk(station -> daycare) + train wait (4 mins)
                    walk_mins = estimate_walk_time(
                        station["latitude"], station["longitude"], 
                        dc["latitude"], dc["longitude"], 
                        req.walk_speed_kmh
                    )
                    added_time = round(2 * walk_mins + 4.0, 1)
            
            # Format display strings
            dc_res = {
                "dcid": dc.get("dcid"),
                "program_name": dc.get("program_name", "Unknown Daycare"),
                "address": dc.get("address", ""),
                "borough": dc.get("borough", ""),
                "zipcode": dc.get("zipcode", ""),
                "phone": dc.get("phone", ""),
                "age_range": dc.get("age_range", ""),
                "capacity": dc.get("capacity", 0),
                "facility_type": dc.get("facility_type", ""),
                "program_type": dc.get("program_type", ""),
                "latitude": dc["latitude"],
                "longitude": dc["longitude"],
                "nearest_source_id": nearest_source,
                "walk_ring_mins": dc["walk_ring_mins"],
                "added_commute_time": added_time
            }
            results.append(dc_res)
            
        # Sort results: daycares with smallest added commute time first
        # Handle cases where added_time might be None
        results.sort(key=lambda x: x["added_commute_time"] if x["added_commute_time"] is not None else 999.0)

        # 6. Format stations for response
        response_stations = [
            {
                "gtfs_stop_id": s["gtfs_stop_id"],
                "station_name": s["station_name"],
                "latitude": s["latitude"],
                "longitude": s["longitude"]
            }
            for s in route_stations
        ]

        return {
            "stations": response_stations,
            "isochrones": isochrones_dict,
            "daycares": results,
            "summary": {
                "total_found": len(results),
                "infant_only": req.accepts_infants_only,
                "walk_time_limit": req.walk_time_mins,
                "walk_speed_kmh": req.walk_speed_kmh
            }
        }
    except Exception as e:
        logger.error(f"Error during search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status")
def get_status():
    """
    Get caching status of the data files and walking network.
    """
    from backend.data.subway import STATIONS_CACHE_PATH
    from backend.data.daycare import DAYCARES_CACHE_PATH
    from backend.data.network import GRAPHML_PATH
    
    return {
        "subway_stations_cached": STATIONS_CACHE_PATH.exists(),
        "daycares_cached": DAYCARES_CACHE_PATH.exists(),
        "walk_network_cached": GRAPHML_PATH.exists(),
        "graph_loaded": G_walk is not None,
        "graph_nodes": len(G_walk.nodes) if G_walk else 0,
        "graph_edges": len(G_walk.edges) if G_walk else 0
    }

# Mount static files for the frontend at the root /
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
