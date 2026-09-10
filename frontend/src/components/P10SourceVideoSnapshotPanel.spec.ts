import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import P10SourceVideoSnapshotPanel from './P10SourceVideoSnapshotPanel.vue'
import * as projectApi from '@/features/projects/api'
import * as snapshotApi from '@/features/projects/sourceSnapshot'
import type { SourceVideoSnapshotRead } from '@/features/projects/sourceSnapshot'

vi.mock('@/features/projects/api', () => ({
  getProject: vi.fn(),
}))

vi.mock('@/features/projects/sourceSnapshot', async () => {
  const actual = await vi.importActual<typeof import('@/features/projects/sourceSnapshot')>('@/features/projects/sourceSnapshot')
  return {
    ...actual,
    getSourceVideoSnapshot: vi.fn(),
    listSourceVideoSnapshotRevisions: vi.fn(),
    finalizeSourceVideoSnapshot: vi.fn(),
  }
})

const notBuilt: SourceVideoSnapshotRead = {
  project_id: 'project-p10',
  status: 'NOT_BUILT',
  artifact_id: null,
  revision: null,
  input_fingerprint: null,
  content: null,
  provenance: null,
}

const frozenArtifacts = [
  'SOURCE_VIDEO',
  'SHOT_ANCHORS',
  'SOURCE_DIALOGUE',
  'SOURCE_BIBLE',
  'STORY_SKELETON',
  'RHYTHM_SKELETON',
  'SOURCE_SHOT_FACTS',
  'SOURCE_CHARACTERS',
  'SOURCE_SPEAKERS',
  'SOURCE_SCENES',
  'SOURCE_PROPS',
].map((artifactType, index) => ({
  artifact_type: artifactType,
  artifact_id: `artifact-${index + 1}`,
  revision: index + 1,
  input_fingerprint: `${index + 1}`.padStart(64, '0'),
}))

const current: SourceVideoSnapshotRead = {
  project_id: 'project-p10',
  status: 'CURRENT',
  artifact_id: 'snapshot-1',
  revision: 1,
  input_fingerprint: 'a'.repeat(64),
  content: {
    schema_version: '1.0',
    title: '原片分析定稿',
    source_truth_contract: 'frozen-accepted-source-facts-v1',
    frozen_artifacts: frozenArtifacts,
    episodes: [{
      episode_id: 'episode-1',
      source_asset_id: 'asset-1',
      episode_order: 1,
      source_filename: 'episode.mp4',
      source_asset_sha256: 'b'.repeat(64),
      duration_us: 5_000_000,
      width: 1080,
      height: 1920,
      codec_name: 'h264',
      avg_frame_rate: '25/1',
      has_audio: true,
      shot_boundary_set_id: 'boundary-1',
      shot_boundary_fingerprint: 'c'.repeat(64),
      source_evidence_set_id: 'evidence-1',
      source_evidence_fingerprint: 'd'.repeat(64),
      shot_anchors: [{ shot_anchor_id: 'shot-1', shot_number: 1, start_us: 0, end_us: 5_000_000, duration_us: 5_000_000 }],
      canonical_dialogue: [{ utterance_id: 'utt-1', utterance_number: 1, start_us: 1_000_000, end_us: 2_000_000, text: '原片对白', language: 'zh-CN' }],
      canonical_visual_text: [{ span_id: 'ocr-1', span_number: 1, start_us: 2_000_000, end_us: 3_000_000, text: '原片字幕', confidence: 0.99 }],
    }],
    source_bible: {},
    source_shot_facts: {},
    source_characters: { entities: [{}] },
    source_speakers: { entities: [{}, {}] },
    source_scenes: { entities: [{}] },
    source_props: { entities: [{}] },
  },
  provenance: {
    snapshot_contract: 'p10-source-video-snapshot-v1',
    schema_version: '1.0',
    source_truth_contract: 'frozen-accepted-source-facts-v1',
    professional_skill_id: 'source-video-snapshot',
    professional_skill_version: '1.0.0',
    publication_mode: 'DETERMINISTIC_FREEZE',
    source_chain_fingerprint: 'e'.repeat(64),
    frozen_artifacts: frozenArtifacts,
    episode_inputs: [{
      episode_id: 'episode-1',
      source_asset_id: 'asset-1',
      source_asset_sha256: 'b'.repeat(64),
      shot_boundary_set_id: 'boundary-1',
      shot_boundary_fingerprint: 'c'.repeat(64),
      source_evidence_set_id: 'evidence-1',
      source_evidence_fingerprint: 'd'.repeat(64),
    }],
    provider_jobs: [],
    supersedes_artifact_id: null,
  },
}

async function mountPanel(value: SourceVideoSnapshotRead = notBuilt) {
  vi.mocked(projectApi.getProject).mockResolvedValue({ id: 'project-p10', project_type: 'REPLICA' } as Awaited<ReturnType<typeof projectApi.getProject>>)
  vi.mocked(snapshotApi.getSourceVideoSnapshot).mockResolvedValue(value)
  vi.mocked(snapshotApi.listSourceVideoSnapshotRevisions).mockResolvedValue([])

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', component: P10SourceVideoSnapshotPanel }],
  })
  await router.push('/projects/project-p10')
  await router.isReady()
  const wrapper = mount(P10SourceVideoSnapshotPanel, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => vi.clearAllMocks())

describe('P10SourceVideoSnapshotPanel', () => {
  it('keeps initial load read-only and only finalizes after explicit click', async () => {
    const wrapper = await mountPanel()
    expect(snapshotApi.finalizeSourceVideoSnapshot).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="p10-provider-boundary"]').text()).toContain('GET 只读 · POST 显式定稿')
    expect(wrapper.text()).toContain('页面打开和刷新不会自动创建 Artifact、Task 或 ProviderJob')

    vi.mocked(snapshotApi.finalizeSourceVideoSnapshot).mockResolvedValue(current)
    const button = wrapper.get('.workspace-actions .primary-action')
    await button.trigger('click')
    await flushPromises()

    expect(snapshotApi.finalizeSourceVideoSnapshot).toHaveBeenCalledTimes(1)
    expect(snapshotApi.finalizeSourceVideoSnapshot).toHaveBeenCalledWith('project-p10')
    expect(wrapper.text()).toContain('SOURCE_VIDEO_SNAPSHOT rev 1')
    expect(wrapper.text()).toContain('没有重新调用模型')
    wrapper.unmount()
  })

  it('renders Speaker independently and exposes deterministic provenance', async () => {
    const wrapper = await mountPanel(current)
    const text = wrapper.text()
    expect(text).toContain('Speakers · 独立冻结')
    expect(text).toContain('P9 Speakers')
    expect(text).toContain('SOURCE_SPEAKERS')
    expect(text).toContain('ProviderJobs：0')
    expect(text).toContain('DETERMINISTIC_FREEZE')
    expect(text).toContain('source-video-snapshot@1.0.0')
    wrapper.unmount()
  })

  it('keeps stale history visible and requires another explicit finalize', async () => {
    const stale: SourceVideoSnapshotRead = { ...current, status: 'STALE' }
    const wrapper = await mountPanel(stale)
    expect(wrapper.text()).toContain('上游 CURRENT Source Artifact 已变化')
    expect(wrapper.text()).toContain('请显式重新定稿')
    expect(snapshotApi.finalizeSourceVideoSnapshot).not.toHaveBeenCalled()
    expect(wrapper.get('.workspace-actions .primary-action').text()).toBe('原片分析定稿')
    wrapper.unmount()
  })
})
