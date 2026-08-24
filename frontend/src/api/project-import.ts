import { API_BASE_URL } from './http'
import type { ProjectImportProgress, ProjectImportWorkflowResult } from '../types/project-import'
import type { ApiErrorPayload, CreateProjectPayload } from '../types/project'

/**
 * Workflow 01「导入原片」单一 HTTP 入口。
 *
 * 浏览器只提交一次 multipart/form-data；后端依次编排 Project、Source、Preprocess。
 * 不手动设置 Content-Type，必须让浏览器生成 multipart boundary。
 */
export function importProjectSource(
  payload: CreateProjectPayload,
  file: File,
  onProgress?: (progress: ProjectImportProgress) => void,
): Promise<ProjectImportWorkflowResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE_URL}/api/project-imports`)
    xhr.responseType = 'json'

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || event.total <= 0) return
      onProgress?.({
        loaded: event.loaded,
        total: event.total,
        percent: Math.min(100, Math.round((event.loaded / event.total) * 100)),
      })
    }

    xhr.onerror = () => reject(new Error('导入原片失败，请检查本地后端是否正常运行'))
    xhr.onabort = () => reject(new Error('导入原片已取消'))
    xhr.onload = () => {
      const response = xhr.response as ProjectImportWorkflowResult | ApiErrorPayload | null
      if (xhr.status >= 200 && xhr.status < 300 && response) {
        resolve(response as ProjectImportWorkflowResult)
        return
      }

      const apiError = response as ApiErrorPayload | null
      const error = new Error(apiError?.error?.message || `导入原片失败（HTTP ${xhr.status}）`)
      ;(error as Error & { code?: string }).code = apiError?.error?.code
      reject(error)
    }

    const form = new FormData()
    form.append('name', payload.name)
    if (payload.source_language) form.append('source_language', payload.source_language)
    form.append('target_language', payload.target_language)
    form.append('target_region', payload.target_region)
    if (payload.workspace_root) form.append('workspace_root', payload.workspace_root)
    form.append('file', file, file.name)
    xhr.send(form)
  })
}
