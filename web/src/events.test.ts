import { describe, expect, it } from 'vitest'
import type { JobSnapshot } from './api'
import { applyEvent, applySnapshot, initialLiveState, teamRows } from './events'

function snapshot(overrides: Partial<JobSnapshot> = {}): JobSnapshot {
  return {
    id: 'job1',
    status: 'running',
    completed: 0,
    total: 100,
    progress: 0,
    seed: 2026,
    workers: 4,
    teams_only: false,
    elapsed_seconds: 0,
    simulations_per_second: 0,
    championships: {},
    playoff_appearances: {},
    division_wins: {},
    error: null,
    ...overrides,
  }
}

describe('applyEvent', () => {
  it('follows the queued → status → progress lifecycle', () => {
    let state = applyEvent(initialLiveState, 'queued', snapshot({ status: 'queued' }))
    expect(state.phase).toBe('queued')

    state = applyEvent(state, 'status', snapshot({ status: 'loading' }))
    expect(state.phase).toBe('loading')

    state = applyEvent(
      state,
      'progress',
      snapshot({
        completed: 5,
        championships: { 'Team A': 3, 'Team B': 2 },
        last_result: {
          champion: 'Team A',
          playoff_teams: ['Team A', 'Team B'],
          division_winners: ['Team A'],
        },
      }),
    )
    expect(state.phase).toBe('running')
    expect(state.snapshot?.completed).toBe(5)
    expect(state.lastResult?.champion).toBe('Team A')
  })

  it('keeps the previous last_result when a progress event omits it', () => {
    let state = applyEvent(
      initialLiveState,
      'progress',
      snapshot({
        completed: 1,
        last_result: { champion: 'Team A', playoff_teams: [], division_winners: [] },
      }),
    )
    state = applyEvent(state, 'progress', snapshot({ completed: 2 }))
    expect(state.lastResult?.champion).toBe('Team A')
  })

  it('captures the error message on failure', () => {
    const state = applyEvent(
      initialLiveState,
      'failed',
      snapshot({ status: 'failed', error: 'league snapshot missing' }),
    )
    expect(state.phase).toBe('failed')
    expect(state.error).toBe('league snapshot missing')
  })

  it('marks completion', () => {
    const state = applyEvent(
      initialLiveState,
      'complete',
      snapshot({ status: 'completed', completed: 100, progress: 1 }),
    )
    expect(state.phase).toBe('completed')
    expect(state.snapshot?.completed).toBe(100)
  })
})

describe('applySnapshot', () => {
  it('resyncs phase and counters from a polled snapshot', () => {
    const state = applySnapshot(
      initialLiveState,
      snapshot({ status: 'running', completed: 42 }),
    )
    expect(state.phase).toBe('running')
    expect(state.snapshot?.completed).toBe(42)
  })

  it('surfaces the error when the polled job has failed', () => {
    const state = applySnapshot(
      initialLiveState,
      snapshot({ status: 'failed', error: 'boom' }),
    )
    expect(state.phase).toBe('failed')
    expect(state.error).toBe('boom')
  })
})

describe('teamRows', () => {
  it('returns an empty list without a snapshot', () => {
    expect(teamRows(null, 'championships')).toEqual([])
  })

  it('keeps zero-count teams and preserves names exactly', () => {
    const rows = teamRows(
      snapshot({
        completed: 10,
        championships: { '  Spaced Team  ': 0, '🏈 Emoji Squad': 7, 'Team C': 3 },
      }),
      'championships',
    )
    expect(rows.map((r) => r.team)).toEqual(['🏈 Emoji Squad', 'Team C', '  Spaced Team  '])
    expect(rows[2]).toEqual({ team: '  Spaced Team  ', count: 0, share: 0 })
    expect(rows[0].share).toBeCloseTo(0.7)
  })

  it('includes teams that only appear in another metric, with zero counts', () => {
    const rows = teamRows(
      snapshot({
        completed: 4,
        championships: { 'Team A': 4 },
        playoff_appearances: { 'Team A': 4, 'Team B': 2 },
      }),
      'championships',
    )
    expect(rows).toEqual([
      { team: 'Team A', count: 4, share: 1 },
      { team: 'Team B', count: 0, share: 0 },
    ])
  })

  it('sorts by the selected metric', () => {
    const base = snapshot({
      completed: 10,
      championships: { 'Team A': 8, 'Team B': 2 },
      division_wins: { 'Team A': 1, 'Team B': 9 },
    })
    expect(teamRows(base, 'division_wins')[0].team).toBe('Team B')
    expect(teamRows(base, 'championships')[0].team).toBe('Team A')
  })

  it('reports zero shares before any simulation completes', () => {
    const rows = teamRows(
      snapshot({ completed: 0, championships: { 'Team A': 0 } }),
      'championships',
    )
    expect(rows[0].share).toBe(0)
  })
})
