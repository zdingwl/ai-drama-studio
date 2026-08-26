export type ShotCacheScope = 'transitions' | 'transvlm' | 'flow' | 'preprocess' | 'all'
export type ShotRecomputeMode = 'auto' | ShotCacheScope

export interface ShotCacheLayers {
  preprocess: boolean
  flow: boolean
  transvlm: boolean
  transitions: boolean
}

export interface ShotCacheStatus {
  schema: string
  root: string
  manifest_valid: boolean
  layers: ShotCacheLayers
  transition_cache_usable: boolean
  bytes: number
  episode_id: string
  project_id: string
}

export interface ShotCacheClearResult {
  episode_id: string
  project_id: string
  cleared: {
    scope: ShotCacheScope
    deleted: string[]
    bytes_removed: number
  }
  cache: ShotCacheStatus
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const payload = await response.json()
      message = payload.detail || message
    } catch {
      // Keep the status-based fallback for non-JSON failures.
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export const shotCacheApi = {
  getEpisodeCache: (episodeId: string) =>
    request<ShotCacheStatus>(`/api/episodes/${episodeId}/shot-cache`),

  clearEpisodeCache: (episodeId: string, scope: ShotCacheScope) =>
    request<ShotCacheClearResult>(`/api/episodes/${episodeId}/shot-cache?scope=${encodeURIComponent(scope)}`, {
      method: 'DELETE',
    }),
}
