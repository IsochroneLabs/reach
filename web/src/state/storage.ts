/**
 * localStorage, wrapped: private modes, blocked storage and full quotas never break the app; the
 * profile is then kept in memory and in the link only (docs/app_screens.md §3.2).
 */
let blocked = false

export const storage = {
  get(key: string): string | null {
    try {
      return window.localStorage.getItem(key)
    } catch {
      blocked = true
      return null
    }
  },
  set(key: string, value: string): void {
    try {
      window.localStorage.setItem(key, value)
    } catch {
      blocked = true
    }
  },
  remove(key: string): void {
    try {
      window.localStorage.removeItem(key)
    } catch {
      blocked = true
    }
  },
  /** True once a read or write failed. */
  get blocked(): boolean {
    return blocked
  },
}
