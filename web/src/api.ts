// Thin client for the reach API. Read endpoints send `Cache-Control: no-cache` and an ETag per
// run, so the browser's HTTP cache revalidates them with `If-None-Match` and reuses the body on
// 304; nothing is cached here on top of that.
import type {
  CandidateCatchment,
  CellTimes,
  Cells,
  DistrictScores,
  Facilities,
  Districts,
  Housing,
  Inspect,
  IsochroneAnswer,
  Meta,
  Recommendations,
  RouteAnswer,
} from './types'

const API_BASE: string = import.meta.env.VITE_API_BASE

export class ApiError extends Error {
  readonly status: number
  readonly retryAfterS: number | null

  constructor(status: number, message: string, retryAfterS: number | null = null) {
    super(message)
    this.status = status
    this.retryAfterS = retryAfterS
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(API_BASE + path, init)
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(0, 'The API is not reachable.')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
      else if (body.detail !== undefined) detail = JSON.stringify(body.detail)
    } catch {
      // body is not JSON (e.g. a proxy error page); keep the status text
    }
    const retry = Number(res.headers.get('Retry-After'))
    throw new ApiError(res.status, detail, Number.isFinite(retry) && retry > 0 ? retry : null)
  }
  return (await res.json()) as T
}

const query = (params: Record<string, string>) => new URLSearchParams(params).toString()

export const getMeta = () => request<Meta>('/meta')
export const getDistricts = () => request<Districts>('/districts')
export const getDistrictScores = (id: string, profile: string) =>
  request<DistrictScores>(`/districts/${encodeURIComponent(id)}/scores?${query({ profile })}`)
export const getCells = (category: string, profile: string) =>
  request<Cells>(`/cells?${query({ category, profile })}`)
export const getCellTimes = (profile: string) => request<CellTimes>(`/cells/times?${query({ profile })}`)
export const getHousing = (profile: string) => request<Housing>(`/housing?${query({ profile })}`)
export const getFacilities = (category: string) =>
  request<Facilities>(`/facilities?${query({ category, geometry: 'area' })}`)
export const getRecommendations = (category: string, profile: string) =>
  request<Recommendations>(`/recommendations?${query({ category, profile })}`)

export const postCandidateCatchment = (
  candidateId: string,
  category: string,
  profile: string,
  signal?: AbortSignal,
) =>
  request<CandidateCatchment>('/catchment', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate_id: candidateId, category, profile }),
    signal,
  })

export const postInspect = (lon: number, lat: number, profile: string, signal?: AbortSignal) =>
  request<Inspect>('/inspect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lon, lat, profile }),
    signal,
  })

export const postIsochrone = (
  lon: number,
  lat: number,
  profile: string,
  direction: 'forward' | 'reverse',
  signal?: AbortSignal,
) =>
  request<IsochroneAnswer>('/isochrone', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lon, lat, profile, direction }),
    signal,
  })

export const postRoute = (lon: number, lat: number, profile: string, facilityId: string, signal?: AbortSignal) =>
  request<RouteAnswer>('/route', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lon, lat, profile, facility_id: facilityId }),
    signal,
  })

/** User-facing message for a failed request, by status (docs/data_contract.md, errors). */
export function errorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return 'Something went wrong.'
  switch (err.status) {
    case 0:
      return 'The API is not reachable. Is the local stack running (make up)?'
    case 422:
      return `This point cannot be inspected: ${err.message}.`
    case 429:
      return `Too many requests. Please wait ${err.retryAfterS ?? 'a few'} seconds and try again.`
    case 502:
      return 'The routing engine did not answer. Please try again in a moment.'
    case 503:
      return 'No published run is available yet (database down or empty).'
    case 504:
      return 'The live calculation took too long (timeout). Try again or pick a point closer to a street.'
    default:
      return `Request failed (${err.status}): ${err.message}`
  }
}
