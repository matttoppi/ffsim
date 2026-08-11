import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { JobSnapshot } from './api'
import { useSimulation } from './useSimulation'

class MockEventSource {
  static instances: MockEventSource[] = []
  listeners = new Map<string, ((event: MessageEvent) => void)[]>()
  closed = false
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor(readonly url: string) {
    MockEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener])
  }

  close() {
    this.closed = true
  }

  emit(type: string, data: unknown) {
    const event = { data: JSON.stringify(data) } as MessageEvent
    for (const listener of this.listeners.get(type) ?? []) listener(event)
  }
}

function jobSnapshot(overrides: Partial<JobSnapshot> = {}): JobSnapshot {
  return {
    id: 'job1',
    status: 'queued',
    completed: 0,
    total: 50,
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

const params = { simulations: 50, seed: 2026, workers: 4, teams_only: false }

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  } as Response
}

const fetchMock = vi.fn()

beforeEach(() => {
  MockEventSource.instances = []
  fetchMock.mockReset()
  vi.stubGlobal('EventSource', MockEventSource)
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useSimulation', () => {
  it('starts a job, streams progress, and finalizes on complete', async () => {
    const finalResults = {
      league: { id: '1', name: 'Test League' },
      simulations: 50,
      seed: 2026,
      teams: {},
    }
    fetchMock
      .mockResolvedValueOnce(jsonResponse(jobSnapshot()))
      .mockResolvedValueOnce(jsonResponse(finalResults))

    const { result } = renderHook(() => useSimulation())
    await act(() => result.current.start(params))

    expect(result.current.busy).toBe(true)
    const source = MockEventSource.instances[0]
    expect(source.url).toContain('/api/simulations/job1/events')

    act(() => {
      source.emit('status', jobSnapshot({ status: 'running' }))
      source.emit(
        'progress',
        jobSnapshot({
          status: 'running',
          completed: 10,
          championships: { 'Team A': 6, 'Team B': 4 },
          last_result: {
            champion: 'Team B',
            playoff_teams: ['Team A', 'Team B'],
            division_winners: ['Team B'],
          },
        }),
      )
    })
    expect(result.current.live.snapshot?.completed).toBe(10)
    expect(result.current.live.lastResult?.champion).toBe('Team B')

    act(() => {
      source.emit('complete', jobSnapshot({ status: 'completed', completed: 50, progress: 1 }))
    })
    expect(source.closed).toBe(true)
    await waitFor(() => expect(result.current.results).toEqual(finalResults))
    expect(result.current.live.phase).toBe('completed')
    expect(result.current.busy).toBe(false)
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/simulations/job1/results'),
      undefined,
    )
  })

  it('reports a clear message on 409', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: 'A simulation is already running' }, 409),
    )
    const { result } = renderHook(() => useSimulation())
    await act(() => result.current.start(params))

    expect(result.current.startError).toMatch(/already running/)
    expect(result.current.busy).toBe(false)
    expect(MockEventSource.instances).toHaveLength(0)
  })

  it('reports a connection error when the server is unreachable', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('fetch failed'))
    const { result } = renderHook(() => useSimulation())
    await act(() => result.current.start(params))

    expect(result.current.startError).toBe('Cannot reach the simulation server')
    expect(result.current.busy).toBe(false)
  })

  it('surfaces the failure message and closes the stream on failed', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(jobSnapshot()))
    const { result } = renderHook(() => useSimulation())
    await act(() => result.current.start(params))

    const source = MockEventSource.instances[0]
    act(() => {
      source.emit('failed', jobSnapshot({ status: 'failed', error: 'snapshot missing' }))
    })
    expect(result.current.live.phase).toBe('failed')
    expect(result.current.live.error).toBe('snapshot missing')
    expect(source.closed).toBe(true)
    expect(result.current.busy).toBe(false)
  })

  it('resyncs from status when the stream drops mid-run', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(jobSnapshot()))
      .mockResolvedValueOnce(jsonResponse(jobSnapshot({ status: 'running', completed: 30 })))

    const { result } = renderHook(() => useSimulation())
    await act(() => result.current.start(params))

    const source = MockEventSource.instances[0]
    await act(async () => {
      await source.onerror?.()
    })
    expect(result.current.live.snapshot?.completed).toBe(30)
    expect(source.closed).toBe(false) // still running: let EventSource retry
  })

  it('finalizes when a dropped stream reveals the job already completed', async () => {
    const finalResults = {
      league: { id: '1', name: 'Test League' },
      simulations: 50,
      seed: 2026,
      teams: {},
    }
    fetchMock
      .mockResolvedValueOnce(jsonResponse(jobSnapshot()))
      .mockResolvedValueOnce(
        jsonResponse(jobSnapshot({ status: 'completed', completed: 50, progress: 1 })),
      )
      .mockResolvedValueOnce(jsonResponse(finalResults))

    const { result } = renderHook(() => useSimulation())
    await act(() => result.current.start(params))

    const source = MockEventSource.instances[0]
    await act(async () => {
      await source.onerror?.()
    })
    expect(source.closed).toBe(true)
    await waitFor(() => expect(result.current.results).toEqual(finalResults))
    expect(result.current.live.phase).toBe('completed')
  })

  it('closes the stream on unmount', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(jobSnapshot()))
    const { result, unmount } = renderHook(() => useSimulation())
    await act(() => result.current.start(params))

    const source = MockEventSource.instances[0]
    expect(source.closed).toBe(false)
    unmount()
    expect(source.closed).toBe(true)
  })

  it('closes the previous stream and clears results when starting a new run', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(jobSnapshot()))
      .mockResolvedValueOnce(jsonResponse(jobSnapshot({ id: 'job2' })))

    const { result } = renderHook(() => useSimulation())
    await act(() => result.current.start(params))
    const first = MockEventSource.instances[0]

    await act(() => result.current.start(params))
    expect(first.closed).toBe(true)
    expect(MockEventSource.instances).toHaveLength(2)
    expect(MockEventSource.instances[1].url).toContain('job2')
    expect(result.current.results).toBeNull()

    // events from the stale stream are ignored
    act(() => {
      first.emit('progress', jobSnapshot({ id: 'job1', completed: 99 }))
    })
    expect(result.current.live.snapshot?.completed).toBe(0)
  })
})
