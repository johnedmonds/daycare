# NYC Daycare Commute Finder 🗽🎒

An interactive, commuter-focused daycare discovery tool for New York City. This application helps parents find daycare options along their daily commute by calculating stroller-pace walking networks and isochrones around home, work, and subway transit corridors, combined with real-time health department inspection histories.

---

## 🚀 Quick Start (Running the App)

The project uses [**`uv`**](https://github.com/astral-sh/uv), a blazing-fast Python package manager and resolver. If you have `uv` installed, you can bootstrap and start the application in a single command.

### 1. Run the application
From the root of the project directory, run:
```bash
uv run run.py
```

### What happens behind the scenes:
1. **Virtual Environment**: `uv` automatically creates a virtual environment (`.venv`) and installs the dependencies declared in [pyproject.toml](file:///c:/Users/pocke/Documents/daycare/pyproject.toml).
2. **Data Caching**: It downloads NYC subway stations, daycare facilities, and daycare health inspection records from public NYC/NYS Open Data portals.
3. **OpenStreetMap Download** *(First run only)*: It downloads the pedestrian routing network for the transit corridor (covering Brooklyn through Upper Manhattan). This step takes 1-2 minutes and is cached to disk as `walk_network.graphml` for sub-second subsequent loads.
4. **Web Server**: Starts a local FastAPI server on `http://127.0.0.1:8000/`.
5. **Auto-open**: Automatically opens your default web browser to the interface.

---

## 🛠️ Requirements & Installation Options

### Option A: Using `uv` (Highly Recommended)
If you don't have `uv` installed yet, install it via:
* **Windows (PowerShell)**:
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
* **macOS / Linux**:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

Once installed, just run `uv run run.py` inside the project folder.

### Option B: Using Standard Python Virtual Environments
If you prefer not to use `uv`, you can set up a standard Python virtual environment:

1. **Create and activate the environment**:
   * **Windows**:
     ```powershell
     python -m venv .venv
     .venv\Scripts\activate
     ```
   * **macOS / Linux**:
     ```bash
     python -m venv .venv
     source .venv/bin/activate
     ```

2. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install fastapi uvicorn osmnx networkx geopandas shapely requests scikit-learn
   ```

3. **Run the app**:
   ```bash
   python run.py
   ```

> [!NOTE]
> Setting up Geospatial libraries like `geopandas` and `osmnx` can sometimes be tricky on Windows due to binary dependencies (GDAL, PROJ, etc.). Using `uv` is recommended because it resolves and installs pre-compiled wheels seamlessly.

---

## 📁 Project Structure

```
daycare/
├── backend/                  # FastAPI Backend
│   ├── config.py             # Global constants, line colors, and API endpoints
│   ├── main.py               # API routes and server initialization
│   ├── cache/                # Cached data folder
│   │   ├── walk_network.graphml  # Pre-downloaded OSM walking corridors
│   │   └── isochrones/           # Cached travel calculations
│   └── data/                 # Data fetch & download utilities (subway, daycare, network)
├── frontend/                 # Client UI (served static by FastAPI)
│   ├── index.html            # Main Map UI layout
│   ├── styles.css            # Styling and visual interface layout
│   └── app.js                # Map interactions, route searching, and visualization logic
├── pyproject.toml            # Python dependencies and metadata
├── run.py                    # Entrypoint bootstrapping script
└── README.md                 # Project instructions (this file)
```

---

## 🌟 Key Features

* **Commute Corridors**: Map out your route (Home to Work) using NYC Subway lines.
* **Walking Isochrones**: See how far you can walk in 5, 10, or 15 minutes pushing a stroller (defaulting to a comfortable `4.0 km/h` pace) from your home, work, or any transit stop.
* **Inspection Details**: Instantly check daycare violation rates, inspection results, and health department statuses.
* **Smart Filtering**: Filter daycares by facility type, capacity, search radius, or minimum health rating.
