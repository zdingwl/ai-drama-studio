import type {
  LocalizationDraftEditPayload,
  LocalizationDraftStatus,
  LocalizationDraftView,
  LocalizationRevisionSummary,
} from '../types/localization'

const jsonHeaders = { 'Content-Type': 'application/json' }

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const payload = await response.json()
      message = payload.detail || message
    } catch {
      // keep default message
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

function notifyProjectChanged(projectId: string): void {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent('studio-project-truth-changed', {
    detail: { project_id: projectId },
  }))
}

async function writeDraft(url: string, options: RequestInit): Promise<LocalizationDraftView> {
  const draft = await request<LocalizationDraftView>(url, options)
  notifyProjectChanged(draft.project_id)
  return draft
}

export const localizationApi = {
  getCurrentDraft: (episodeId: string) => request<LocalizationDraftView | null>(`/api/episodes/${episodeId}/localization-draft`),
  listRevisions: (episodeId: string) => request<LocalizationRevisionSummary[]>(`/api/episodes/${episodeId}/localization-revisions`),
  getRevision: (revisionId: string) => request<LocalizationDraftView>(`/api/localization-revisions/${revisionId}`),
  createDraft: (episodeId: string, note?: string | null) => writeDraft(`/api/episodes/${episodeId}/localization-draft`, {
    method: 'POST', headers: jsonHeaders, body: JSON.stringify({ note: note || null }),
  }),
  editDraft: (episodeId: string, baseRevisionId: string, entries: LocalizationDraftEditPayload[], note?: string | null) => writeDraft(`/api/episodes/${episodeId}/localization-draft`, {
    method: 'PATCH', headers: jsonHeaders, body: JSON.stringify({
      base_revision_id: baseRevisionId,
      entries,
      note: note || null,
    }),
  }),
  setStatus: (episodeId: string, baseRevisionId: string, status: LocalizationDraftStatus, note?: string | null) => writeDraft(`/api/episodes/${episodeId}/localization-draft/status`, {
    method: 'POST', headers: jsonHeaders, body: JSON.stringify({
      base_revision_id: baseRevisionId,
      status,
      note: note || null,
    }),
  }),
  rebaseDraft: (episodeId: string, note?: string | null) => writeDraft(`/api/episodes/${episodeId}/localization-draft/rebase`, {
    method: 'POST', headers: jsonHeaders, body: JSON.stringify({ note: note || null }),
  }),
}
