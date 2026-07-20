use yew::prelude::*;
mod components;
mod engine;

use engine::{
    estimate_walk_time, haversine_distance, Daycare, RoutingEngine, Station, WalkNetwork,
};
use gloo_net::http::Request;
use std::rc::Rc;
use wasm_bindgen_futures::spawn_local;

#[function_component(App)]
fn app() -> Html {
    let stations = use_state(|| vec![]);
    let daycares = use_state(|| vec![]);
    let lines = use_state(|| vec![]);
    let routing_engine = use_state(|| None::<Rc<RoutingEngine>>);
    let engine_loading = use_state(|| false);
    let engine_ready = use_state(|| false);

    {
        let stations = stations.clone();
        let daycares = daycares.clone();
        let lines = lines.clone();
        use_effect_with((), move |_| {
            // Initialize Leaflet map safely now that DOM is definitely ready
            components::initMapFromRust();

            spawn_local(async move {
                if let Ok(resp) = Request::get("/data/stations.json").send().await {
                    if let Ok(data) = resp.json::<Vec<Station>>().await {
                        let mut unique_lines = std::collections::HashSet::new();
                        for s in &data {
                            if let Some(routes) = &s.daytime_routes {
                                for r in routes.split_whitespace() {
                                    unique_lines.insert(r.to_string());
                                }
                            }
                        }
                        let mut lines_vec: Vec<String> = unique_lines.into_iter().collect();
                        lines_vec.sort();
                        lines.set(lines_vec);
                        stations.set(data);
                    }
                }

                if let Ok(resp) = Request::get("/data/daycares.json").send().await {
                    if let Ok(data) = resp.json::<Vec<Daycare>>().await {
                        daycares.set(data);
                    }
                }
            });
            || ()
        });
    }

    let selected_line = use_state(|| "".to_string());
    let selected_home_station = use_state(|| "".to_string());
    let selected_work_station = use_state(|| "".to_string());
    let walk_time = use_state(|| 10);
    let walk_speed = use_state(|| 4.0);
    let infant_only = use_state(|| false);

    // Filter stations by line
    let current_line_stations: Vec<Station> = if selected_line.is_empty() {
        vec![]
    } else {
        let mut filtered = stations
            .iter()
            .filter(|s| {
                if let Some(routes) = &s.daytime_routes {
                    routes.split_whitespace().any(|r| r == *selected_line)
                } else {
                    false
                }
            })
            .cloned()
            .collect::<Vec<_>>();
        filtered.sort_by(|a, b| a.gtfs_stop_id.cmp(&b.gtfs_stop_id));
        filtered
    };

    let on_line_change = {
        let selected_line = selected_line.clone();
        let selected_home_station = selected_home_station.clone();
        let selected_work_station = selected_work_station.clone();
        Callback::from(move |line: String| {
            selected_line.set(line);
            selected_home_station.set("".to_string());
            selected_work_station.set("".to_string());
        })
    };

    let on_search = {
        let routing_engine = routing_engine.clone();
        let engine_loading = engine_loading.clone();
        let engine_ready = engine_ready.clone();
        let daycares = daycares.clone();
        let stations = stations.clone();
        let selected_home_station = selected_home_station.clone();
        let selected_work_station = selected_work_station.clone();
        let walk_time = walk_time.clone();
        let walk_speed = walk_speed.clone();
        let infant_only = infant_only.clone();

        Callback::from(move |_| {
            if selected_home_station.is_empty() || selected_work_station.is_empty() {
                log::warn!("Please select home and work stations.");
                return;
            }

            let routing_engine = routing_engine.clone();
            let engine_loading = engine_loading.clone();
            let engine_ready = engine_ready.clone();
            let daycares = daycares.clone();
            let stations = stations.clone();
            let walk_time = *walk_time;
            let walk_speed = *walk_speed;
            let infant_only = *infant_only;
            let home_id = selected_home_station.to_string();
            let work_id = selected_work_station.to_string();

            spawn_local(async move {
                // Load engine lazily
                if !*engine_ready && !*engine_loading {
                    engine_loading.set(true);
                    log::info!("Loading routing graph... this may take a moment.");

                    if let Ok(resp) = Request::get("/data/graph.json").send().await {
                        if let Ok(network) = resp.json::<WalkNetwork>().await {
                            let engine = RoutingEngine::new(network);
                            routing_engine.set(Some(Rc::new(engine)));
                            engine_ready.set(true);
                            log::info!("Routing graph loaded and RTree built.");
                        }
                    }
                    engine_loading.set(false);
                }

                // If it's loaded now, we can perform the search
                if *engine_ready {
                    log::info!("Executing search... filtering daycares.");
                    if let Some(engine) = &*routing_engine {
                        let mut results = vec![];

                        let home_stn = stations
                            .iter()
                            .find(|s| s.gtfs_stop_id.as_deref() == Some(&home_id));
                        let work_stn = stations
                            .iter()
                            .find(|s| s.gtfs_stop_id.as_deref() == Some(&work_id));

                        let (h_lat, h_lng) = if let Some(s) = home_stn {
                            (s.latitude, s.longitude)
                        } else {
                            return;
                        };
                        let (w_lat, w_lng) = if let Some(s) = work_stn {
                            (s.latitude, s.longitude)
                        } else {
                            return;
                        };

                        for dc in daycares.iter() {
                            if infant_only {
                                if let Some(age) = &dc.age_range {
                                    if !age.to_uppercase().contains("0 YEARS") {
                                        continue;
                                    }
                                } else {
                                    continue;
                                }
                            }

                            if let (Some(lat), Some(lng)) = (dc.latitude, dc.longitude) {
                                let mut best_added_time = 999.0;
                                let mut best_source = "".to_string();

                                // Test Home
                                let t_home = engine.walk_time(h_lat, h_lng, lat, lng, walk_speed);
                                if t_home <= walk_time as f64 {
                                    let added = t_home * 2.0; // Round trip from home station
                                    if added < best_added_time {
                                        best_added_time = added;
                                        best_source = "home".to_string();
                                    }
                                }

                                // Test Work
                                let t_work = engine.walk_time(w_lat, w_lng, lat, lng, walk_speed);
                                if t_work <= walk_time as f64 {
                                    let added = t_work * 2.0; // Round trip from work station
                                    if added < best_added_time {
                                        best_added_time = added;
                                        best_source = "work".to_string();
                                    }
                                }

                                if best_added_time <= walk_time as f64 * 2.0 {
                                    results.push(engine::DaycareResult {
                                        dcid: dc.dcid.clone(),
                                        program_name: dc.program_name.clone(),
                                        address: dc.address.clone(),
                                        borough: dc.borough.clone(),
                                        zipcode: dc.zipcode.clone(),
                                        phone: dc.phone.clone(),
                                        age_range: dc.age_range.clone(),
                                        capacity: dc.capacity,
                                        facility_type: dc.facility_type.clone(),
                                        program_type: dc.program_type.clone(),
                                        latitude: lat,
                                        longitude: lng,
                                        nearest_source_id: best_source,
                                        walk_ring_mins: walk_time,
                                        added_commute_time: (best_added_time * 10.0).round() / 10.0,
                                        permit_number: dc.permit_number.clone(),
                                        safety_metrics: dc.safety_metrics.clone(),
                                    });
                                }
                            }
                        }

                        results.sort_by(|a, b| {
                            a.added_commute_time
                                .partial_cmp(&b.added_commute_time)
                                .unwrap_or(std::cmp::Ordering::Equal)
                        });

                        if let Ok(js_val) = serde_wasm_bindgen::to_value(&results) {
                            components::renderResults(js_val, walk_time, infant_only);
                        }
                    }
                }
            });
        })
    };

    html! {
        <div class="app-container">
            <aside class="sidebar-panel" id="sidebar">
                <header class="sidebar-header">
                    <div class="logo-area">
                        <div class="logo-icon">{ "👶" }</div>
                        <div>
                            <h1>{ "Daycare Commute" }</h1>
                            <p class="subtitle">{ "NYC Corridor Finder (WASM)" }</p>
                        </div>
                    </div>
                </header>

                <div class="tab-content-container">
                    <components::Controls
                        lines={(*lines).clone()}
                        stations={current_line_stations}
                        selected_line={(*selected_line).clone()}
                        selected_home_station={(*selected_home_station).clone()}
                        selected_work_station={(*selected_work_station).clone()}
                        walk_time={*walk_time}
                        walk_speed={*walk_speed}
                        infant_only={*infant_only}
                        on_line_change={on_line_change}
                        on_home_change={Callback::from(move |val| selected_home_station.set(val))}
                        on_work_change={Callback::from(move |val| selected_work_station.set(val))}
                        on_walk_time_change={Callback::from(move |val| walk_time.set(val))}
                        on_walk_speed_change={Callback::from(move |val| walk_speed.set(val))}
                        on_infant_change={Callback::from(move |val| infant_only.set(val))}
                        on_search={on_search}
                    />
                </div>
            </aside>
            <div id="map"></div>
        </div>
    }
}

fn main() {
    wasm_logger::init(wasm_logger::Config::default());
    yew::Renderer::<App>::new().render();
}
