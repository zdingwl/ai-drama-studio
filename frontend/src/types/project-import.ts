import type { SourcePreprocess } from './preprocess'
import type { Project } from './project'
import type { SourceVideo } from './source-video'

/** Workflow 01「导入原片」一次成功后的完整结果。 */
export interface ProjectImportWorkflowResult {
  status: 'ready'
  project: Project
  source_video: SourceVideo
  preprocess: SourcePreprocess
}

/** Workflow 01 前端用于展示上传阶段真实字节进度。 */
export interface ProjectImportProgress {
  loaded: number
  total: number
  percent: number
}
