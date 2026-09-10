import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiRequest } from '@/lib/api'
import { getShotBreakdown } from './shotBreakdown'
import {
  adjudicateSourceResolution,
  getSourceResolution,
  listSourceResolutionRevisions,
  startSourceResolution,
} from './sourceResolution'

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}))

vi.mock('./shotBreakdown', () => ({
  getShotBreakdown: vi.fn(),
}))

beforeEach(() => {
  vi.clearAllMocks()
})

describe('P9 source resolution API contract', () => {
  it('uses read-only GET endpoints for current result and revision history', async () => {
    vi.mocked(apiRequest).mockResolvedValue({})

    await getSourceResolution('project-p9')
    await listSourceResolutionRevisions('project-p9')

    expect(apiRequest).toHaveBeenNthCalledWith(1, '/projects/project-p9/source-resolution', { cache: 'no-store' })
    expect(apiRequest).toHaveBeenNthCalledWith(2, '/projects/project-p9/source-resolution/revisions', { cache: 'no-store' })
  })

  it('does not create a P9 task when P8 SOURCE_SHOT_FACTS is not CURRENT', async () => {
    vi.mocked(getShotBreakdown).mockResolvedValue({
      project_id: 'project-p9',
      status: 'STALE',
      artifact_id: 'facts-old',
      revision: 6,
      input_fingerprint: 'stale',
      content: null,
      provenance: null,
    })

    await expect(startSourceResolution('project-p9', 'p9-key')).rejects.toThrow('P8 SOURCE_SHOT_FACTS 当前为 STALE')
    expect(apiRequest).not.toHaveBeenCalled()
  })

  it('creates the explicit P9 command only after a CURRENT P8 preflight', async () => {
    vi.mocked(getShotBreakdown).mockResolvedValue({
      project_id: 'project-p9',
      status: 'CURRENT',
      artifact_id: 'facts-current',
      revision: 7,
      input_fingerprint: 'current',
      content: null,
      provenance: null,
    })
    vi.mocked(apiRequest).mockResolvedValue({ id: 'task-p9' })

    await startSourceResolution('project-p9', 'p9-key')

    expect(apiRequest).toHaveBeenCalledTimes(1)
    expect(apiRequest).toHaveBeenCalledWith('/projects/project-p9/commands/source-resolution', {
      method: 'POST',
      headers: { 'Idempotency-Key': 'p9-key' },
    })
  })

  it('uses an explicit POST command for manual adjudication', async () => {
    vi.mocked(apiRequest).mockResolvedValue({})
    await adjudicateSourceResolution('project-p9', 'SPEAKER', {
      expected_revision: 2,
      operation: 'REASSIGN',
      entity_ids: ['speaker-1'],
      character_id: null,
      reason: '音画证据不足，解除 Speaker 到 Character 的强绑定',
    })

    expect(apiRequest).toHaveBeenCalledWith('/projects/project-p9/source-resolution/SPEAKER/commands/adjudicate', {
      method: 'POST',
      body: JSON.stringify({
        expected_revision: 2,
        operation: 'REASSIGN',
        entity_ids: ['speaker-1'],
        character_id: null,
        reason: '音画证据不足，解除 Speaker 到 Character 的强绑定',
      }),
    })
  })
})
