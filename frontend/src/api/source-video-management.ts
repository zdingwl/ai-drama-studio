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

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isSourceVideoEpisode(value: unknown): value is SourceVideoEpisode {
  if (!isRecord(value)) return false
  return typeof value.id === 'string'
    && value.id.length > 0
    && typeof value.project_id === 'string'
    && typeof value.title === 'string'
    && typeof value.original_filename === 'string'
    && typeof value.sort_order === 'number'
    && Number.isFinite(value.sort_order)
}

function parseSourceVideoEpisode(value: unknown, context: string): SourceVideoEpisode {
  if (!isSourceVideoEpisode(value)) {
    throw new Error(`${context}返回格式异常：缺少有效的剧集基础字段`)
  }
  return value
}

function parseSourceVideoList(value: unknown): SourceVideoEpisode[] {
  if (!Array.isArray(value)) {
    throw new Error('原短剧视频接口返回格式异常：预期为视频数组')
  }
  return value.map((episode, index) => parseSourceVideoEpisode(episode, `原短剧视频第 ${index + 1} 项`))
}

export async function listProjectSourceVideos(projectId: string): Promise<SourceVideoEpisode[]> {
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/source-videos`)
  if (!response.ok) throw new Error(await parseFetchError(response))
  const payload: unknown = await response.json()
  return parseSourceVideoList(payload)
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
      try {
        const episode = parseSourceVideoEpisode(xhr.response as unknown, '视频上传接口')
        onProgress({ loaded: file.size, total: file.size, percent: 100 })
        resolve(episode)
      } catch (error) {
        reject(error instanceof Error ? error : new Error('上传成功但服务端未返回有效剧集数据'))
      }
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
