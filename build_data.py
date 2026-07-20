import json
import logging
from pathlib import Path
import osmnx as ox

from backend.data.subway import fetch_stations
from backend.data.daycare import fetch_daycares, fetch_inspections, enrich_daycare_with_inspections
from backend.data.network import load_walk_network

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PUBLIC_DATA_DIR = Path("public/data")
PUBLIC_DATA_DIR.mkdir(parents=True, exist_ok=True)

def build_data():
    logger.info("Starting data build pipeline...")

    # 1. Subway Stations
    logger.info("Fetching and saving subway stations...")
    stations = fetch_stations()
    with open(PUBLIC_DATA_DIR / "stations.json", "w", encoding="utf-8") as f:
        json.dump(stations, f)
    logger.info(f"Saved {len(stations)} stations.")

    # 2. Daycares and Inspections
    logger.info("Fetching daycares and inspections...")
    daycares = fetch_daycares()
    inspections = fetch_inspections()

    # Pre-enrich daycares with inspections so the WASM app doesn't have to join them
    inspections_by_permit = {}
    for i in inspections:
        p = i.get("permit_number")
        if not p:
            continue
        if p not in inspections_by_permit:
            inspections_by_permit[p] = []
        inspections_by_permit[p].append(i)

    for dc in daycares:
        enrich_daycare_with_inspections(dc, inspections_by_permit)

    with open(PUBLIC_DATA_DIR / "daycares.json", "w", encoding="utf-8") as f:
        json.dump(daycares, f)
    logger.info(f"Saved {len(daycares)} daycares with safety metrics.")

    # 3. Walking Network Graph
    logger.info("Loading OSM walking network...")
    G = load_walk_network()

    logger.info("Exporting graph to lightweight JSON...")

    # We only need nodes (id, x, y) and edges (u, v, length, and maybe geometry for drawing paths)
    nodes = []
    # Create a mapping from old node ID to new 0-indexed ID for petgraph efficiency
    node_id_map = {}
    for i, (node_id, data) in enumerate(G.nodes(data=True)):
        node_id_map[node_id] = i
        nodes.append({
            "id": i,
            "x": data["x"],
            "y": data["y"]
        })

    edges = []
    for u, v, k, data in G.edges(data=True, keys=True):
        if u not in node_id_map or v not in node_id_map:
            continue

        edge_obj = {
            "u": node_id_map[u],
            "v": node_id_map[v],
            "length": data.get("length", 0.0)
        }

        # Extract geometry coords if present for more accurate path rendering
        if "geometry" in data:
            edge_obj["geometry"] = list(data["geometry"].coords)

        edges.append(edge_obj)

    graph_data = {
        "nodes": nodes,
        "edges": edges
    }

    with open(PUBLIC_DATA_DIR / "graph.json", "w", encoding="utf-8") as f:
        # Avoid indentation to keep file size down
        json.dump(graph_data, f)

    logger.info(f"Saved graph with {len(nodes)} nodes and {len(edges)} edges.")
    logger.info("Data build pipeline complete!")

if __name__ == "__main__":
    build_data()
