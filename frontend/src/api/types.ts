export interface Point {
  lat: number;
  lon: number;
  ele: number | null;
  time: string | null;
}

export interface DayStats {
  point_count: number;
  distance_m: number;
  ascent_m: number;
  descent_m: number;
}

export interface DaySummary {
  id: number;
  project_id: number;
  name: string;
  order_index: number;
  is_circular: boolean;
  is_locked: boolean;
  lock_start: boolean;
  lock_end: boolean;
  stats: DayStats;
}

export type ConnectorType = "start_access" | "end_access" | "spur";

export interface Connector {
  id: number;
  day_id: number;
  name: string;
  type: ConnectorType;
  points: Point[];
}

export interface DayDetail extends DaySummary {
  points: Point[];
  connectors: Connector[];
  /** The wider route this day was trimmed from; empty when nothing was trimmed. */
  source_points: Point[];
  is_trimmed: boolean;
  source_start: number;
  source_end: number;
}

export interface ProjectSummary {
  id: number;
  name: string;
  source_filename: string | null;
  created_at: string;
  day_count: number;
}

export interface ProjectDetail extends ProjectSummary {
  days: DaySummary[];
}

export type CyclingRelevance = "high" | "medium" | "low" | "none";

export interface RoadworkMatch {
  external_id: string;
  road_name: string | null;
  works_desc: string | null;
  responsible_org: string | null;
  permit_ref: string | null;
  start_date: string | null;
  end_date: string | null;
  traffic_management: string | null;
  item_type: string | null;
  delay: string | null;
  tm_cat: string | null;
  impact: string | null;
  works_state: string | null;
  permit_status: string | null;
  cycling_relevance: CyclingRelevance;
  distance_m: number;
  nearest_point_index: number;
  lat: number;
  lon: number;
  geometry: [number, number][];
}

export interface RoadworksResponse {
  day_id: number;
  day_name: string;
  target_date: string | null;
  buffer_m: number;
  candidates_checked: number;
  total_stored: number;
  matches: RoadworkMatch[];
}

export interface TileRef {
  z: number;
  x: number;
  y: number;
}

export interface TilesForDay {
  day_id: number;
  day_name: string;
  z: number;
  count: number;
  tiles: TileRef[];
}


export interface FetchResult {
  day_name: string;
  target_date: string;
  zoom: number;
  tiles_required: number;
  tiles_from_cache: number;
  tiles_fetched: number;
  tiles_empty: number;
  imported: number;
  updated: number;
  total_stored: number;
  failures: string[];
}


export interface StravaStatus {
  configured: boolean;
  connected: boolean;
  athlete_name: string | null;
  athlete_id: number | null;
  expires_at: string | null;
  scope: string | null;
  redirect_uri: string;
}

export interface StravaRoute {
  id_str: string;
  name: string;
  description: string | null;
  distance_m: number;
  elevation_gain_m: number | null;
  type: number | null;
  sub_type: number | null;
  private: boolean;
  starred: boolean;
  created_at: string | null;
}

export interface PotholeMatch {
  report_id: string;
  title: string | null;
  reported_approx: string | null;
  url: string | null;
  lat: number;
  lon: number;
  distance_m: number;
  nearest_point_index: number;
}

export interface PotholeResponse {
  day_id: number;
  buffer_m: number;
  max_age_years: number;
  candidates_checked: number;
  excluded_too_old: number;
  total_stored: number;
  matches: PotholeMatch[];
}

export interface PotholeFetchResult {
  boxes_required: number;
  boxes_cached: number;
  boxes_fetched: number;
  boxes_saturated: number;
  pins_seen: number;
  new_reports: number;
  total_stored: number;
  failures: string[];
}

export interface WindEffect {
  label: "headwind" | "tailwind" | "crosswind";
  along_kmh: number;
  across_kmh: number;
}

export interface DayWeather {
  day_id: number;
  date: string;
  summary: string;
  temp_min_c: number;
  temp_max_c: number;
  precip_mm: number;
  precip_chance_pct: number | null;
  wind_kmh: number;
  gust_kmh: number | null;
  wind_from: string | null;
  sunrise: string | null;
  sunset: string | null;
  route_heading: string;
  overall_wind: WindEffect | null;
  legs: { from_index: number; heading: string; wind: WindEffect | null }[];
}

export interface Boundary {
  index: number;
  day_a_id: number;
  day_b_id: number;
  day_a_name: string;
  day_b_name: string;
  lat: number | null;
  lon: number | null;
  movable: boolean;
  blocked_by: string[];
  max_back_m: number;
  max_forward_m: number;
  day_a_distance_m: number;
  day_b_distance_m: number;
  wraps?: boolean;
}

export interface BoundaryList {
  project_id: number;
  day_count: number;
  is_loop: boolean;
  movable_count: number;
  boundaries: Boundary[];
}

export interface ShiftResult {
  boundaries_moved: number;
  boundaries_skipped: { index: number; blocked_by: string[] }[];
  average_moved_m: number;
}

export interface ShadowCandidate {
  day_id: number;
  name: string;
  project_id: number;
  project_name: string | null;
  point_count: number;
  distance_m: number;
  overlaps: boolean;
  is_longer: boolean;
}

/** [lat, lon, indexIntoThatDaysPoints] */
export type GeomPoint = [number, number, number];

export interface DayGeometry {
  day_id: number;
  name: string;
  order_index: number;
  point_count: number;
  is_locked: boolean;
  points: GeomPoint[];
}

export interface ProjectGeometry {
  project_id: number;
  days: DayGeometry[];
  /** The trip returns to its start, so the first and last days share a boundary. */
  is_loop: boolean;
}

export interface HistoryStatus {
  can_undo: boolean;
  can_redo: boolean;
  undo_action: string | null;
  redo_action: string | null;
  undo_depth: number;
  redo_depth: number;
}
