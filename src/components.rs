use crate::engine::{Daycare, RoutingEngine, Station};
use std::rc::Rc;
use wasm_bindgen::prelude::*;
use yew::prelude::*;

#[wasm_bindgen(module = "/public/app.js")]
extern "C" {
    pub fn initMapFromRust();
    pub fn onLineChanged(stations: JsValue, line: &str);
    pub fn onStationsChanged(route_stations: JsValue, home_val: &str, work_val: &str, line: &str);
    pub fn renderResults(daycares: JsValue, walk_time: i32, accepts_infants: bool);
    pub fn clearSearchLayers();
    pub fn renderIsochronesJS(isochrones: JsValue);
    pub fn switchTab(tab: &str);
}

#[derive(Properties, PartialEq)]
pub struct ControlsProps {
    pub lines: Vec<String>,
    pub stations: Vec<Station>,
    pub selected_line: String,
    pub selected_home_station: String,
    pub selected_work_station: String,
    pub walk_time: i32,
    pub walk_speed: f64,
    pub infant_only: bool,
    pub on_line_change: Callback<String>,
    pub on_home_change: Callback<String>,
    pub on_work_change: Callback<String>,
    pub on_walk_time_change: Callback<i32>,
    pub on_walk_speed_change: Callback<f64>,
    pub on_infant_change: Callback<bool>,
    pub on_search: Callback<()>,
}

#[function_component(Controls)]
pub fn controls(props: &ControlsProps) -> Html {
    let on_line_change = {
        let cb = props.on_line_change.clone();
        Callback::from(move |e: Event| {
            use wasm_bindgen::JsCast;
            let target: web_sys::HtmlSelectElement = e.target_unchecked_into();
            cb.emit(target.value());
        })
    };

    let on_home_change = {
        let cb = props.on_home_change.clone();
        Callback::from(move |e: Event| {
            use wasm_bindgen::JsCast;
            let target: web_sys::HtmlSelectElement = e.target_unchecked_into();
            cb.emit(target.value());
        })
    };

    let on_work_change = {
        let cb = props.on_work_change.clone();
        Callback::from(move |e: Event| {
            use wasm_bindgen::JsCast;
            let target: web_sys::HtmlSelectElement = e.target_unchecked_into();
            cb.emit(target.value());
        })
    };

    let on_walk_time_change = {
        let cb = props.on_walk_time_change.clone();
        Callback::from(move |e: InputEvent| {
            use wasm_bindgen::JsCast;
            let target: web_sys::HtmlInputElement = e.target_unchecked_into();
            if let Ok(val) = target.value().parse::<i32>() {
                cb.emit(val);
            }
        })
    };

    let on_walk_speed_change = {
        let cb = props.on_walk_speed_change.clone();
        Callback::from(move |e: InputEvent| {
            use wasm_bindgen::JsCast;
            let target: web_sys::HtmlInputElement = e.target_unchecked_into();
            if let Ok(val) = target.value().parse::<f64>() {
                cb.emit(val);
            }
        })
    };

    let on_infant_change = {
        let cb = props.on_infant_change.clone();
        Callback::from(move |e: Event| {
            use wasm_bindgen::JsCast;
            let target: web_sys::HtmlInputElement = e.target_unchecked_into();
            cb.emit(target.checked());
        })
    };

    let on_search = {
        let cb = props.on_search.clone();
        Callback::from(move |_| {
            cb.emit(());
        })
    };

    let switch_tab_controls = Callback::from(|_| {
        switchTab("controls");
    });

    let switch_tab_results = Callback::from(|_| {
        switchTab("results");
    });

    html! {
        <>
        <div class="tabs-nav">
            <button class="tab-btn active" id="tab-btn-controls" onclick={switch_tab_controls}>
                <i data-lucide="sliders"></i> { "Controls" }
            </button>
            <button class="tab-btn" id="tab-btn-results" onclick={switch_tab_results}>
                <i data-lucide="list"></i> { "Results" }
                <span class="badge hidden" id="results-count">{ "0" }</span>
            </button>
        </div>

        <section class="tab-content active" id="tab-controls">
            <div class="control-group">
                <h2><i data-lucide="train"></i> { "1. Select Your Route" }</h2>
                <div class="field">
                    <label for="subway-line">{ "Subway Line" }</label>
                    <select id="subway-line" onchange={on_line_change} value={props.selected_line.clone()}>
                        <option value="">{ "Select Line..." }</option>
                        {
                            for props.lines.iter().map(|line| {
                                html! { <option value={line.clone()}>{ format!("{} Train", line) }</option> }
                            })
                        }
                    </select>
                </div>
                <div class="row">
                    <div class="field">
                        <label for="home-station">{ "Home Station" }</label>
                        <select id="home-station" disabled={props.selected_line.is_empty()} onchange={on_home_change} value={props.selected_home_station.clone()}>
                            <option value="">{ "Select line first..." }</option>
                            {
                                for props.stations.iter().map(|station| {
                                    if let Some(id) = &station.gtfs_stop_id {
                                        html! { <option value={id.clone()}>{ station.station_name.clone() }</option> }
                                    } else {
                                        html! {}
                                    }
                                })
                            }
                        </select>
                    </div>
                    <div class="field">
                        <label for="work-station">{ "Work Station" }</label>
                        <select id="work-station" disabled={props.selected_line.is_empty()} onchange={on_work_change} value={props.selected_work_station.clone()}>
                            <option value="">{ "Select line first..." }</option>
                            {
                                for props.stations.iter().map(|station| {
                                    if let Some(id) = &station.gtfs_stop_id {
                                        html! { <option value={id.clone()}>{ station.station_name.clone() }</option> }
                                    } else {
                                        html! {}
                                    }
                                })
                            }
                        </select>
                    </div>
                </div>
            </div>

            <div class="control-group">
                <h2><i data-lucide="footprints"></i> { "2. Detour Settings" }</h2>
                <div class="field">
                    <div class="field-header">
                        <label for="walk-time">{ "Max Walk Budget" }</label>
                        <span class="value-display">{ format!("{} min", props.walk_time) }</span>
                    </div>
                    <input type="range" id="walk-time" min="5" max="15" step="5" value={props.walk_time.to_string()} oninput={on_walk_time_change} />
                    <div class="range-labels">
                        <span>{ "5m" }</span>
                        <span>{ "10m" }</span>
                        <span>{ "15m" }</span>
                    </div>
                </div>
                <div class="field">
                    <div class="field-header">
                        <label for="walk-speed">{ "Walking Speed (Stroller)" }</label>
                        <span class="value-display">{ format!("{:.1} km/h", props.walk_speed) }</span>
                    </div>
                    <input type="range" id="walk-speed" min="2.0" max="6.0" step="0.5" value={props.walk_speed.to_string()} oninput={on_walk_speed_change} />
                    <div class="range-labels">
                        <span>{ "2.0 (Slow)" }</span>
                        <span>{ "4.0 (Stroller)" }</span>
                        <span>{ "6.0 (Fast)" }</span>
                    </div>
                </div>
            </div>

            <div class="control-group">
                <h2><i data-lucide="map-pin"></i> { "3. Custom Pins & Filters" }</h2>
                <div class="checkbox-row">
                    <input type="checkbox" id="infant-filter" checked={props.infant_only} onchange={on_infant_change} />
                    <div class="checkbox-label">
                        <span class="title">{ "Infant Care Only" }</span>
                        <span class="desc">{ "Filter for programs accepting under 2 years" }</span>
                    </div>
                </div>
            </div>

            <button class="btn btn-primary" onclick={on_search}>
                <span class="btn-text">{ "Find Daycares" }</span>
            </button>
        </section>

        <section class="tab-content" id="tab-results">
            <div class="results-summary">
                <div>
                    <span class="label">{ "Matched" }</span>
                    <span class="val" id="summary-total">{ "0" }</span>
                </div>
                <div class="divider"></div>
                <div>
                    <span class="label">{ "Age Filter" }</span>
                    <span class="val" id="summary-infant">{ "None" }</span>
                </div>
                <div class="divider"></div>
                <div>
                    <span class="label">{ "Budget" }</span>
                    <span class="val" id="summary-budget">{ "10 min" }</span>
                </div>
            </div>

            <div class="results-list" id="results-list">
                <div class="placeholder-state" id="results-placeholder">
                    <div class="icon">{ "🚇" }</div>
                    <h3>{ "Configure your commute" }</h3>
                    <p>{ "Select your subway line, stops, walk time, and click 'Find Daycares' to see convenience corridors." }</p>
                </div>
            </div>
        </section>
        </>
    }
}
