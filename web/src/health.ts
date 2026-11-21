/** API health as returned by GET /api/health (api/src/reach_api/main.py). */
export interface Health {
  status: string
  version: string
  build_sha: string
}

export type ApiState =
  | { kind: 'none' }
  | { kind: 'loading' }
  | { kind: 'ok'; health: Health }
  | { kind: 'error'; message: string }

/** Fetch the API health; never throws. */
export async function fetchHealth(base: string, signal?: AbortSignal): Promise<ApiState> {
  if (!base) return { kind: 'none' }
  try {
    const res = await fetch(`${base}/health`, { signal })
    if (!res.ok) return { kind: 'error', message: `HTTP ${res.status}` }
    return { kind: 'ok', health: (await res.json()) as Health }
  } catch (err) {
    return { kind: 'error', message: err instanceof Error ? err.message : String(err) }
  }
}
