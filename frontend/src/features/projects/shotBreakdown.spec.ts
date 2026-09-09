import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiRequest } from '@/lib/api'
import { getSourceBible } from './sourceBible'
import { startShotBreakdown } from './shotBreakdown'

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}))

vi.mock('./sourceBible', () => ({
  getSourceBible: vi.fn(),
}))

beforeEach(() => {
  vi.clearAllMocks()
})

describe('startShotBreakdown preflight', () => {
  it('does not create a P8 task when P7 SOURCE_BIBLE is NOT_BUILT', async () => {
    vi.mocked(getSourceBible).mockResolvedValue({
      project_id: 'project-p8',
      status: 'NOT_BUILT',
      artifact_id: null,
      revision: null,
      input_fingerprint: null,
      content: null,
      provenance: null,
      story_skeleton_artifact_id: null,
      rhythm_skeleton_artifact_id: null,
    })

    await expect(startShotBreakdown('project-p8', 'p8-key')).rejects.toThrow('SOURCE_BIBLE 尚未生成')
    expect(apiRequest).not.toHaveBeenCalled()
  })

  it('does not create a P8 task when P7 SOURCE_BIBLE is STALE', async () => {
    vi.mocked(getSourceBible).mockResolvedValue({
      project_id: 'project-p8',
      status: 'STALE',
      artifact_id: 'source-bible-old',
      revision: 3,
      input_fingerprint: 'stale-fingerprint',
      content: null,
      provenance: null,
      story_skeleton_artifact_id: null,
      rhythm_skeleton_artifact_id: null,
    })

    await expect(startShotBreakdown('project-p8', 'p8-key')).rejects.toThrow('当前为 STALE')
    expect(apiRequest).not.toHaveBeenCalled()
  })

  it('creates the explicit P8 command only when P7 SOURCE_BIBLE is CURRENT', async () => {
    vi.mocked(getSourceBible).mockResolvedValue({
      project_id: 'project-p8',
      status: 'CURRENT',
      artifact_id: 'source-bible-current',
      revision: 4,
      input_fingerprint: 'current-fingerprint',
      content: null,
      provenance: null,
      story_skeleton_artifact_id: 'story-current',
      rhythm_skeleton_artifact_id: 'rhythm-current',
    })
    vi.mocked(apiRequest).mockResolvedValue({
      id: 'task-p8',
      project_id: 'project-p8',
      task_name: '带 Source Bible 的逐镜精细拉片',
      progress_percent: 0,
      status: 'queued',
      last_error: null,
      attempt: 0,
      max_attempts: 3,
      can_retry: false,
      can_cancel: true,
      can_resume: false,
      created_at: '2026-09-09T00:00:00Z',
      started_at: null,
      finished_at: null,
    })

    await startShotBreakdown('project-p8', 'p8-key')

    expect(apiRequest).toHaveBeenCalledTimes(1)
    expect(apiRequest).toHaveBeenCalledWith('/projects/project-p8/commands/shot-breakdown', {
      method: 'POST',
      headers: { 'Idempotency-Key': 'p8-key' },
    })
  })
})
