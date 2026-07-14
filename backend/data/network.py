import osmnx as ox
import logging
from pathlib import Path
from backend.config import CACHE_DIR, DEFAULT_BBOX

GRAPHML_PATH = CACHE_DIR / "walk_network.graphml"
logger = logging.getLogger(__name__)

# Configure osmnx settings
ox.settings.use_cache = True
ox.settings.cache_folder = CACHE_DIR / "osm_cache"

def download_walk_network(bbox=DEFAULT_BBOX):
    """
    Download OSM walking network for a specific bounding box and save to GraphML.
    bbox format: (north, south, east, west)
    """
    logger.info(f"Downloading OSM walking network for bbox {bbox} (this may take 1-2 minutes)...")
    try:
        # Note: osmnx v2 uses a single bbox tuple: bbox=(north, south, east, west)
        G = ox.graph_from_bbox(bbox=bbox, network_type="walk", simplify=True)
        
        # Save to disk
        logger.info(f"Saving walking network graph to {GRAPHML_PATH}...")
        ox.io.save_graphml(G, filepath=GRAPHML_PATH)
        logger.info("Successfully saved walking network graph.")
        return G
    except Exception as e:
        logger.error(f"Failed to download walking network: {e}")
        raise e

def load_walk_network(force_refresh=False):
    """
    Load the cached walking network, or download it if it doesn't exist.
    """
    if not force_refresh and GRAPHML_PATH.exists():
        logger.info("Loading cached walking network from disk (this takes ~2-5 seconds)...")
        try:
            G = ox.io.load_graphml(filepath=GRAPHML_PATH)
            logger.info("Successfully loaded walking network from cache.")
            return G
        except Exception as e:
            logger.error(f"Error loading cached graphml: {e}. Downloading a fresh copy...")
            
    # Download and cache
    return download_walk_network()
