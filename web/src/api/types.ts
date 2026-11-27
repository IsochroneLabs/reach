/**
 * API shapes. Source: "API responses — proposal of S1.4" in docs/data_contract.md (Juju docs
 * stack, not yet in `dev`). Everything marked PROPOSED is not in that proposal; it is listed for
 * Juju as notes N17 and used only by the fixtures until the API decides.
 */

export type LonLat = [number, number]
export type Mode = 'walk' | 'bike' | 'transit' | 'bike_transit'
export type Importance = 0 | 1 | 2 | 3
export type Lang = 'en' | 'de'
export type Label = Record<Lang, string>

export interface DestinationType {
  destination_type: string
  label: Label
  trip_window: string
  fine_time_min: number
  trips_per_week: number
  /**
   * PROPOSED (F2.4, methodology §3.1): the offered labels of this type. Grocery: brands and groups
   * (narrow the grocery term, QF3). Sport and hobby: categories, each a term of its own (QF4), sent
   * as `destinations["sport:tennis"]`; such container types are never a term themselves.
   */
  labels?: DestinationLabel[]
}

/** PROPOSED (F2.4): one label of a destination type with the number of destinations. */
export interface DestinationLabel {
  label: string
  kind: 'brand' | 'group' | 'category'
  name: Label
  destinations: number
}

/** PROPOSED (F2.4): GET /api/label-destinations, labelled destinations for the map. */
export interface LabelDestination {
  destination_id: string
  destination_type: string
  labels: string[]
  name: string | null
  point: LonLat
}

export interface CampusSite {
  site_id: string
  name: string
  programmes: string[]
  point: LonLat
  /** PROPOSED (N17): share of this site in the default campus mix (campus.default_mix). */
  default_share?: number
}

/** PROPOSED (N17): GET /api/programmes. */
export interface Programme {
  programme: string
  label: Label
  sites: string[]
}

/** The student profile as the body of POST /api/fit and POST /api/cell/{id}. */
export interface FitRequest {
  /** PROPOSED (N16/N17): optional; null or absent = default campus mix. */
  programme?: string | null
  campus_days?: Record<string, number>
  modes: Mode[]
  /**
   * Keys: a destination type, or `<type>:<category>` for a sport or hobby category (PROPOSED,
   * F2.4). Categories take importance and fine time only; they never count in the weekly time.
   */
  destinations: Record<
    string,
    { importance: Importance; fine_time_min?: number; trips_per_week?: number }
  >
  /** PROPOSED (F2.4): favourite supermarkets, brands and groups; empty or absent = any. */
  labels?: { grocery?: string[] }
  area_level?: 'district' | 'teilort'
}

export interface Reason {
  kind: 'strength' | 'weakness' | 'reliability'
  destination_type: string
  name: string | null
  minutes: number | null
  mode: Mode | null
  trip_window: string
  /** reliability: e.g. the last departure home ("00:47"). */
  value?: string | number
}

export interface Area {
  area_id: string
  name: string
  fit: number
  best_cell_id: string
  best_cell_fit: number
  weekly_min: number
  reasons: Reason[]
}

/** cell_id → [fit, weekly_min, populated]; the third element is PROPOSED (N17), 1 = populated. */
export type CellFits = Record<string, [number | null, number | null, 0 | 1]>

export interface FitResponse {
  run_id: string
  areas: Area[]
  cells: CellFits
}

export interface TransitLegs {
  access_min: number
  wait_min: number
  in_vehicle_min: number
  egress_min: number
  transfers: number
  first_stop: string | null
  first_route: string | null
  walk_only: boolean
  /** night window: last departure home (PROPOSED presentation of stop_departures). */
  last_departure?: string | null
}

export interface Trip {
  destination_type: string
  destination_id: string
  name: string | null
  mode: Mode
  trip_window: string
  /** null = not reachable; never 0 for "unknown". */
  minutes: number | null
  legs?: TransitLegs
}

/** PROPOSED (N17): per destination type, what it adds to the fit. */
export interface FitPart {
  destination_type: string
  minutes: number | null
  mode: Mode | null
  score: number
  weight: number
  /** share of the fit points this type contributes, 0–1 */
  share: number
}

export interface CellDetail {
  cell_id: string
  district: string | null
  point: LonLat
  trips: Trip[]
  fit?: number | null
  reasons?: Reason[]
  /** PROPOSED (N17) */
  weekly_min?: number | null
  /** PROPOSED (N17) */
  fit_parts?: FitPart[]
  /** PROPOSED (N17): false = address cell (no residents) */
  populated?: boolean
}

/** PROPOSED (F4.6): one current WG-Gesucht listing with the fit of its Zensus cell. */
export interface Listing {
  listing_id: string
  source_url: string
  kind: 'wg_room' | 'studio' | 'flat'
  title: string | null
  rent_total_eur: number | null
  rent_cold_eur: number | null
  deposit_eur: number | null
  size_m2: number | null
  flat_size_m2: number | null
  rooms: number | null
  household_size: number | null
  available_from: string | null
  available_to: string | null
  furnished: string | null
  features: string[] | null
  district: string | null
  postcode: string | null
  address_text: string | null
  geocode_precision: 'house' | 'street' | 'marker' | null
  cell_id: string | null
  image_urls: string[] | null
  description_excerpt: string | null
  first_seen: string
  last_seen: string
  point: LonLat | null
  /** F4.5 point routing is not built yet; the address is the cell or the ad's own marker. */
  approximate: boolean
  /** from POST /api/listings/fit */
  fit?: number | null
  weekly_min?: number | null
}

export interface AddressHit {
  label: string
  cell_id: string
  point: LonLat
}

export interface TripWindow {
  trip_window: string
  weekday: string
  time: string
  kind: 'arrive_by' | 'depart_at'
  direction: 'to' | 'back'
  reference_date: string
}

/** PROPOSED (N17): GET /api/meta. */
export interface Meta {
  run_id: string
  sources: { source: 'osm' | 'gtfs' | 'zensus'; date: string; valid_to?: string }[]
  trip_windows: TripWindow[]
  /** bounds of the routing area: [[west, south], [east, north]] */
  bounds: [LonLat, LonLat]
  modes: Mode[]
}

/** PROPOSED (N17): GET /api/personas (config/personas.yaml). */
export interface Persona {
  persona: string
  label: Label
  profile: FitRequest
}

export interface Health {
  status: string
  version: string
  build_sha: string
}

export class ApiError extends Error {
  status: number
  retryAfterS: number | null
  constructor(status: number, message: string, retryAfterS: number | null = null) {
    super(message)
    this.status = status
    this.retryAfterS = retryAfterS
  }
}
