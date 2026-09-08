export type ProjectType =
  | 'REPLICA'
  | 'REDRAW'
  | 'TRANSLATION'
  | 'NOVEL_TO_DRAMA'
  | 'SCRIPT_TO_DRAMA'
  | 'SCRIPT_LOCALIZATION'

export type SceneStrategy = 'KEEP' | 'LOCALIZE' | 'MIXED'
export type AudioPolicy = 'KEEP_SOURCE_AUDIO' | 'REGENERATE_AUDIO'
export type PlanStepStatus = 'COMPLETED' | 'READY' | 'BLOCKED_DEPENDENCY' | 'WAITING_CAPABILITY'
export type TaskStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'interrupted'

export interface ProjectTypeOption {
  value: ProjectType
  label: string
  description: string
  icon: string
}

export const PROJECT_TYPE_OPTIONS: readonly ProjectTypeOption[] = [
  { value: 'REPLICA', label: '复刻短剧', description: '保留故事与节奏，换人物、地区、文化和语言重新拍。', icon: '🎬' },
  { value: 'REDRAW', label: '重绘短剧', description: '保持内容和表演结构，重点重新生成视觉。', icon: '🎨' },
  { value: 'TRANSLATION', label: '翻译短剧', description: '原画面为主，重做目标语言配音、口型和字幕。', icon: '🌍' },
  { value: 'NOVEL_TO_DRAMA', label: '小说生成短剧', description: '把小说先改编成短剧，再完成分镜和视频生成。', icon: '📖' },
  { value: 'SCRIPT_TO_DRAMA', label: '剧本生成短剧', description: '把已有剧本整理成导演分镜并生成成片。', icon: '📝' },
  { value: 'SCRIPT_LOCALIZATION', label: '剧本本土化', description: '把剧本改成目标地区真正成立的版本。', icon: '🌐' },
] as const

export const VIDEO_PROJECT_TYPES = new Set<ProjectType>(['REPLICA', 'REDRAW', 'TRANSLATION'])

export const LANGUAGE_OPTIONS = [
  { value: 'zh-CN', label: '中文（简体）' },
  { value: 'en-US', label: '英语（美国）' },
  { value: 'en-GB', label: '英语（英国）' },
  { value: 'es-ES', label: '西班牙语' },
  { value: 'pt-BR', label: '葡萄牙语（巴西）' },
  { value: 'id-ID', label: '印度尼西亚语' },
  { value: 'ja-JP', label: '日语' },
  { value: 'ko-KR', label: '韩语' },
  { value: 'th-TH', label: '泰语' },
  { value: 'vi-VN', label: '越南语' },
  { value: 'ar-SA', label: '阿拉伯语' },
] as const

export const REGION_OPTIONS = [
  { value: 'US', label: '美国' },
  { value: 'GB', label: '英国' },
  { value: 'CA', label: '加拿大' },
  { value: 'AU', label: '澳大利亚' },
  { value: 'ES', label: '西班牙' },
  { value: 'MX', label: '墨西哥' },
  { value: 'BR', label: '巴西' },
  { value: 'ID', label: '印度尼西亚' },
  { value: 'JP', label: '日本' },
  { value: 'KR', label: '韩国' },
  { value: 'TH', label: '泰国' },
  { value: 'VN', label: '越南' },
  { value: 'SA', label: '沙特阿拉伯' },
  { value: 'AE', label: '阿联酋' },
] as const

export interface ProjectRead {
  id: string
  name: string
  project_type: ProjectType
  source_language: string | null
  target_language: string
  target_region: string
  scene_strategy: SceneStrategy
  audio_policy: AudioPolicy
  status: 'ACTIVE' | 'ARCHIVED'
  workflow_revision: number
  created_at: string
  updated_at: string
}

export interface ProjectCreatePayload {
  name: string
  project_type: ProjectType
  source_language?: string | null
  target_language: string
  target_region: string
  scene_strategy?: SceneStrategy
  audio_policy?: AudioPolicy
}

export interface ExecutionPlanStep {
  id: string
  phase: string
  title: string
  description: string
  status: PlanStepStatus
  capabilities: string[]
  requires: string[]
  produces: string[]
  missing_artifacts: string[]
}

export interface ProjectExecutionPlan {
  project_id: string
  project_type: ProjectType
  skill_id: string
  skill_title: string
  workflow_revision: number
  steps: ExecutionPlanStep[]
}

export interface TaskRead {
  id: string
  project_id: string
  task_name: string
  progress_percent: number
  status: TaskStatus
  last_error: string | null
  attempt: number
  max_attempts: number
  can_retry: boolean
  can_cancel: boolean
  can_resume: boolean
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export function projectTypeLabel(type: ProjectType): string {
  return PROJECT_TYPE_OPTIONS.find((item) => item.value === type)?.label ?? type
}
