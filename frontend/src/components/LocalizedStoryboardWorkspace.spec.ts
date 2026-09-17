import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import LocalizedStoryboardWorkspace from './LocalizedStoryboardWorkspace.vue'
import * as projectApi from '@/features/projects/api'
import * as replicaApi from '@/features/projects/replicaFiveStep'
import type { TaskRead } from '@/features/projects/types'

vi.mock('@/features/projects/api', () => ({
  listProjectTasks: vi.fn(),
}))

vi.mock('@/features/projects/replicaFiveStep', () => ({
  getLocalizedStoryboard: vi.fn(),
  listLocalizedStoryboardCandidates: vi.fn(),
  reviewLocalizedStoryboard: vi.fn(),
  startLocalizedStoryboard: vi.fn(),
  updateLocalizedStoryboardShot: vi.fn(),
}))

const runningTask: TaskRead = {
  id: 'localized-task-1',
  project_id: 'project-1',
  task_type: 'replica.localized-storyboard',
  task_name: '本土化分镜',
  progress_percent: 42,
  status: 'running',
  last_error: null,
  attempt: 1,
  max_attempts: 3,
  can_retry: false,
  can_cancel: true,
  can_resume: false,
  created_at: '2026-09-14T07:15:00Z',
  started_at: '2026-09-14T07:15:01Z',
  finished_at: null,
}

function mockReads(tasks: TaskRead[] = []) {
  vi.mocked(replicaApi.getLocalizedStoryboard).mockResolvedValue({
    project_id: 'project-1',
    status: 'NOT_BUILT',
    artifact_id: null,
    revision: null,
    content: null,
  })
  vi.mocked(replicaApi.listLocalizedStoryboardCandidates).mockResolvedValue([])
  vi.mocked(projectApi.listProjectTasks).mockResolvedValue(tasks)
}

async function mountWorkspace() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', component: { template: '<main />' } }],
  })
  await router.push('/projects/project-1')
  await router.isReady()
  const wrapper = mount(LocalizedStoryboardWorkspace, {
    global: { plugins: [router] },
  })
  await flushPromises()
  return wrapper
}

afterEach(() => vi.clearAllMocks())

describe('LocalizedStoryboardWorkspace task progress', () => {
  it('restores and displays a running localization task with its real progress', async () => {
    mockReads([runningTask])

    const wrapper = await mountWorkspace()

    const progress = wrapper.get('[data-testid="localized-storyboard-progress"]')
    expect(progress.text()).toContain('正在生成')
    expect(progress.text()).toContain('42%')
    const track = progress.get('[role="progressbar"]')
    expect(track.attributes('aria-valuenow')).toBe('42')
    expect(track.get('.progress-value').attributes('style')).toContain('width: 42%')
    const generate = wrapper.findAll('button').find(button => button.text().includes('本土化中 42%'))
    expect(generate).toBeTruthy()
    expect(generate?.attributes('disabled')).toBeDefined()

    wrapper.unmount()
  })

  it('shows progress immediately after starting a new localization task', async () => {
    mockReads([])
    const queuedTask = { ...runningTask, status: 'queued' as const, progress_percent: 0, started_at: null }
    vi.mocked(replicaApi.startLocalizedStoryboard).mockResolvedValue(queuedTask)

    const wrapper = await mountWorkspace()
    const generate = wrapper.findAll('button').find(button => button.text() === '生成本土化分镜')
    expect(generate).toBeTruthy()
    await generate!.trigger('click')
    await flushPromises()

    expect(replicaApi.startLocalizedStoryboard).toHaveBeenCalledWith('project-1')
    const progress = wrapper.get('[data-testid="localized-storyboard-progress"]')
    expect(progress.text()).toContain('排队中')
    expect(progress.text()).toContain('0%')
    expect(wrapper.text()).toContain('可在下方查看实时进度')

    wrapper.unmount()
  })
})

describe('LocalizedStoryboardWorkspace editing', () => {
  it('edits a confirmed shot and saves it as a review candidate', async () => {
    const content = {
      source_snapshot_artifact_id: 'snapshot-1', target_language: 'en-US', target_region: 'US', characters: [], scenes: [], props: [], dialogue: [],
      shots: [{
        storyboard_shot_id: 'shot-1', episode_id: 'episode-1', episode_order: 1, source_shot_anchor_id: 'anchor-1', shot_number: 1,
        start_us: 0, end_us: 2_000_000, duration_us: 2_000_000, output_ratio: '9:16', source_visual_description: '原片画面',
        localized_visual_description_zh: '原本的本土化画面', camera_description_zh: '原本的镜头说明', target_character_ids: [], target_scene_ids: [], target_prop_ids: [], dialogue: [], sound_effects: [], ambience: [],
      }],
    }
    vi.mocked(replicaApi.getLocalizedStoryboard).mockResolvedValue({ project_id: 'project-1', status: 'CURRENT', artifact_id: 'storyboard-1', revision: 1, content })
    vi.mocked(replicaApi.listLocalizedStoryboardCandidates).mockResolvedValue([])
    vi.mocked(projectApi.listProjectTasks).mockResolvedValue([])
    vi.mocked(replicaApi.updateLocalizedStoryboardShot).mockResolvedValue({ id: 'candidate-edit-1', project_id: 'project-1', generation_sequence: 2, review_status: 'NEEDS_REVIEW', review_reason: null, content })

    const wrapper = await mountWorkspace()
    const fields = wrapper.findAll('textarea')
    expect(fields).toHaveLength(2)
    await fields[0].setValue('修改后的本土化画面内容')
    await fields[1].setValue('修改后的镜头说明内容')
    await fields[1].trigger('blur')
    await flushPromises()

    expect(replicaApi.updateLocalizedStoryboardShot).toHaveBeenCalledWith('project-1', expect.objectContaining({
      candidate_id: null,
      expected_current_artifact_id: 'storyboard-1',
      expected_source_snapshot_artifact_id: 'snapshot-1',
      storyboard_shot_id: 'shot-1',
      localized_visual_description_zh: '修改后的本土化画面内容',
      camera_description_zh: '修改后的镜头说明内容',
    }))
    expect(wrapper.text()).toContain('已自动保存为待确认版本')
    wrapper.unmount()
  })
})
