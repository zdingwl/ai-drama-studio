/** F01 前端使用的项目基础数据。只包含创建项目阶段需要的字段。 */
export interface Project {
  id: string
  name: string
  source_language: string | null
  target_language: string
  target_region: string
  workspace_path: string
  project_format_version: number
  status: 'creating' | 'ready'
  created_at: string
  last_opened_at: string | null
}

/** 新建项目表单提交给后端的字段。 */
export interface CreateProjectPayload {
  name: string
  source_language?: string | null
  target_language: string
  target_region: string
  workspace_root?: string | null
}

export interface ApiErrorPayload {
  error: {
    code: string
    message: string
  }
}
