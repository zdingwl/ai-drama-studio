const normalize = (value: string | null | undefined) => String(value ?? '').trim().toUpperCase()

export function runStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    READY: '可用草稿',
    READY_WITH_WARNINGS: '可用 · 有提示',
    PROCESSING: '处理中',
    FAILED: '失败',
    STALE: '历史 · 已过期',
    CANCELLED: '已取消',
  }
  return labels[normalize(status)] || status || '未知状态'
}

export function componentStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    READY: '可用',
    READY_WITH_WARNINGS: '可用 · 有提示',
    PROCESSING: '处理中',
    FAILED: '失败',
    NOT_AVAILABLE: '不可用',
    NO_EVIDENCE: '无证据',
    CANCELLED: '已取消',
  }
  return labels[normalize(status)] || status || '—'
}

export function sceneSpaceLabel(value: string | null | undefined): string {
  const labels: Record<string, string> = {
    INTERIOR: '内景',
    EXTERIOR: '外景',
    INT: '内景',
    EXT: '外景',
    UNKNOWN: '未知',
  }
  return labels[normalize(value)] || value || ''
}

export function timeOfDayLabel(value: string | null | undefined): string {
  const labels: Record<string, string> = {
    DAY: '白天',
    NIGHT: '夜晚',
    MORNING: '早晨',
    AFTERNOON: '下午',
    EVENING: '傍晚',
    DAWN: '清晨',
    DUSK: '黄昏',
    UNKNOWN: '未知',
  }
  return labels[normalize(value)] || value || ''
}

export function visibilityLabel(value: string | null | undefined): string {
  const labels: Record<string, string> = {
    FULL: '完整可见',
    PARTIAL: '部分可见',
    OCCLUDED: '被遮挡',
    BACK: '背面',
    OFFSCREEN: '画外',
    UNKNOWN: '未知',
  }
  return labels[normalize(value)] || value || '未知'
}

export function speakingStateLabel(value: string | null | undefined): string {
  const labels: Record<string, string> = {
    SPEAKING: '正在说话',
    LIKELY_SPEAKING: '可能正在说话',
    NOT_SPEAKING: '未说话',
    SILENT: '未说话',
    UNKNOWN: '未知',
  }
  return labels[normalize(value)] || value || '未知'
}

export function propImportanceLabel(value: string | null | undefined): string {
  const labels: Record<string, string> = {
    KEY: '关键',
    SUPPORTING: '辅助',
    AMBIENT: '环境',
    BACKGROUND: '背景',
    UNKNOWN: '未知',
  }
  return labels[normalize(value)] || value || '未标注'
}

export function participantRoleLabel(value: string | null | undefined): string {
  const labels: Record<string, string> = {
    SPEAKER: '说话人',
    ACTOR: '动作主体',
    SUBJECT: '主体',
    TARGET: '目标',
    OBSERVER: '观察者',
    UNKNOWN: '未知角色',
  }
  return labels[normalize(value)] || value || '未标注角色'
}

export function eventOriginLabel(value: string | null | undefined): string {
  const origin = normalize(value)
  if (origin.includes('ASR')) return 'ASR 语音识别'
  if (origin.includes('OCR')) return 'OCR 文字识别'
  if (origin.includes('VLM')) return 'VLM 画面理解'
  if (origin.includes('FUSION')) return '融合结果'
  return value || '未知来源'
}

export function evidenceRoleLabel(value: string | null | undefined): string {
  const labels: Record<string, string> = {
    PRIMARY: '主要证据',
    SUPPORT: '辅助证据',
    SUPPORTING: '辅助证据',
    DERIVED: '派生证据',
    CONTEXT: '上下文证据',
  }
  return labels[normalize(value)] || value || '证据'
}

export function evidenceSourceTypeLabel(value: string | null | undefined): string {
  const type = normalize(value)
  const labels: Record<string, string> = {
    OCR_OBSERVATION: 'OCR 文字识别',
    VLM_OUTPUT: 'VLM 画面理解',
    ASR_WORD: 'ASR 词级识别',
    ASR_SEGMENT: 'ASR 分段识别',
    AUDIO_OBSERVATION: '音频识别',
    SHOT_REFERENCE: '镜头参考片段',
  }
  return labels[type] || value || '未知证据来源'
}

export function eventTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    DIALOGUE: '对白',
    ACTION: '动作',
    OCR: '画面文字',
    VISUAL: '画面',
    AUDIO_EVENT: '声音',
  }
  return labels[normalize(type)] || type
}
