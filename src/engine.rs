use petgraph::graph::UnGraph;
use rstar::{PointDistance, RTree};
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct Station {
    pub station_name: String,
    pub gtfs_stop_id: Option<String>,
    pub latitude: f64,
    pub longitude: f64,
    pub daytime_routes: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Daycare {
    pub dcid: Option<String>,
    pub program_name: String,
    pub address: String,
    pub borough: String,
    pub zipcode: String,
    pub phone: Option<String>,
    pub age_range: Option<String>,
    pub capacity: i32,
    pub facility_type: String,
    pub program_type: String,
    pub latitude: Option<f64>,
    pub longitude: Option<f64>,
    pub permit_number: Option<String>,
    pub safety_metrics: Option<SafetyMetrics>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct SafetyMetrics {
    pub total_inspections: i32,
    pub hazard_violations: i32,
    pub critical_violations: i32,
    pub total_violations: i32,
    pub latest_inspection_date: Option<String>,
    pub violations: Vec<Violation>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Violation {
    pub date: String,
    pub category: String,
    pub summary: String,
    pub status: String,
}

#[derive(Debug, Serialize, Deserialize, Clone, PartialEq)]
pub struct GraphNode {
    pub id: usize,
    pub x: f64,
    pub y: f64,
}

impl rstar::Point for GraphNode {
    type Scalar = f64;
    const DIMENSIONS: usize = 2;

    fn generate(mut generator: impl FnMut(usize) -> Self::Scalar) -> Self {
        GraphNode {
            id: 0,
            x: generator(0),
            y: generator(1),
        }
    }

    fn nth(&self, index: usize) -> Self::Scalar {
        match index {
            0 => self.x,
            1 => self.y,
            _ => unreachable!(),
        }
    }

    fn nth_mut(&mut self, index: usize) -> &mut Self::Scalar {
        match index {
            0 => &mut self.x,
            1 => &mut self.y,
            _ => unreachable!(),
        }
    }
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct GraphEdge {
    pub u: usize,
    pub v: usize,
    pub length: f64,
    pub geometry: Option<Vec<(f64, f64)>>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct WalkNetwork {
    pub nodes: Vec<GraphNode>,
    pub edges: Vec<GraphEdge>,
}

pub struct RoutingEngine {
    pub graph: UnGraph<GraphNode, f64>,
    pub rtree: RTree<GraphNode>,
}

impl RoutingEngine {
    pub fn new(network: WalkNetwork) -> Self {
        let mut graph = UnGraph::default();
        let mut node_indices = vec![];
        let mut rtree_nodes = vec![];

        // Add nodes
        for node in network.nodes.into_iter() {
            let idx = graph.add_node(node.clone());
            node_indices.push(idx);
            rtree_nodes.push(node);
        }

        // Add edges
        for edge in network.edges.into_iter() {
            if edge.u < node_indices.len() && edge.v < node_indices.len() {
                graph.add_edge(node_indices[edge.u], node_indices[edge.v], edge.length);
            }
        }

        let rtree = RTree::bulk_load(rtree_nodes);

        RoutingEngine { graph, rtree }
    }

    pub fn nearest_node(&self, lat: f64, lng: f64) -> Option<usize> {
        // Create a dummy node with the query point
        let query = GraphNode {
            id: 0,
            x: lng,
            y: lat,
        };
        self.rtree.nearest_neighbor(&query).map(|node| node.id)
    }

    pub fn shortest_path_length(&self, start_id: usize, end_id: usize) -> Option<f64> {
        let start = petgraph::graph::NodeIndex::new(start_id);
        let end = petgraph::graph::NodeIndex::new(end_id);

        let res = petgraph::algo::dijkstra(&self.graph, start, Some(end), |e| *e.weight());
        res.get(&end).copied()
    }

    pub fn walk_time(
        &self,
        start_lat: f64,
        start_lng: f64,
        end_lat: f64,
        end_lng: f64,
        walk_speed_kmh: f64,
    ) -> f64 {
        let start_node = match self.nearest_node(start_lat, start_lng) {
            Some(n) => n,
            None => {
                return estimate_walk_time(start_lat, start_lng, end_lat, end_lng, walk_speed_kmh)
            }
        };
        let end_node = match self.nearest_node(end_lat, end_lng) {
            Some(n) => n,
            None => {
                return estimate_walk_time(start_lat, start_lng, end_lat, end_lng, walk_speed_kmh)
            }
        };

        let walk_speed_m_per_min = (walk_speed_kmh * 1000.0) / 60.0;

        if let Some(path_len) = self.shortest_path_length(start_node, end_node) {
            let net_time = path_len / walk_speed_m_per_min;
            let (n_start_lat, n_start_lng) = self.node_coords(start_node).unwrap();
            let (n_end_lat, n_end_lng) = self.node_coords(end_node).unwrap();

            let offset_start = haversine_distance(start_lat, start_lng, n_start_lat, n_start_lng);
            let offset_end = haversine_distance(end_lat, end_lng, n_end_lat, n_end_lng);

            net_time + (offset_start + offset_end) / walk_speed_m_per_min
        } else {
            estimate_walk_time(start_lat, start_lng, end_lat, end_lng, walk_speed_kmh)
        }
    }

    pub fn node_coords(&self, node_id: usize) -> Option<(f64, f64)> {
        self.graph
            .node_weight(petgraph::graph::NodeIndex::new(node_id))
            .map(|n| (n.y, n.x))
    }
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct DaycareResult {
    pub dcid: Option<String>,
    pub program_name: String,
    pub address: String,
    pub borough: String,
    pub zipcode: String,
    pub phone: Option<String>,
    pub age_range: Option<String>,
    pub capacity: i32,
    pub facility_type: String,
    pub program_type: String,
    pub latitude: f64,
    pub longitude: f64,
    pub nearest_source_id: String,
    pub walk_ring_mins: i32,
    pub added_commute_time: f64,
    pub permit_number: Option<String>,
    pub safety_metrics: Option<SafetyMetrics>,
}

pub fn haversine_distance(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    let r = 6371000.0; // Radius of Earth in meters
    let phi1 = lat1.to_radians();
    let phi2 = lat2.to_radians();
    let delta_phi = (lat2 - lat1).to_radians();
    let delta_lambda = (lon2 - lon1).to_radians();

    let a = (delta_phi / 2.0).sin().powi(2)
        + phi1.cos() * phi2.cos() * (delta_lambda / 2.0).sin().powi(2);
    let c = 2.0 * a.sqrt().atan2((1.0 - a).sqrt());

    r * c
}

pub fn estimate_walk_time(lat1: f64, lon1: f64, lat2: f64, lon2: f64, walk_speed_kmh: f64) -> f64 {
    let dist_meters = haversine_distance(lat1, lon1, lat2, lon2);
    let speed_m_per_min = (walk_speed_kmh * 1000.0) / 60.0;
    (dist_meters * 1.3) / speed_m_per_min
}
