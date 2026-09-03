import type { Episode } from '../types/studio'

export interface EpisodeUploadProgress {
  loaded: number
  total: number
  percent: number
}

function parseUploadError(xhr: XMLHttpRequest): string {
  try {
    const payload = JSON.parse(xhr.responseText || '{}') as { detail?: string }
    if (payload.detail) return payload.detail
  } catch {
    // 保留通用错误信息。
  }
  return `上传失败（${xhr.status || '网络错误'}）`
}

/**
 * 使用 XHR 是为了获得浏览器真实的上传字节进度。
 * 后端仍复用现有 /episodes/batch 接口；每次只提交一个文件，便于逐文件重试且避免成功文件重复上传。
 */
export function uploadEpisodeWithProgress(
  projectId: string,
  file: File,
  onProgress: (progress: EpisodeUploadProgress) => void,
): Promise<Episode> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const body = new FormData()
    body.append('files', file)

    xhr.open('POST', `/api/projects/${encodeURIComponent(projectId)}/episodes/batch`)
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
      const payload = xhr.response as Episode[] | null
      const episode = Array.isArray(payload) ? payload[0] : null
      if (!episode) {
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
