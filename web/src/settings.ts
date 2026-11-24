/**
 * Frontend-only settings (docs/app_screens.md §4). The API never reads them, so they live here
 * and not in config/config.yaml.
 */

/** Wait after the last profile change before a fit or cell request is sent. */
export const FIT_DEBOUNCE_MS = 300
/** Fit responses kept in memory, keyed by the normalised profile. */
export const FIT_CACHE_SIZE = 10
/** Wait after the last keystroke before the address search is sent. */
export const SEARCH_DEBOUNCE_MS = 250
/** Places in Check (product v1.1: up to three). */
export const MAX_PLACES = 3
/** "Better places nearby": radius around a place, metres (EPSG:3035). */
export const NEARBY_RADIUS_M = 1500
/** Fit difference below which two places count as "about equal". */
export const FIT_EQUAL_DELTA = 3
