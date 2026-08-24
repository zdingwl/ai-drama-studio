import { API_BASE_URL, apiRequest } from './http'
import type { ApiErrorPayload } from '../types/project'
import type { SourceVideo, SourceVideoUploadProgress } from '../types/source-video'

/** 页面加载/刷新时读取当前项目已经 ready 的 Source Video；没有原片时返回 null。 */
export function fetchSourceVideo(projectId: string): Promise<SourceVideo | null> {
  return apiRequest<SourceVideo | null>(`/api/projects/${encodeURIComponent(projectId)}/source-video`)
}

/**
 * 使用原生 XMLHttpRequest 上传大视频，从而获得浏览器真实 upload progress。
 *
 * 这里不手动设置 Content-Type；浏览器必须自己给 multipart/form-data 生成 boundary。
 * 文件合法性、Hash、FFprobe 和一项目一原片规则全部由后端负责。
 */
export function uploadSourceVideo(
  projectId: string,
  file: File,
  onProgress?: (progress: SourceVideoUploadProgress) => void,
): Promise<SourceVideo> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE_URL}/api/projects/${encodeURIComponent(projectId)}/source-video`)
    xhr.responseType = 'json'

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || event.total <= 0) return
      onProgress?.({
        loaded: event.loaded,
        total: event.total,
        percent: Math.min(100, Math.round((event.loaded / event.total) * 100)),
      })
    }

    xhr.onerror = () => reject(new Error('原视频上传失败，请检查本地后端是否正常运行'))
    xhr.onabort = () => reject(new Error('原视频上传已取消'))
    xhr.onload = () => {
      const payload = xhr.response as SourceVideo | ApiErrorPayload | null
      if (xhr.status >= 200 && xhr.status < 300 && payload) {
        resolve(payload as SourceVideo)
        return
      }

      const apiError = payload as ApiErrorPayload | null
      const error = new Error(apiError?.error?.message || `原视频上传失败（HTTP ${xhr.status}）`)
      ;(error as Error & { code?: string }).code = apiError?.error?.code
      reject(error)
    }

    const form = new FormData()
    form.append('file', file, file.name)
    xhr.send(form)
  })
}
