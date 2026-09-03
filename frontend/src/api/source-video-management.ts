import type { Episode } from '../types/studio'

export interface SourceVideoEpisode extends Episode {
  file_size_bytes: number | null
}

export interface EpisodeUploadProgress {
  loaded: number
  total: number
  percent: number
}

function detailMessage(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object') {
    const payload = detail as { message?: unknown }
    if (typeof payload.message === 'string' && payload.message.trim()) return payload.message
  }
  return null
}

function parseUploadError(xhr: XMLHttpRequest): string {
  try {
    const response = xhr.response as unknown
    if (response && typeof response === 'object') {
      const payload = response as { detail?: unknown }
      const message = detailMessage(payload.detail)
      if (message) return message
    }
    if (typeof response === 'string' && response.trim()) {
      const payload = JSON.parse(response) as { detail?: unknown }
      const message = detailMessage(payload.detail)
      if (message) return message
    }
  } catch {
    // 保留通用错误信息。
  }
  return `上传失败（${xhr.status || '网络错误'}）`
}

async function parseFetchError(response: Response): Promise<string> {
  try {
    const payload = await response.json() as { detail?: unknown }
    const message = detailMessage(payload.detail)
    if (message) return message
  } catch {
    // 保留通用错误信息。
  }
  return `请求失败（${response.status}）`
}

export async function listProjectSourceVideos(projectId: string): Promise<SourceVideoEpisode[]> {
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/source-videos`)
  if (!response.ok) throw new Error(await parseFetchError(response))
  return response.json() as Promise<SourceVideoEpisode[]>
}

function uploadWithProgress(
  method: 'POST' | 'PUT',
  url: string,
  file: File,
  onProgress: (progress: EpisodeUploadProgress) => void,
): Promise<SourceVideoEpisode> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const body = new FormData()
    body.append('file', file)

    xhr.open(method, url)
    xhr.responseType = 'json'

    xhr.upload.addEventListener('progress', (event) => {
      if (!event.lengthComputable || event.total <= 0) return
      const percent = Math.min(100, Math.max(0, Math.round((event.loaded / event.total) * 100)))
      onProgress({ loaded: event.loaded, total: event.total, percent })
    })

    xhr.addEventListener('load', () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(parseUploadError(xhr)))
        return
      }
      const episode = xhr.response as SourceVideoEpisode | null
      if (!episode?.id) {
        reject(new Error('上传成功但服务端未返回剧集数据'))
        return
      }
      onProgress({ loaded: file.size, total: file.size, percent: 100 })
      resolve(episode)
    })

    xhr.addEventListener('error', () => reject(new Error('网络异常，视频上传失败')))
    xhr.addEventListener('abort', () => reject(new Error('视频上传已取消')))
    xhr.send(body)
  })
}

/**
 * 正式项目页逐文件上传入口。
 * 批量选择后仍按用户选择顺序逐文件调用，失败项可单独重试且不会重复上传成功项。
 */
export function uploadEpisodeWithProgress(
  projectId: string,
  file: File,
  onProgress: (progress: EpisodeUploadProgress) => void,
): Promise<SourceVideoEpisode> {
  return uploadWithProgress(
    'POST',
    `/api/projects/${encodeURIComponent(projectId)}/source-videos`,
    file,
    onProgress,
  )
}

/**
 * 原地替换某一 Episode 的 Source Video。Episode ID 与排序保持不变；
 * 后端会使依赖旧原片的镜头检测、AI 拉片和资产结果失效。
 */
export function replaceEpisodeWithProgress(
  episodeId: string,
  file: File,
  onProgress: (progress: EpisodeUploadProgress) => void,
): Promise<SourceVideoEpisode> {
  return uploadWithProgress(
    'PUT',
    `/api/episodes/${encodeURIComponent(episodeId)}/source`,
    file,
    onProgress,
  )
}
