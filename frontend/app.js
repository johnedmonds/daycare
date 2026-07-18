// --- State Management ---
let map;
let linesData = [];
let stationsData = [];
let routeStations = [];
let daycareMarkers = {};
let stationMarkers = {};
let isochroneLayers = [];
let homeMarker = null;
let workMarker = null;

let homeCoords = null;
let workCoords = null;
let pinMode = null; // 'home' or 'work' or null

// MTA Official Hex Colors lookup (matching backend)
const MTA_COLORS = {
    "A": "#0039A6", "C": "#0039A6", "E": "#0039A6",
    "1": "#EE352E", "2": "#EE352E", "3": "#EE352E",
    "B": "#FF6319", "D": "#FF6319", "F": "#FF6319", "M": "#FF6319",
    "G": "#6CBE45", "L": "#A7A9AC",
    "J": "#996633", "Z": "#996633",
    "N": "#FCCC0A", "Q": "#FCCC0A", "R": "#FCCC0A", "W": "#FCCC0A",
    "7": "#B933AD", "S": "#808080"
};

// Isochrone ring styles
const ISOCHRONE_STYLES = {
    5: { color: "#10b981", fillColor: "#10b981", weight: 1.5, fillOpacity: 0.18 },
    10: { color: "#f59e0b", fillColor: "#f59e0b", weight: 1.5, fillOpacity: 0.12 },
    15: { color: "#ef4444", fillColor: "#ef4444", weight: 1.5, fillOpacity: 0.08 }
};

// Layer Groups
let stationsLayerGroup;
let isochronesLayerGroup;
let daycaresLayerGroup;
let pinsLayerGroup;
let routeLineLayer;
let homeWalkLineLayer;
let workWalkLineLayer;

// --- Initialize App ---
document.addEventListener("DOMContentLoaded", () => {
    initMap();
    fetchLines();
    setupCoordsPasteListeners();
    lucide.createIcons();
});

// --- Map Setup ---
function initMap() {
    // Center on NYC (Nostrand Ave / central Brooklyn area)
    map = L.map("map", {
        zoomControl: false
    }).setView([40.7128, -73.9600], 12);

    L.control.zoom({
        position: 'topright'
    }).addTo(map);

    // Dark Matter Map Tiles
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 20
    }).addTo(map);

    // Initialize layer groups
    stationsLayerGroup = L.layerGroup().addTo(map);
    isochronesLayerGroup = L.layerGroup().addTo(map);
    daycaresLayerGroup = L.layerGroup().addTo(map);
    pinsLayerGroup = L.layerGroup().addTo(map);
    routeLineLayer = L.polyline([], { color: '#3b82f6', weight: 4, opacity: 0.6, dashArray: '8, 8' }).addTo(map);
    homeWalkLineLayer = L.polyline([], { color: '#10b981', weight: 4, opacity: 0.8, dashArray: '5, 5' }).addTo(map);
    workWalkLineLayer = L.polyline([], { color: '#a855f7', weight: 4, opacity: 0.8, dashArray: '5, 5' }).addTo(map);

    // Map click handler for placing custom pins
    map.on("click", (e) => {
        if (pinMode === "home") {
            setHomePin(e.latlng.lat, e.latlng.lng);
        } else if (pinMode === "work") {
            setWorkPin(e.latlng.lat, e.latlng.lng);
        }
    });
}

// --- Fetch Subway Lines ---
async function fetchLines() {
    try {
        const response = await fetch("/api/lines");
        const data = await response.json();
        linesData = data.lines;
        
        const select = document.getElementById("subway-line");
        select.innerHTML = '<option value="">Select Line...</option>';
        
        linesData.forEach(line => {
            const opt = document.createElement("option");
            opt.value = line;
            opt.textContent = `${line} Train`;
            select.appendChild(opt);
        });
    } catch (e) {
        console.error("Error fetching subway lines:", e);
    }
}

// --- Subway Line Selection Changed ---
async function onLineChanged() {
    const line = document.getElementById("subway-line").value;
    const homeSelect = document.getElementById("home-station");
    const workSelect = document.getElementById("work-station");
    
    // Clear existing selections and map elements
    homeSelect.innerHTML = '<option value="">Select Home Station...</option>';
    workSelect.innerHTML = '<option value="">Select Work Station...</option>';
    homeSelect.disabled = true;
    workSelect.disabled = true;
    
    clearSearchLayers();
    stationsLayerGroup.clearLayers();
    stationMarkers = {};
    
    if (!line) return;
    
    try {
        const response = await fetch(`/api/stations?line=${line}`);
        const data = await response.json();
        stationsData = data.stations;
        
        // Populate dropdowns
        homeSelect.innerHTML = '<option value="">Select Home Station...</option>';
        workSelect.innerHTML = '<option value="">Select Work Station...</option>';
        
        stationsData.forEach(station => {
            const optHome = document.createElement("option");
            optHome.value = station.gtfs_stop_id;
            optHome.textContent = station.station_name;
            homeSelect.appendChild(optHome);
            
            const optWork = document.createElement("option");
            optWork.value = station.gtfs_stop_id;
            optWork.textContent = station.station_name;
            workSelect.appendChild(optWork);
        });
        
        homeSelect.disabled = false;
        workSelect.disabled = false;
        
        // Plot all stations on map (gray style initially)
        const lineColor = MTA_COLORS[line] || "#ffffff";
        stationsData.forEach(station => {
            const marker = L.circleMarker([station.latitude, station.longitude], {
                radius: 5,
                color: "#1f2937",
                fillColor: lineColor,
                fillOpacity: 0.6,
                weight: 1.5
            }).addTo(stationsLayerGroup);
            
            marker.bindPopup(`<b>${station.station_name}</b><br>${station.daytime_routes} Train(s)`);
            stationMarkers[station.gtfs_stop_id] = marker;
        });
        
        // Adjust map bounds to cover all line stations
        if (stationsData.length > 0) {
            const bounds = L.latLngBounds(stationsData.map(s => [s.latitude, s.longitude]));
            map.fitBounds(bounds, { padding: [50, 50] });
        }
    } catch (e) {
        console.error("Error loading stations:", e);
    }
}

// --- Stations Selection Changed ---
function onStationsChanged() {
    const line = document.getElementById("subway-line").value;
    const homeVal = document.getElementById("home-station").value;
    const workVal = document.getElementById("work-station").value;
    
    // Reset all station markers style
    const lineColor = MTA_COLORS[line] || "#ffffff";
    Object.values(stationMarkers).forEach(marker => {
        marker.setStyle({
            radius: 5,
            color: "#1f2937",
            fillColor: lineColor,
            fillOpacity: 0.6,
            weight: 1.5
        });
    });
    
    routeLineLayer.setLatLngs([]);
    
    if (homeVal && workVal) {
        // Find route stations
        const homeIdx = stationsData.findIndex(s => s.gtfs_stop_id === homeVal);
        const workIdx = stationsData.findIndex(s => s.gtfs_stop_id === workVal);
        
        if (homeIdx !== -1 && workIdx !== -1) {
            const start = Math.min(homeIdx, workIdx);
            const end = Math.max(homeIdx, workIdx);
            routeStations = stationsData.slice(start, end + 1);
            
            // Highlight route stations
            routeStations.forEach(station => {
                const marker = stationMarkers[station.gtfs_stop_id];
                if (marker) {
                    marker.setStyle({
                        radius: 8,
                        color: "#ffffff",
                        fillColor: lineColor,
                        fillOpacity: 0.9,
                        weight: 2
                    });
                }
            });
            
            // Special styling for endpoints
            const homeMarkerObj = stationMarkers[homeVal];
            if (homeMarkerObj) homeMarkerObj.setStyle({ radius: 10, color: "#10b981", weight: 3 });
            const workMarkerObj = stationMarkers[workVal];
            if (workMarkerObj) workMarkerObj.setStyle({ radius: 10, color: "#a855f7", weight: 3 });
            
            // Draw connection route line
            const latlngs = routeStations.map(s => [s.latitude, s.longitude]);
            routeLineLayer.setLatLngs(latlngs);
            routeLineLayer.setStyle({ color: lineColor });
            
            // Fit bounds to the corridor
            map.fitBounds(L.latLngBounds(latlngs), { padding: [80, 80] });
        }
    }
}

// --- Toggle Pin Mode (Home / Work) ---
function togglePinMode(type) {
    const homeBtn = document.getElementById("btn-pin-home");
    const workBtn = document.getElementById("btn-pin-work");
    
    if (type === "home") {
        if (pinMode === "home") {
            pinMode = null;
            homeBtn.classList.remove("active");
            map.getContainer().style.cursor = "";
        } else {
            pinMode = "home";
            homeBtn.classList.add("active");
            workBtn.classList.remove("active");
            map.getContainer().style.cursor = "crosshair";
        }
    } else if (type === "work") {
        if (pinMode === "work") {
            pinMode = null;
            workBtn.classList.remove("active");
            map.getContainer().style.cursor = "";
        } else {
            pinMode = "work";
            workBtn.classList.add("active");
            homeBtn.classList.remove("active");
            map.getContainer().style.cursor = "crosshair";
        }
    }
}

// --- Set Custom Pins ---
function setHomePin(lat, lng, updateInputs = true) {
    homeCoords = [lat, lng];
    pinMode = null;
    document.getElementById("btn-pin-home").classList.remove("active");
    map.getContainer().style.cursor = "";
    
    if (updateInputs) {
        document.getElementById("home-lat").value = parseFloat(lat).toFixed(6);
        document.getElementById("home-lng").value = parseFloat(lng).toFixed(6);
    }
    
    if (homeMarker) pinsLayerGroup.removeLayer(homeMarker);
    
    homeMarker = L.marker([lat, lng], {
        icon: L.divIcon({
            className: 'custom-pin home-pin',
            html: '<div style="background-color: #10b981; width: 14px; height: 14px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 10px rgba(16, 185, 129, 0.6)"></div>',
            iconSize: [14, 14],
            iconAnchor: [7, 7]
        })
    }).addTo(pinsLayerGroup);
    homeMarker.bindPopup("<b>Home Location Pin</b>");
}

function setWorkPin(lat, lng, updateInputs = true) {
    workCoords = [lat, lng];
    pinMode = null;
    document.getElementById("btn-pin-work").classList.remove("active");
    map.getContainer().style.cursor = "";
    
    if (updateInputs) {
        document.getElementById("work-lat").value = parseFloat(lat).toFixed(6);
        document.getElementById("work-lng").value = parseFloat(lng).toFixed(6);
    }
    
    if (workMarker) pinsLayerGroup.removeLayer(workMarker);
    
    workMarker = L.marker([lat, lng], {
        icon: L.divIcon({
            className: 'custom-pin work-pin',
            html: '<div style="background-color: #a855f7; width: 14px; height: 14px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 10px rgba(168, 85, 247, 0.6)"></div>',
            iconSize: [14, 14],
            iconAnchor: [7, 7]
        })
    }).addTo(pinsLayerGroup);
    workMarker.bindPopup("<b>Work Location Pin</b>");
}

// --- Coordinate Manual Inputs & Clearing ---
function onCoordsInput(type) {
    const latInput = document.getElementById(`${type}-lat`);
    const lngInput = document.getElementById(`${type}-lng`);
    const lat = parseFloat(latInput.value);
    const lng = parseFloat(lngInput.value);
    
    if (!isNaN(lat) && !isNaN(lng)) {
        // Validation: Must be roughly near/within greater New York region
        if (lat >= 40.0 && lat <= 41.5 && lng >= -74.5 && lng <= -73.0) {
            if (type === "home") {
                setHomePin(lat, lng, false);
            } else if (type === "work") {
                setWorkPin(lat, lng, false);
            }
        }
    }
}

function clearPin(type) {
    if (type === "home") {
        homeCoords = null;
        if (homeMarker) {
            pinsLayerGroup.removeLayer(homeMarker);
            homeMarker = null;
        }
        document.getElementById("home-lat").value = "";
        document.getElementById("home-lng").value = "";
        document.getElementById("btn-pin-home").classList.remove("active");
    } else if (type === "work") {
        workCoords = null;
        if (workMarker) {
            pinsLayerGroup.removeLayer(workMarker);
            workMarker = null;
        }
        document.getElementById("work-lat").value = "";
        document.getElementById("work-lng").value = "";
        document.getElementById("btn-pin-work").classList.remove("active");
    }
}

// --- Clipboard Coordinate Paste Handling ---
function setupCoordsPasteListeners() {
    ["home", "work"].forEach(type => {
        ["lat", "lng"].forEach(coord => {
            const input = document.getElementById(`${type}-${coord}`);
            if (input) {
                input.addEventListener("paste", (e) => handleCoordsPaste(e, type));
            }
        });
    });
}

function handleCoordsPaste(event, type) {
    const clipboardData = event.clipboardData || window.clipboardData;
    if (!clipboardData) return;
    
    const pastedText = clipboardData.getData("text");
    if (!pastedText) return;
    
    // Check if the pasted text has a comma (common format from Google Maps is "lat, lng")
    if (pastedText.includes(",")) {
        const parts = pastedText.split(",");
        if (parts.length >= 2) {
            const lat = parseFloat(parts[0].trim());
            const lng = parseFloat(parts[1].trim());
            
            if (!isNaN(lat) && !isNaN(lng)) {
                // Validation: Must be roughly near/within greater New York region
                if (lat >= 40.0 && lat <= 41.5 && lng >= -74.5 && lng <= -73.0) {
                    event.preventDefault(); // Stop normal single-input paste
                    
                    if (type === "home") {
                        setHomePin(lat, lng);
                    } else if (type === "work") {
                        setWorkPin(lat, lng);
                    }
                }
            }
        }
    }
}


// --- Clear Layer Groups ---
function clearSearchLayers() {
    isochronesLayerGroup.clearLayers();
    daycaresLayerGroup.clearLayers();
    daycareMarkers = {};
    isochroneLayers = [];
    document.getElementById("results-count").classList.add("hidden");
    document.getElementById("results-count").textContent = "0";
    if (homeWalkLineLayer) homeWalkLineLayer.setLatLngs([]);
    if (workWalkLineLayer) workWalkLineLayer.setLatLngs([]);
}

// --- TRIGGER SEARCH ---
async function triggerSearch() {
    const line = document.getElementById("subway-line").value;
    const homeVal = document.getElementById("home-station").value;
    const workVal = document.getElementById("work-station").value;
    const walkTime = parseInt(document.getElementById("walk-time").value);
    const walkSpeed = parseFloat(document.getElementById("walk-speed").value);
    const acceptsInfantsOnly = document.getElementById("infant-filter").checked;
    
    if (!line || !homeVal || !workVal) {
        alert("Please configure subway line, home station, and work station first.");
        return;
    }
    
    // UI Loading state
    const searchBtn = document.getElementById("search-btn");
    const spinner = document.getElementById("search-spinner");
    const progressArea = document.getElementById("progress-area");
    const progressFill = document.getElementById("progress-fill");
    
    searchBtn.disabled = true;
    spinner.classList.remove("hidden");
    progressArea.classList.remove("hidden");
    progressFill.style.width = "10%";
    
    clearSearchLayers();
    
    // Switch to results tab to show progress
    switchTab("results");
    
    const list = document.getElementById("results-list");
    list.innerHTML = `
        <div class="placeholder-state">
            <div class="spinner" style="width: 32px; height: 32px; border-color: rgba(59, 130, 246, 0.15); border-top-color: var(--color-primary);"></div>
            <h3>Analyzing corridors...</h3>
            <p id="loading-subtext">Computing walking geometries along your route. This is computed entirely locally using your CPU graph library.</p>
        </div>
    `;
    
    const body = {
        line: line,
        home_station_id: homeVal,
        work_station_id: workVal,
        walk_time_mins: walkTime,
        walk_speed_kmh: walkSpeed,
        home_coords: homeCoords,
        work_coords: workCoords,
        accepts_infants_only: acceptsInfantsOnly
    };
    
    try {
        progressFill.style.width = "40%";
        document.getElementById("progress-text").textContent = "Filtering daycares & routing paths...";
        
        const response = await fetch("/api/search", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(body)
        });
        
        progressFill.style.width = "80%";
        document.getElementById("progress-text").textContent = "Mapping walk limits...";
        
        if (!response.ok) {
            throw new Error(await response.text());
        }
        
        const data = await response.json();
        renderResults(data, walkTime, acceptsInfantsOnly);
        
        progressFill.style.width = "100%";
        document.getElementById("progress-text").textContent = "Analysis complete!";
        
        setTimeout(() => {
            progressArea.classList.add("hidden");
        }, 1500);
        
    } catch (e) {
        console.error(e);
        alert("Search failed: " + e.message);
        list.innerHTML = `
            <div class="placeholder-state" style="color: var(--color-danger)">
                <div class="icon">⚠️</div>
                <h3>Calculation Error</h3>
                <p>${e.message}</p>
            </div>
        `;
        progressArea.classList.add("hidden");
    } finally {
        searchBtn.disabled = false;
        spinner.classList.add("hidden");
    }
}

// --- Render Results ---
function renderResults(data, maxWalkTime, acceptsInfantsOnly) {
    const list = document.getElementById("results-list");
    list.innerHTML = "";
    
    // Update header summary metrics
    document.getElementById("summary-total").textContent = data.daycares.length;
    document.getElementById("summary-infant").textContent = acceptsInfantsOnly ? "Infants" : "All Ages";
    document.getElementById("summary-budget").textContent = `${maxWalkTime} min`;
    
    const countBadge = document.getElementById("results-count");
    countBadge.classList.remove("hidden");
    countBadge.textContent = data.daycares.length;
    
    if (data.daycares.length === 0) {
        list.innerHTML = `
            <div class="placeholder-state">
                <div class="icon">🔍</div>
                <h3>No convenient daycares found</h3>
                <p>Try increasing your walk budget, placing home/work pins, or checking the "Infant Care" option to broaden your reach.</p>
            </div>
        `;
        return;
    }
    
    // Draw walking paths if available
    if (homeWalkLineLayer) homeWalkLineLayer.setLatLngs([]);
    if (workWalkLineLayer) workWalkLineLayer.setLatLngs([]);
    if (data.walking_paths) {
        if (data.walking_paths.home_walk && homeWalkLineLayer) {
            homeWalkLineLayer.setLatLngs(data.walking_paths.home_walk);
        }
        if (data.walking_paths.work_walk && workWalkLineLayer) {
            workWalkLineLayer.setLatLngs(data.walking_paths.work_walk);
        }
    }

    // 1. Draw Isochrones on Map
    Object.entries(data.isochrones).forEach(([sourceId, rings]) => {
        // Sort rings in reverse so largest rings (15m) are drawn first (in the background)
        // and smallest rings (5m) are drawn on top.
        const sortedRings = Object.entries(rings).sort((a, b) => parseInt(b[0]) - parseInt(a[0]));
        
        sortedRings.forEach(([minsStr, geom]) => {
            const mins = parseInt(minsStr);
            const style = ISOCHRONE_STYLES[mins] || { color: "#ffffff", fillColor: "#ffffff", weight: 1, fillOpacity: 0.1 };
            
            // Convert to Leaflet GeoJSON layer
            const layer = L.geoJSON(geom, {
                style: {
                    ...style,
                    // If source is Home or Work, use alternate styling
                    color: sourceId === "home" ? "#10b981" : (sourceId === "work" ? "#a855f7" : style.color),
                    fillColor: sourceId === "home" ? "#10b981" : (sourceId === "work" ? "#a855f7" : style.fillColor)
                }
            }).addTo(isochronesLayerGroup);
            
            isochroneLayers.push(layer);
        });
    });

    // 2. Draw Daycares and Populate List
    data.daycares.forEach(dc => {
        // Map marker
        const isInfant = dc.age_range && dc.age_range.toUpperCase().includes("0 YEARS");
        
        // Color badge by added commute time
        let addedTimeClass = "";
        if (dc.added_commute_time <= 8) {
            addedTimeClass = "";
        } else if (dc.added_commute_time <= 15) {
            addedTimeClass = "warning";
        } else {
            addedTimeClass = "danger";
        }
        
        const popupContent = `
            <div>
                <h3>${dc.program_name}</h3>
                <p><b>Address:</b> ${dc.address}, ${dc.borough}</p>
                <p><b>Phone:</b> ${dc.phone || 'N/A'}</p>
                <p><b>Age Group:</b> ${dc.age_range || 'Unknown'}</p>
                <p><b>Capacity:</b> ${dc.capacity} children</p>
                <p><b>Commute Detour:</b> <span style="font-weight: 800; color: ${addedTimeClass === "danger" ? "var(--color-danger)" : (addedTimeClass === "warning" ? "var(--color-warning)" : "var(--color-success)")}">+${dc.added_commute_time} min</span></p>
            </div>
        `;
        
        const marker = L.circleMarker([dc.latitude, dc.longitude], {
            radius: 6,
            color: "#ffffff",
            fillColor: "#10b981",
            fillOpacity: 0.85,
            weight: 1.5
        }).addTo(daycaresLayerGroup);
        
        marker.bindPopup(popupContent);
        daycareMarkers[dc.dcid] = marker;
          // Generate list card HTML
        const card = document.createElement("div");
        card.className = "daycare-card";
        card.id = `card-${dc.dcid}`;
        
        // Match label/source description
        let sourceDesc = "";
        if (dc.nearest_source_id === "home") {
            sourceDesc = "Near Home";
        } else if (dc.nearest_source_id === "work") {
            sourceDesc = "Near Work";
        } else {
            // Find station name
            const station = data.stations.find(s => s.gtfs_stop_id === dc.nearest_source_id);
            sourceDesc = station ? `Off ${station.station_name}` : "Commute Stop";
        }
        
        const totalVio = dc.safety_metrics ? dc.safety_metrics.total_violations : 0;
        
        card.innerHTML = `
            <div class="card-header">
                <h4 class="card-title">${dc.program_name}</h4>
                <span class="time-badge ${addedTimeClass}">+${dc.added_commute_time} min</span>
            </div>
            <div class="card-details">
                <p><i data-lucide="map-pin"></i> ${dc.address}</p>
                <p><i data-lucide="baby"></i> ${dc.age_range || 'Age info unavailable'}</p>
                <p><i data-lucide="phone"></i> ${dc.phone || 'No phone'}</p>
                <p><i data-lucide="users"></i> Cap: ${dc.capacity || 'N/A'}</p>
            </div>
            
            <!-- Expanded Section -->
            <div class="card-body-expanded">
                <!-- Tabs Navigation -->
                <div class="card-expanded-tabs">
                    <button class="expanded-tab-btn active" id="tab-btn-overview-${dc.dcid}">Overview</button>
                    <button class="expanded-tab-btn" id="tab-btn-safety-${dc.dcid}">Safety & Staff</button>
                    <button class="expanded-tab-btn" id="tab-btn-violations-${dc.dcid}">Violations (${totalVio})</button>
                </div>
                
                <!-- Tab Contents -->
                <!-- 1. OVERVIEW TAB -->
                <div class="expanded-tab-content active" id="content-overview-${dc.dcid}">
                    <div class="overview-list">
                        <div class="overview-item"><i data-lucide="building"></i> <span><b>Borough:</b> ${dc.borough || 'N/A'}</span></div>
                        <div class="overview-item"><i data-lucide="hash"></i> <span><b>Permit #:</b> ${dc.permit_number || 'N/A'}</span></div>
                        <div class="overview-item"><i data-lucide="shield-check"></i> <span><b>Type:</b> ${dc.facility_type || 'N/A'} (${dc.program_type || 'N/A'})</span></div>
                        <div class="overview-item"><i data-lucide="baby"></i> <span><b>Age Limit:</b> ${dc.age_range || 'N/A'}</span></div>
                    </div>
                    
                    <div class="action-buttons">
                        <a href="https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(dc.program_name + ' ' + dc.address + ' ' + dc.borough + ' NY')}" 
                           target="_blank" class="action-btn action-btn-primary" onclick="event.stopPropagation();">
                            <i data-lucide="navigation"></i> Directions
                        </a>
                        <a href="https://www.google.com/search?q=${encodeURIComponent(dc.program_name + ' ' + dc.borough + ' daycare reviews tours')}" 
                           target="_blank" class="action-btn action-btn-secondary" onclick="event.stopPropagation();">
                            <i data-lucide="search"></i> Reviews & Tours
                        </a>
                    </div>
                </div>
                
                <!-- 2. SAFETY & STAFF TAB -->
                <div class="expanded-tab-content" id="content-safety-${dc.dcid}">
                    ${renderSafetyTabHTML(dc)}
                </div>
                
                <!-- 3. VIOLATIONS TAB -->
                <div class="expanded-tab-content" id="content-violations-${dc.dcid}">
                    ${renderViolationsTabHTML(dc)}
                </div>
            </div>
            
            <div class="card-footer">
                <span class="source-indicator">${sourceDesc}</span>
                <span class="expand-prompt" style="font-size: 11px; color: var(--color-primary); font-weight: 600;">Click to see details</span>
            </div>
        `;
        
        // Card hover events to highlight map markers
        card.addEventListener("mouseenter", () => highlightDaycare(dc.dcid));
        card.addEventListener("mouseleave", () => unhighlightDaycare(dc.dcid));
        card.addEventListener("click", (e) => {
            // Expand card
            toggleCardExpanded(dc.dcid);
            
            // Map actions
            highlightDaycare(dc.dcid);
            const m = daycareMarkers[dc.dcid];
            if (m) {
                m.openPopup();
                map.setView(m.getLatLng(), 15);
            }
        });
        
        // Set up tab click handlers inside the card
        setTimeout(() => {
            const tabOverviewBtn = document.getElementById(`tab-btn-overview-${dc.dcid}`);
            const tabSafetyBtn = document.getElementById(`tab-btn-safety-${dc.dcid}`);
            const tabViolationsBtn = document.getElementById(`tab-btn-violations-${dc.dcid}`);

            const contentOverview = document.getElementById(`content-overview-${dc.dcid}`);
            const contentSafety = document.getElementById(`content-safety-${dc.dcid}`);
            const contentViolations = document.getElementById(`content-violations-${dc.dcid}`);

            if (tabOverviewBtn && tabSafetyBtn && tabViolationsBtn) {
                function switchCardTab(tabName) {
                    [tabOverviewBtn, tabSafetyBtn, tabViolationsBtn].forEach(btn => btn.classList.remove("active"));
                    [contentOverview, contentSafety, contentViolations].forEach(content => content.classList.remove("active"));
                    
                    if (tabName === "overview") {
                        tabOverviewBtn.classList.add("active");
                        contentOverview.classList.add("active");
                    } else if (tabName === "safety") {
                        tabSafetyBtn.classList.add("active");
                        contentSafety.classList.add("active");
                    } else if (tabName === "violations") {
                        tabViolationsBtn.classList.add("active");
                        contentViolations.classList.add("active");
                    }
                }

                tabOverviewBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    switchCardTab("overview");
                });
                tabSafetyBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    switchCardTab("safety");
                });
                tabViolationsBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    switchCardTab("violations");
                });
            }
        }, 0);
        
        list.appendChild(card);
    });
    
    // Fit map bounds to cover route stations and daycares found
    const allGeoms = [];
    data.stations.forEach(s => allGeoms.push([s.latitude, s.longitude]));
    data.daycares.forEach(d => allGeoms.push([d.latitude, d.longitude]));
    if (homeCoords) allGeoms.push(homeCoords);
    if (workCoords) allGeoms.push(workCoords);
    
    if (allGeoms.length > 0) {
        map.fitBounds(L.latLngBounds(allGeoms), { padding: [50, 50] });
    }
    
    lucide.createIcons();
}

// --- Card Hover Highlighting ---
function highlightDaycare(dcid) {
    const marker = daycareMarkers[dcid];
    if (marker) {
        marker.setStyle({
            radius: 12,
            color: "#ffffff",
            fillColor: "#f59e0b", // pulse yellow on highlight
            weight: 3
        });
        marker.bringToFront();
    }
    
    const card = document.getElementById(`card-${dcid}`);
    if (card) {
        card.classList.add("highlighted");
    }
}

function unhighlightDaycare(dcid) {
    const marker = daycareMarkers[dcid];
    if (marker) {
        marker.setStyle({
            radius: 6,
            color: "#ffffff",
            fillColor: "#10b981",
            weight: 1.5
        });
    }
    
    const card = document.getElementById(`card-${dcid}`);
    if (card) {
        card.classList.remove("highlighted");
    }
}

// --- Switch Tabs ---
function switchTab(tab) {
    const ctrlBtn = document.getElementById("tab-btn-controls");
    const resBtn = document.getElementById("tab-btn-results");
    const ctrlTab = document.getElementById("tab-controls");
    const resTab = document.getElementById("tab-results");
    
    if (tab === "controls") {
        ctrlBtn.classList.add("active");
        resBtn.classList.remove("active");
        ctrlTab.classList.add("active");
        resTab.classList.remove("active");
    } else {
        ctrlBtn.classList.remove("active");
        resBtn.classList.add("active");
        ctrlTab.classList.remove("active");
        resTab.classList.add("active");
    }
}

// --- Mobile Navigation Drawer Toggle ---
function toggleSidebar() {
    const sidebar = document.getElementById("sidebar");
    const toggleBtn = document.getElementById("mobile-toggle-btn");
    
    sidebar.classList.toggle("collapsed");
    
    const isCollapsed = sidebar.classList.contains("collapsed");
    toggleBtn.innerHTML = isCollapsed ? '<i data-lucide="menu"></i>' : '<i data-lucide="x"></i>';
    lucide.createIcons();
}

// --- Toggle Daycare Card Expansion ---
function toggleCardExpanded(dcid) {
    const card = document.getElementById(`card-${dcid}`);
    if (!card) return;
    
    const isExpanded = card.classList.contains("expanded");
    
    // Collapse all other cards first
    document.querySelectorAll(".daycare-card.expanded").forEach(c => {
        if (c.id !== `card-${dcid}`) {
            c.classList.remove("expanded");
            const prompt = c.querySelector(".expand-prompt");
            if (prompt) prompt.textContent = "Click to see details";
        }
    });
    
    const prompt = card.querySelector(".expand-prompt");
    if (isExpanded) {
        card.classList.remove("expanded");
        if (prompt) prompt.textContent = "Click to see details";
    } else {
        card.classList.add("expanded");
        if (prompt) prompt.textContent = "Click to collapse";
        // Scroll card into view smoothly
        setTimeout(() => {
            card.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }, 100);
    }
}

// --- Render Safety Tab HTML ---
function renderSafetyTabHTML(dc) {
    const sm = dc.safety_metrics;
    if (!sm || sm.total_inspections === 0) {
        return `
            <div class="safety-grade-container">
                <span class="safety-label">Safety Status</span>
                <span class="safety-status-badge status-warning">No History</span>
            </div>
            <p style="font-size: 11.5px; color: var(--text-muted); text-align: center; margin-top: 20px;">
                No city inspections are cached for this daycare permit.
            </p>
        `;
    }
    
    // Safety score calculation
    let safetyStatus = "Passed";
    let safetyClass = "status-passed";
    if (sm.hazard_violations > 0) {
        safetyStatus = `${sm.hazard_violations} Health Hazard${sm.hazard_violations > 1 ? 's' : ''}`;
        safetyClass = "status-danger";
    } else if (sm.critical_violations > 0) {
        safetyStatus = `${sm.critical_violations} Critical Violation${sm.critical_violations > 1 ? 's' : ''}`;
        safetyClass = "status-warning";
    } else if (sm.total_violations > 0) {
        safetyStatus = `${sm.total_violations} General Violation${sm.total_violations > 1 ? 's' : ''}`;
        safetyClass = "status-warning";
    } else {
        safetyStatus = "Clean Record";
    }
    
    const latestDate = sm.latest_inspection_date 
        ? new Date(sm.latest_inspection_date).toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: 'numeric'}) 
        : "N/A";
    
    // Formulate rates comparison
    const r = sm.rates;
    const violationRateVal = r.violation_rate !== null ? `${r.violation_rate}%` : '0%';
    const avgViolationRateVal = r.avg_violation_rate !== null ? `${r.avg_violation_rate}%` : '21.9%';
    const criticalRateVal = r.critical_rate !== null ? `${r.critical_rate}%` : '0%';
    const avgCriticalRateVal = r.avg_critical_rate !== null ? `${r.avg_critical_rate}%` : '18.9%';
    
    // Staffing compare
    const st = sm.staffing;
    const staffText = st.total_workers !== null 
        ? `<b>${st.total_workers}</b> educational workers <span style="color: var(--text-dim)">(City avg: ${st.avg_workers || 11})</span>`
        : "Staffing data not reported";
        
    return `
        <div class="safety-grade-container">
            <span class="safety-label">Latest: ${latestDate}</span>
            <span class="safety-status-badge ${safetyClass}">${safetyStatus}</span>
        </div>
        <div class="metrics-comparison">
            <div class="metric-card">
                <div class="metric-label-row">
                    <span>Violation Rate</span>
                    <span class="metric-val-compare">Facility: ${violationRateVal} | City Avg: ${avgViolationRateVal}</span>
                </div>
                <div class="metric-bar-group">
                    <div class="progress-bar-container">
                        <div class="progress-bar-fill facility" style="width: ${r.violation_rate || 0}%; background-color: ${r.violation_rate > 21.9 ? 'var(--color-danger)' : 'var(--color-warning)'}"></div>
                    </div>
                </div>
            </div>
            
            <div class="metric-card">
                <div class="metric-label-row">
                    <span>Critical Violation Rate</span>
                    <span class="metric-val-compare">Facility: ${criticalRateVal} | City Avg: ${avgCriticalRateVal}</span>
                </div>
                <div class="metric-bar-group">
                    <div class="progress-bar-container">
                        <div class="progress-bar-fill facility-hazard" style="width: ${r.critical_rate || 0}%"></div>
                    </div>
                </div>
            </div>
            
            <div class="staffing-info">
                <i data-lucide="users"></i>
                <span>${staffText}</span>
            </div>
        </div>
    `;
}

// --- Render Violations Tab HTML ---
function renderViolationsTabHTML(dc) {
    const sm = dc.safety_metrics;
    if (!sm || !sm.violations || sm.violations.length === 0) {
        return `
            <div class="no-violations-state">
                <i data-lucide="shield-alert" style="color: var(--color-success); font-size: 24px; margin-bottom: 6px; display: block; text-align: center;"></i>
                <p style="text-align: center;">No active or historical violations recorded for this daycare.</p>
            </div>
        `;
    }
    
    let listHTML = "";
    sm.violations.forEach(v => {
        const vDate = v.date ? new Date(v.date).toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: 'numeric'}) : "N/A";
        
        let sevClass = "general";
        const catUpper = v.category.toUpperCase();
        if (catUpper.includes("HAZARD")) {
            sevClass = "hazard";
        } else if (catUpper.includes("CRITICAL")) {
            sevClass = "critical";
        }
        
        const statusClass = v.status.toUpperCase() === "CORRECTED" ? "status-corrected" : "status-open";
        
        listHTML += `
            <div class="violation-card">
                <div class="violation-header-row">
                    <span class="violation-date">${vDate}</span>
                    <span class="violation-severity-badge ${sevClass}">${v.category}</span>
                </div>
                <p class="violation-summary-text">${v.summary}</p>
                <div class="violation-status-row">
                    <span>Status: <span class="${statusClass}">${v.status}</span></span>
                </div>
            </div>
        `;
    });
    
    return `
        <div class="violations-scroller">
            ${listHTML}
        </div>
    `;
}
