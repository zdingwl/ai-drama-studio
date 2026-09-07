export type ReviewQueueItem = { key: string; shotId: string; personKey?: string; issueId?: string }

// Follow the previous ordering after a save, even when several related items disappear.
export function nextReviewKey(before: string[], current: string, remaining: string[]): string {
  const index = before.indexOf(current)
  const candidates = index < 0 ? before : [...before.slice(index + 1), ...before.slice(0, index)]
  return candidates.find(key => remaining.includes(key)) || remaining[0] || ''
}

export function uniqueReviewItems(items: ReviewQueueItem[]): ReviewQueueItem[] {
  const seen = new Set<string>()
  return items.filter(item => !seen.has(item.key) && Boolean(seen.add(item.key)))
}
