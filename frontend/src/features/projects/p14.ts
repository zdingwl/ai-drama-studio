import { apiRequest } from '@/lib/api'
import type { TaskRead } from './types'

export type ReviewStatus = 'NEEDS_REVIEW' | 'ACCEPTED' | 'REJECTED' | 'SUPERSEDED'

export interface VoiceBinding {
  scope: 'CHARACTER' | 'UTTERANCE'
  target_character_id?: string
  utterance_id?: string
  voice_id: string
  voice_label?: string
}

export interface AudioClip {
  clip_id: string
  utterance_id: string
  utterance_number: number
  target_character_id: string | null
  final_target_dialogue: string
  voice_id: string
  voice_label: string | null
  media_url: string
  actual_speech_duration_us: number
}

export interface TargetAudioContent {
  target_script_artifact_id: string
  target_bible_artifact_id: string
  clips: AudioClip[]
}

export interface TargetAudioRead {
  status: 'NOT_BUILT' | 'CURRENT' | 'STALE'
  artifact_id: string | null
  content: TargetAudioContent | null
}

export interface AudioCandidate {
  id: string
  generation_sequence: number
  review_status: ReviewStatus
  content: TargetAudioContent
}

export interface TimingItem {
  utterance_id: string
  utterance_number: number
  source_slot_duration_us: number
  actual_speech_duration_us: number
  residual_hold_us: number
  overflow_us: number
  fit_status: 'FIT' | 'OVERFLOW'
}

export interface TimingContent {
  target_script_artifact_id: string
  target_audio_artifact_id: string
  items: TimingItem[]
  has_overflow: boolean
  total_overflow_us: number
}

export interface TimingRead {
  status: 'NOT_BUILT' | 'CURRENT' | 'STALE'
  artifact_id: string | null
  content: TimingContent | null
}

export interface TimingCandidate {
  id: string
  generation_sequence: number
  review_status: ReviewStatus
  content: TimingContent
}

export const getTargetAudio = (projectId: string) => apiRequest<TargetAudioRead>(`/projects/${projectId}/target-audio`, { cache: 'no-store' })
export const listAudioCandidates = (projectId: string) => apiRequest<AudioCandidate[]>(`/projects/${projectId}/target-audio/candidates`, { cache: 'no-store' })
export const startTargetAudio = (projectId: string, bindings: VoiceBinding[], key: string) => apiRequest<TaskRead>(`/projects/${projectId}/commands/target-audio`, { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ bindings }) })
export const reviewAudioCandidate = (projectId: string, candidate: AudioCandidate, accept: boolean, scriptId: string, bibleId: string, reason: string) => apiRequest( `/projects/${projectId}/target-audio/candidates/${candidate.id}/commands/${accept ? 'accept' : 'reject'}`, { method: 'POST', body: JSON.stringify({ expected_target_script_artifact_id: scriptId, expected_target_bible_artifact_id: bibleId, expected_generation_sequence: candidate.generation_sequence, reason }) })
export const getTimingPlan = (projectId: string) => apiRequest<TimingRead>(`/projects/${projectId}/timing-plan`, { cache: 'no-store' })
export const listTimingCandidates = (projectId: string) => apiRequest<TimingCandidate[]>(`/projects/${projectId}/timing-plan/candidates`, { cache: 'no-store' })
export const startTimingPlan = (projectId: string, key: string) => apiRequest<TaskRead>(`/projects/${projectId}/commands/timing-plan`, { method: 'POST', headers: { 'Idempotency-Key': key } })
export const reviewTimingCandidate = (projectId: string, candidate: TimingCandidate, accept: boolean, scriptId: string, audioId: string, reason: string) => apiRequest(`/projects/${projectId}/timing-plan/candidates/${candidate.id}/commands/${accept ? 'accept' : 'reject'}`, { method: 'POST', body: JSON.stringify({ expected_target_script_artifact_id: scriptId, expected_target_audio_artifact_id: audioId, expected_generation_sequence: candidate.generation_sequence, reason }) })
