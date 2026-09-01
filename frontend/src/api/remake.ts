import type {
  EpisodeOutputPlan,
  GenerationAttemptSummary,
  GenerationQualityCheck,
  GenerationQualitySummary,
  GenerationSegmentPlan,
  GenerationSelection,
  H3RuntimeStatus,
  LipSyncRuntimeStatus,
  PostProductionPlan,
  ProjectRemakePolicy,
  RemakeEpisodeTimeline,
  RemakeProjectTimeline,
  ReviewIssue,
  ReviewIssueStatus,
  SceneLocalizationMapping,
  ScenePolicy,
  TargetCharacter,
  TargetDialogue,
  TargetDialogueBundle,
  TargetLocalizationBundle,
  TimingStrategy,
  TtsRuntimeStatus,
} from '../types/remake'
import type { BackgroundTask } from '../types/studio'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const payload = await response.json()
      message = payload.detail || message
    } catch {
      // Keep the default message for non-JSON errors.
    }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function requestTask(url: string): Promise<BackgroundTask> {
  const task = await request<BackgroundTask>(url, { method: 'POST' })
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('studio-task-created', { detail: task }))
  }
  return task
}

const jsonHeaders = { 'Content-Type': 'application/json' }

export const remakeApi = {
  getPolicy: (projectId: string) => request<ProjectRemakePolicy>(`/api/projects/${projectId}/remake-policy`),
  updatePolicy: (projectId: string, scenePolicy: ScenePolicy) => request<ProjectRemakePolicy>(`/api/projects/${projectId}/remake-policy`, {
    method: 'PATCH',
    headers: jsonHeaders,
    body: JSON.stringify({ scene_policy: scenePolicy, generation_engine: 'MINIMAX_H3_LOCAL' }),
  }),
  startAutoPrepare: (projectId: string) => requestTask(`/api/projects/${projectId}/tasks/auto-remake-prepare`),
  listReviewIssues: (projectId: string, status: ReviewIssueStatus | '' = 'OPEN') => request<ReviewIssue[]>(
    `/api/projects/${projectId}/review-issues${status ? `?status=${status}` : '?status='}`,
  ),
  setReviewIssueStatus: (issueId: string, status: ReviewIssueStatus, resolution: unknown = null) => request<ReviewIssue>(`/api/review-issues/${issueId}`, {
    method: 'PATCH',
    headers: jsonHeaders,
    body: JSON.stringify({ status, resolution }),
  }),
  getTargetLocalization: (projectId: string) => request<TargetLocalizationBundle>(`/api/projects/${projectId}/target-localization`),
  generateTargetLocalization: (projectId: string) => request<TargetLocalizationBundle>(`/api/projects/${projectId}/target-localization/generate`, { method: 'POST' }),
  updateTargetCharacter: (id: string, payload: Pick<TargetCharacter, 'target_name' | 'appearance_profile' | 'generation_prompt'>) => request<TargetCharacter>(`/api/target-characters/${id}`, {
    method: 'PATCH',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  }),
  deleteTargetCharacter: (id: string) => request<void>(`/api/target-characters/${id}`, { method: 'DELETE' }),
  updateSceneLocalization: (id: string, payload: { decision: 'KEEP' | 'LOCALIZE'; target_label?: string | null; target_description?: string | null; reason?: string | null }) => request<SceneLocalizationMapping>(`/api/scene-localization-mappings/${id}`, {
    method: 'PATCH',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  }),
  deleteSceneLocalization: (id: string) => request<void>(`/api/scene-localization-mappings/${id}`, { method: 'DELETE' }),
  getTargetDialogue: (projectId: string) => request<TargetDialogueBundle>(`/api/projects/${projectId}/target-dialogue`),
  generateTargetDialogue: (projectId: string, synthesizeAudio = true) => request<TargetDialogueBundle>(`/api/projects/${projectId}/target-dialogue/generate`, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ synthesize_audio: synthesizeAudio }),
  }),
  generateTargetDialogueText: (projectId: string) => request<TargetDialogueBundle>(`/api/projects/${projectId}/target-dialogue/generate-text`, { method: 'POST' }),
  materializeTargetDialogueAudio: (projectId: string) => request<TargetDialogueBundle>(`/api/projects/${projectId}/target-dialogue/materialize-audio`, { method: 'POST' }),
  updateTargetDialogue: (id: string, payload: { translated_text?: string | null; localized_text?: string | null; final_text: string }) => request<TargetDialogue>(`/api/target-dialogues/${id}`, {
    method: 'PATCH',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  }),
  targetDialogueAudioUrl: (id: string) => `/api/target-dialogues/${id}/audio`,
  getTtsRuntimeStatus: () => request<TtsRuntimeStatus>('/api/tts/runtime-status'),
  getRemakeTimeline: (projectId: string) => request<RemakeProjectTimeline>(`/api/projects/${projectId}/remake-timeline`),
  generateRemakeTimeline: (projectId: string) => request<RemakeProjectTimeline>(`/api/projects/${projectId}/remake-timeline/generate`, { method: 'POST' }),
  updateRemakeShotTiming: (
    timelineId: string,
    shotPlanId: string,
    payload: { strategy: TimingStrategy; planned_duration_us: number; carry_over_shot_key?: string | null; reason?: string | null },
  ) => request<RemakeEpisodeTimeline>(`/api/remake-timelines/${timelineId}/shots/${shotPlanId}`, {
    method: 'PATCH',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  }),
  getGenerationSegments: (projectId: string) => request<GenerationSegmentPlan>(`/api/projects/${projectId}/generation-segments`),
  compileGenerationSegments: (projectId: string) => request<GenerationSegmentPlan>(`/api/projects/${projectId}/generation-segments/compile`, { method: 'POST' }),
  getH3RuntimeStatus: () => request<H3RuntimeStatus>('/api/h3/runtime'),
  listGenerationAttempts: (projectId: string) => request<GenerationAttemptSummary>(`/api/projects/${projectId}/generation-attempts`),
  startH3Generation: (projectId: string) => requestTask(`/api/projects/${projectId}/tasks/h3-generate-ready`),
  generationAttemptVideoUrl: (attemptId: string) => `/api/generation-attempts/${attemptId}/video`,
  getH3Quality: (projectId: string) => request<GenerationQualitySummary>(`/api/projects/${projectId}/h3-quality`),
  checkGenerationAttempt: (attemptId: string) => request<GenerationQualityCheck>(`/api/generation-attempts/${attemptId}/quality-check`, { method: 'POST' }),
  selectGenerationAttempt: (attemptId: string) => request<GenerationSelection>(`/api/generation-attempts/${attemptId}/select`, { method: 'POST' }),
  retryH3Segment: (projectId: string, segmentId: string) => requestTask(`/api/projects/${projectId}/generation-segments/${segmentId}/tasks/h3-qc-retry`),
  selectedGenerationVideoUrl: (projectId: string, segmentId: string) => `/api/generation-segments/${segmentId}/selected-video?project_id=${encodeURIComponent(projectId)}`,

  getLipSyncRuntimeStatus: () => request<LipSyncRuntimeStatus>('/api/lip-sync/runtime'),
  getPostProduction: (projectId: string) => request<PostProductionPlan>(`/api/projects/${projectId}/postproduction`),
  getEpisodeOutputs: (projectId: string) => request<EpisodeOutputPlan>(`/api/projects/${projectId}/outputs`),
  startPostProduction: (projectId: string) => requestTask(`/api/projects/${projectId}/tasks/postproduction`),
  postProductionSegmentVideoUrl: (projectId: string, segmentId: string) => `/api/postproduction-segments/${segmentId}/video?project_id=${encodeURIComponent(projectId)}`,
  episodeFinalVideoUrl: (projectId: string, episodeId: string) => `/api/episodes/${episodeId}/final-video?project_id=${encodeURIComponent(projectId)}`,
  episodeSubtitleUrl: (projectId: string, episodeId: string) => `/api/episodes/${episodeId}/subtitles?project_id=${encodeURIComponent(projectId)}`,
}
