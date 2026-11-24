/**
 * ETRS89-LAEA (EPSG:3035) on the GRS80 ellipsoid, forward and inverse (EPSG guidance note 7-2,
 * §3.2.2). Used only to draw Zensus cells from their ids and to find the cell under a pin; the
 * browser never measures distances in degrees (architecture rule 3).
 *
 * Standalone on purpose (no imports), so `node --test` and the fixture script can load it.
 */

export type LonLat = [number, number]
export type EastNorth = [number, number]

const A = 6378137.0
const F = 1 / 298.257222101
const E2 = 2 * F - F * F
const E = Math.sqrt(E2)
const LAT0 = (52 * Math.PI) / 180
const LON0 = (10 * Math.PI) / 180
const FE = 4321000.0
const FN = 3210000.0

function q(sinPhi: number): number {
  const es = E * sinPhi
  return (1 - E2) * (sinPhi / (1 - es * es) - (1 / (2 * E)) * Math.log((1 - es) / (1 + es)))
}

const QP = q(1)
const Q0 = q(Math.sin(LAT0))
const BETA0 = Math.asin(Q0 / QP)
const RQ = A * Math.sqrt(QP / 2)
const D = (A * Math.cos(LAT0)) / Math.sqrt(1 - E2 * Math.sin(LAT0) ** 2) / (RQ * Math.cos(BETA0))

/** [lon, lat] in degrees (EPSG:4326) → [easting, northing] in metres (EPSG:3035). */
export function toLaea([lon, lat]: LonLat): EastNorth {
  const phi = (lat * Math.PI) / 180
  const lam = (lon * Math.PI) / 180
  const beta = Math.asin(q(Math.sin(phi)) / QP)
  const b =
    RQ *
    Math.sqrt(
      2 /
        (1 +
          Math.sin(BETA0) * Math.sin(beta) +
          Math.cos(BETA0) * Math.cos(beta) * Math.cos(lam - LON0)),
    )
  const e = FE + b * D * Math.cos(beta) * Math.sin(lam - LON0)
  const n =
    FN +
    (b / D) *
      (Math.cos(BETA0) * Math.sin(beta) - Math.sin(BETA0) * Math.cos(beta) * Math.cos(lam - LON0))
  return [e, n]
}

/** [easting, northing] in metres (EPSG:3035) → [lon, lat] in degrees (EPSG:4326). */
export function fromLaea([e, n]: EastNorth): LonLat {
  const x = e - FE
  const y = n - FN
  const rho = Math.sqrt((x / D) ** 2 + (D * y) ** 2)
  const c = 2 * Math.asin(rho / (2 * RQ))
  const betaP = Math.asin(
    Math.cos(c) * Math.sin(BETA0) + (D * y * Math.sin(c) * Math.cos(BETA0)) / rho,
  )
  const lam =
    LON0 +
    Math.atan2(
      x * Math.sin(c),
      D * rho * Math.cos(BETA0) * Math.cos(c) - D * D * y * Math.sin(BETA0) * Math.sin(c),
    )
  const e4 = E2 * E2
  const e6 = e4 * E2
  const phi =
    betaP +
    (E2 / 3 + (31 * e4) / 180 + (517 * e6) / 5040) * Math.sin(2 * betaP) +
    ((23 * e4) / 360 + (251 * e6) / 3780) * Math.sin(4 * betaP) +
    ((761 * e6) / 45360) * Math.sin(6 * betaP)
  return [(lam * 180) / Math.PI, (phi * 180) / Math.PI]
}

const CELL_RE = /^CRS3035RES100mN(\d+)E(\d+)$/
export const CELL_SIZE_M = 100

/** Lower-left corner of a Zensus 100 m cell in EPSG:3035, or null for a malformed id. */
export function cellCorner(cellId: string): EastNorth | null {
  const m = CELL_RE.exec(cellId)
  return m ? [Number(m[2]), Number(m[1])] : null
}

/** Id of the 100 m cell that contains the point. */
export function cellIdAt(point: LonLat): string {
  const [e, n] = toLaea(point)
  const e0 = Math.floor(e / CELL_SIZE_M) * CELL_SIZE_M
  const n0 = Math.floor(n / CELL_SIZE_M) * CELL_SIZE_M
  return `CRS3035RES100mN${n0}E${e0}`
}

/** Closed ring of the cell in [lon, lat] (5 points, counter-clockwise), or null. */
export function cellRing(cellId: string): LonLat[] | null {
  const c = cellCorner(cellId)
  if (!c) return null
  const [e, n] = c
  const s = CELL_SIZE_M
  return [
    fromLaea([e, n]),
    fromLaea([e + s, n]),
    fromLaea([e + s, n + s]),
    fromLaea([e, n + s]),
    fromLaea([e, n]),
  ]
}

/** Centre of the cell in [lon, lat], or null. */
export function cellCentre(cellId: string): LonLat | null {
  const c = cellCorner(cellId)
  return c ? fromLaea([c[0] + CELL_SIZE_M / 2, c[1] + CELL_SIZE_M / 2]) : null
}

/** Planar distance in metres between two cells (EPSG:3035 corners). */
export function cellDistanceM(a: string, b: string): number {
  const ca = cellCorner(a)
  const cb = cellCorner(b)
  if (!ca || !cb) return Infinity
  return Math.hypot(ca[0] - cb[0], ca[1] - cb[1])
}
