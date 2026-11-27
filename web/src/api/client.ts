import { API_BASE, USE_FIXTURES } from '../config'
import {
  ApiError,
  type AddressHit,
  type CampusSite,
  type CellDetail,
  type DestinationType,
  type FitRequest,
  type FitResponse,
  type LabelDestination,
  type Listing,
  type Meta,
  type Persona,
  type Programme,
} from './types'

/** Everything the app asks the API. Profiles go only in POST bodies (root rule 9). */
export interface Api {
  meta(signal?: AbortSignal): Promise<Meta>
  destinationTypes(signal?: AbortSignal): Promise<DestinationType[]>
  campusSites(signal?: AbortSignal): Promise<CampusSite[]>
  programmes(signal?: AbortSignal): Promise<Programme[]>
  personas(signal?: AbortSignal): Promise<Persona[]>
  labelDestinations(signal?: AbortSignal): Promise<LabelDestination[]>
  searchAddresses(q: string, signal?: AbortSignal): Promise<AddressHit[]>
  fit(profile: FitRequest, signal?: AbortSignal): Promise<FitResponse>
  cell(cellId: string, profile: FitRequest, signal?: AbortSignal): Promise<CellDetail>
  /** PROPOSED (F4.6): current listings with the fit of their cell, best first. */
  listings(profile: FitRequest, signal?: AbortSignal): Promise<Listing[]>
}

/** One request: method, path below the API base, optional JSON body. */
export type Transport = (method: 'GET' | 'POST', path: string, body?: unknown, signal?: AbortSignal) => Promise<unknown>

const TIMEOUT_MS = 10_000

/** fetch() against API_BASE with a timeout; non-2xx becomes ApiError. */
export const httpTransport: Transport = async (method, path, body, signal) => {
  const timeout = AbortSignal.timeout(TIMEOUT_MS)
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  })
  if (!res.ok) {
    const retry = Number(res.headers.get('Retry-After'))
    let detail = `HTTP ${res.status}`
    try {
      const j = (await res.json()) as { detail?: unknown }
      if (typeof j.detail === 'string') detail = j.detail
    } catch {
      /* body is not JSON */
    }
    throw new ApiError(res.status, detail, Number.isFinite(retry) && retry > 0 ? retry : null)
  }
  return res.json()
}

/** The typed API on top of a transport (HTTP or the in-browser fixtures). */
export function makeApi(t: Transport): Api {
  return {
    meta: (s) => t('GET', '/meta', undefined, s) as Promise<Meta>,
    destinationTypes: (s) => t('GET', '/destination-types', undefined, s) as Promise<DestinationType[]>,
    campusSites: (s) => t('GET', '/campus-sites', undefined, s) as Promise<CampusSite[]>,
    programmes: (s) => t('GET', '/programmes', undefined, s) as Promise<Programme[]>,
    personas: (s) => t('GET', '/personas', undefined, s) as Promise<Persona[]>,
    labelDestinations: (s) => t('GET', '/label-destinations', undefined, s) as Promise<LabelDestination[]>,
    // PROPOSED (N17): POST, so the typed address never lands in an access log.
    searchAddresses: (q, s) => t('POST', '/addresses/search', { q }, s) as Promise<AddressHit[]>,
    fit: (p, s) => t('POST', '/fit', p, s) as Promise<FitResponse>,
    cell: (id, p, s) => t('POST', `/cell/${encodeURIComponent(id)}`, p, s) as Promise<CellDetail>,
    listings: (p, s) => t('POST', '/listings/fit', p, s) as Promise<Listing[]>,
  }
}

let apiPromise: Promise<Api> | null = null

/** The app's API: fixtures (lazy chunk) in fixture mode, HTTP otherwise. */
export function getApi(): Promise<Api> {
  apiPromise ??= USE_FIXTURES
    ? import('./fixtures/transport').then((m) => makeApi(m.fixtureTransport))
    : Promise.resolve(makeApi(httpTransport))
  return apiPromise
}
