import os
import sys
import webbrowser
import threading
import time
import uvicorn
from pathlib import Path

# Add the project root to python path so backend packages are importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.config import CACHE_DIR, DEFAULT_BBOX
from backend.data.subway import fetch_stations
from backend.data.daycare import fetch_daycares, fetch_inspections
from backend.data.network import load_walk_network, GRAPHML_PATH

def init_data():
    print("==========================================================")
    print("        NYC Daycare Commute Finder — Boot Sequence        ")
    print("==========================================================")
    
    # Create cache dir if not exists
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Subway Stations
    print("[1/3] Checking NYC subway stations cache...", end="", flush=True)
    stations = fetch_stations()
    print(f" OK ({len(stations)} stations loaded)")
    
    # 2. Daycare Programs
    print("[2/3] Checking NYC daycare facilities cache...", end="", flush=True)
    daycares = fetch_daycares()
    print(f" OK ({len(daycares)} daycares loaded)")
    
    # 2.5 Daycare Inspections
    print("[2.5/3] Checking NYC daycare inspections cache...", end="", flush=True)
    inspections = fetch_inspections()
    print(f" OK ({len(inspections)} inspections loaded)")

    
    # 3. Walking Network Graph
    print("[3/3] Checking walking network cache...", end="", flush=True)
    if not GRAPHML_PATH.exists():
        print(" NOT FOUND.")
        print("\n--> Downloading the walking network corridor (Brooklyn to Upper Manhattan).")
        print("    This fetches data from OpenStreetMap. It will take 1-2 minutes...")
        try:
            # This triggers download
            load_walk_network(force_refresh=True)
            print("--> Download complete and saved to cache!")
        except Exception as e:
            print(f"\n[!] WARNING: Failed to download walking network: {e}")
            print("    The application will attempt to download it on first search request.")
    else:
        print(" OK (Found on disk)")
        
    print("\nInitialization complete! Starting FastAPI web server...")
    print("----------------------------------------------------------")

def open_browser():
    # Wait 1.5 seconds for the uvicorn server to bind and start
    time.sleep(1.5)
    url = "http://127.0.0.1:8000/"
    print(f"\n[*] Opening web browser to {url}...")
    webbrowser.open(url)

if __name__ == "__main__":
    # Initialize cache files and download graph if missing
    init_data()
    
    # Start uvicorn server, and open browser in a separate thread
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    # Run uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, log_level="info")
