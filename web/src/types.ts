// Response shapes of the reach API (docs/data_contract.md, "API responses").
import type { Feature, FeatureCollection, LineString, MultiPolygon, Point, Polygon } from 'geojson'

export interface Run {
  run_id: string
  started_at: string
  finished_at: string | null
  status: string
  osm_snapshot: string | null
  gtfs_valid_from: string | null
  gtfs_valid_to: string | null
  reference_weekday: string | null
  config_hash: string
}

export interface DataSource {
  source: string
  url: string
  retrieved_at: string
  checksum: string
  licence: string
}

export interface ValidationIssue {
  check: string
  stage: string
  status: string
  value: number | null
  message: string
}

export interface Profile {
  profile_id: string
  costing: string
  speed_kmh: number
  time_budget_min: number
  transit: boolean
  /** Walking time to stops (transit supply); null without transit. */
  transit_budget_min: number | null
}

export interface Category {
  id: string
  name: string
  k: number
  /** Thematic group from the config (food, health, education, green). */
  group: string | null
}

export interface TransitClass {
  class: string
  lower: number
  upper: number | null
}

export interface Meta {
  run: Run
  data_sources: DataSource[]
  validation: { ok: number; warn: number; fail: number; issues: ValidationIssue[] }
  profiles: Profile[]
  categories: Category[]
  transit_classes: TransitClass[]
}

export interface DistrictProps {
  district_id: string
  name: string
  admin_level: number
  residents: number
  cells: number
}

export type Districts = FeatureCollection<Polygon | MultiPolygon, DistrictProps> & { run_id: string }

export interface DistrictScore {
  category: string
  profile_id: string
  share_lack: number | null
  share_insufficient: number | null
  share_sufficient: number | null
  deficit_sum: number | null
  residents_lack: number | null
  rank_deficit: number | null
  rank_share_lack: number | null
  districts_ranked: number | null
}

export interface DistrictScores {
  run_id: string
  district_id: string
  name: string
  admin_level: number
  scores: DistrictScore[]
}

/** Properties of a cell feature: count columns for facility categories, supply for transit. */
export interface CellProps {
  cell_id: string
  population: number
  district_id: string | null
  class: string
  count?: number
  nearest_min?: number | null
  deficit?: number
  departures?: number
  stops_count?: number
  nearest_stop_min?: number | null
  /** Accessibility score 0–100 (score view only, computed in the browser: `score.ts`). */
  score?: number
  /** Score 100: every selected category fulfilled (outline on the map). */
  full?: boolean
}

export type Cells = FeatureCollection<Polygon, CellProps> & {
  run_id: string
  category: string
  profile_id: string
}

/** One unpopulated grid cell of the housing potential (`GET /api/housing`, methodology §5b):
 * the times (s) of its nearest facilities per category as in `CellTimes`, the default score
 * and, once scored in the browser (`score.ts`), `score`, `class` and `full` for the selection. */
export interface HousingProps {
  cell_id: string
  district_id: string | null
  district_name: string | null
  times: Record<string, number[]>
  class?: string
  full?: boolean
}

/** `available: false` (no features) for a run published without the housing stage. */
export type Housing = FeatureCollection<Polygon, HousingProps & { score: number }> & {
  run_id: string
  available: boolean
  profile_id?: string
  max_times_per_category?: number
}

/** A recommended zone (100 m grid cell) for one new facility of a category (methodology §5). */
export interface RecommendationProps {
  category: string
  profile_id: string
  rank: number
  candidate_id: string
  /** Reduction of the deficit sum (residents) if one facility is added here. */
  population_gain: number
  /** Residents of cells that had no facility of the category within the budget. */
  residents_gaining_access: number
  /** Residents whose class becomes "sufficient". */
  residents_to_sufficient: number
  catchment_residents: number
  catchment_cells: number
  district_id: string | null
  district_name: string | null
  /** Zone centre [lon, lat]: the target of its catchment. */
  point: [number, number]
}

export type Recommendations = FeatureCollection<Polygon, RecommendationProps> & {
  run_id: string
  available: boolean
}

/** POST /api/catchment for a recommended zone: the catchment the recommender used. */
export interface CandidateCatchment {
  run_id: string
  profile_id: string
  target: {
    kind: 'candidate'
    candidate_id: string
    category: string
    rank: number
    population_gain: number
    residents_gaining_access: number
    residents_to_sufficient: number
    origin: [number, number]
  }
  source: 'precomputed'
  residents: number
  cells: number
  cell_ids: string[]
  residents_by_class: Record<string, Record<string, number>>
  isochrone: FeatureCollection<Polygon, { contour_min: number }>
  cached: boolean
}

/** `scored`: in the published run; `unpopulated`: centre in the city, no residents in the
 * Zensus grid; `outside_city`: centre outside the city boundary, never scored. */
export type CellStatus = 'scored' | 'unpopulated' | 'outside_city'

export interface InspectCell {
  cell_id: string
  scored: boolean
  status: CellStatus
  population: number | null
  district_id: string | null
  origin: [number, number]
}

export interface PrecomputedCategory {
  category: string
  count: number
  nearest_min: number | null
  class: string
  deficit: number
}

export interface PrecomputedTransit {
  departures: number
  stops_count: number
  nearest_stop_min: number | null
  class: string
}

/** Informative OSM tags of a facility (config `facility_tags`), as stored. */
export type FacilityTags = Partial<Record<string, string>>

export interface ReachableFacility {
  facility_id: string
  name: string | null
  tags: FacilityTags
  osm_url: string
  time_s: number
  time_min: number
  /** Routing point [lon, lat] the time was measured to (for parks the access point). */
  point: [number, number]
}

export type RouteLine = Feature<LineString, { time_s: number; length_m: number }>

/** The fastest facility of a category that is not counted yet (cell below `k`), also beyond the
 * budget; `route` is null if the route line could not be drawn. */
export interface NextFacility {
  facility_id: string
  name: string | null
  tags: FacilityTags
  osm_url: string
  time_s: number
  time_min: number
  point: [number, number]
  within_budget: boolean
  route: RouteLine | null
}

export interface InspectCategory {
  category: string
  name: string
  count: number
  count_source: 'precomputed' | 'live'
  reachable: ReachableFacility[]
  nearest_route: RouteLine | null
  /** Only for a category below `k`; `next_note` says why there is none (or null). */
  next_facility: NextFacility | null
  next_note: string | null
}

export interface Inspect {
  run_id: string
  profile_id: string
  cell: InspectCell
  source: 'precomputed' | 'live'
  precomputed: { categories: PrecomputedCategory[]; transit: PrecomputedTransit | null } | null
  weakest_category: string | null
  isochrone: FeatureCollection<Polygon, { contour_min: number }>
  categories: InspectCategory[]
  cached: boolean
}

/** POST /api/isochrone: forward (where you get) or reverse (from where people reach the cell). */
export interface IsochroneAnswer {
  run_id: string
  profile_id: string
  cell: InspectCell
  direction: 'forward' | 'reverse'
  isochrone: FeatureCollection<Polygon, { contour_min: number }>
  cached: boolean
}

/** POST /api/route: route from the cell origin to one facility (list click), any distance. */
export interface RouteAnswer {
  run_id: string
  profile_id: string
  cell: InspectCell
  facility: {
    facility_id: string
    name: string | null
    categories: string[]
    tags: FacilityTags
    osm_url: string
    point: [number, number]
  }
  within_budget: boolean
  route: RouteLine
  cached: boolean
}

/** GET /api/facilities: `facility` points; with `geometry=area` also park outlines (`area`) and
 * their routing points on the boundary (`access`). */
export type FacilityFeatureProps =
  | { kind: 'facility'; facility_id: string; name: string | null; category: string; tags: FacilityTags; osm_url: string }
  | { kind: 'area' | 'access'; facility_id: string; name?: string | null; category: string }

export type Facilities = FeatureCollection<Point | MultiPolygon, FacilityFeatureProps> & {
  run_id: string
  category: string
}

/** `GET /api/cells/times`: per scored cell the sorted times (s) of the nearest facilities per
 * category within the budget (at most `max_times_per_category`). Input of the score view. */
export interface CellTimes {
  run_id: string
  profile_id: string
  max_times_per_category: number
  cells: { cell_id: string; population: number; district_id: string | null; times: Record<string, number[]> }[]
}
