export interface SourceScreenplayAction {
  text: string
  source_refs: string[]
}

export interface SourceScreenplayDialogue {
  dialogue_group_id: string
  speaker: string
  text: string
  start_us: number
  end_us: number
  source_refs: string[]
}

export interface SourceScreenplayScene {
  scene_key: string
  heading: string
  source_refs: string[]
  actions: SourceScreenplayAction[]
  dialogue: SourceScreenplayDialogue[]
  story_beat_refs: string[]
}

export interface SourceScreenplay {
  source_revision: string
  source_fingerprint: string
  episode_id: string
  title: string
  status: 'READY' | 'READY_WITH_WARNINGS'
  scenes: SourceScreenplayScene[]
  screenplay_text: string
  unresolved: string[]
}

export interface EpisodeUnderstanding {
  episode_summary: string
}

export interface SourceScreenplayCompilation {
  status: 'READY' | 'READY_WITH_WARNINGS'
  episode_id: string
  source_fingerprint: string
  input_fingerprint: string
  output_fingerprint: string
  episode_understanding: EpisodeUnderstanding
  screenplay: SourceScreenplay
}

export interface SourceScreenplayRead {
  state: 'MISSING' | 'READY' | 'STALE'
  episode_id: string
  source_fingerprint: string
  message: string
  compilation: SourceScreenplayCompilation | null
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json() as { detail?: unknown }
    if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail
  } catch {
    // 保留通用错误。
  }
  return `请求失败（${response.status}）`
}

export async function getSourceScreenplay(episodeId: string): Promise<SourceScreenplayRead> {
  const response = await fetch(`/api/episodes/${encodeURIComponent(episodeId)}/source-screenplay`)
  if (!response.ok) throw new Error(await errorMessage(response))
  return response.json() as Promise<SourceScreenplayRead>
}

export async function compileSourceScreenplay(episodeId: string): Promise<SourceScreenplayCompilation> {
  const response = await fetch(`/api/episodes/${encodeURIComponent(episodeId)}/source-screenplay/compile`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error(await errorMessage(response))
  return response.json() as Promise<SourceScreenplayCompilation>
}
