import type { JobSnapshot, JobStatus, LastResult } from './api'

export type Phase = 'idle' | 'starting' | JobStatus

export interface LiveState {
  phase: Phase
  snapshot: JobSnapshot | null
  lastResult: LastResult | null
  error: string | null
}

export const initialLiveState: LiveState = {
  phase: 'idle',
  snapshot: null,
  lastResult: null,
  error: null,
}

export type SseEvent = 'queued' | 'status' | 'progress' | 'complete' | 'failed'

/** Fold one SSE event into live state. Snapshots are authoritative and cumulative. */
export function applyEvent(
  state: LiveState,
  event: SseEvent,
  data: JobSnapshot,
): LiveState {
  switch (event) {
    case 'queued':
      return { ...state, phase: 'queued', snapshot: data }
    case 'status':
      return { ...state, phase: data.status, snapshot: data }
    case 'progress':
      return {
        phase: 'running',
        snapshot: data,
        lastResult: data.last_result ?? state.lastResult,
        error: null,
      }
    case 'complete':
      return { ...state, phase: 'completed', snapshot: data }
    case 'failed':
      return {
        ...state,
        phase: 'failed',
        snapshot: data,
        error: data.error ?? 'Simulation failed',
      }
  }
}

/** Resync from a polled status snapshot after an SSE drop. */
export function applySnapshot(state: LiveState, data: JobSnapshot): LiveState {
  return {
    ...state,
    phase: data.status,
    snapshot: data,
    error: data.status === 'failed' ? (data.error ?? 'Simulation failed') : state.error,
  }
}

/** Deterministic hue per team so a team keeps its color across boards and runs. */
export function teamHue(name: string): number {
  let hash = 0
  for (const char of name) hash = (hash * 31 + char.codePointAt(0)!) >>> 0
  return hash % 360
}

/** Short badge text: leading emoji if present, otherwise up to two initials. */
export function monogram(name: string): string {
  const trimmed = name.trim()
  if (!trimmed) return '?'
  const chars = [...trimmed]
  if (/\p{Extended_Pictographic}/u.test(chars[0])) return chars[0]
  const words = trimmed.split(/\s+/).filter(Boolean)
  if (words.length > 1) return ([...words[0]][0] + [...words[1]][0]).toUpperCase()
  return chars.slice(0, 2).join('').toUpperCase()
}

export type Metric = 'championships' | 'playoff_appearances' | 'division_wins'

export interface TeamRow {
  team: string
  count: number
  share: number
}

/** Rows for the live leaderboard: union of all team keys, sorted by the chosen metric. */
export function teamRows(snapshot: JobSnapshot | null, metric: Metric): TeamRow[] {
  if (!snapshot) return []
  const names = new Set<string>([
    ...Object.keys(snapshot.championships),
    ...Object.keys(snapshot.playoff_appearances),
    ...Object.keys(snapshot.division_wins),
  ])
  const counts = snapshot[metric]
  return [...names]
    .map((team) => ({
      team,
      count: counts[team] ?? 0,
      share: snapshot.completed > 0 ? (counts[team] ?? 0) / snapshot.completed : 0,
    }))
    .sort((a, b) => b.count - a.count || a.team.localeCompare(b.team))
}
