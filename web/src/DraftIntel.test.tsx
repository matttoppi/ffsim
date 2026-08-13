import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DraftIntel } from './DraftIntel'

function response(body: unknown) {
  return { ok: true, status: 200, json: () => Promise.resolve(body) } as Response
}

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  fetchMock.mockResolvedValue(response({ status: 'idle' }))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('DraftIntel', () => {
  it('explains the league-created mobile mock requirement and accepts its URL', async () => {
    render(<DraftIntel currentDraftId="real" />)
    expect(screen.getByText(/Sleeper mobile app/)).toBeTruthy()
    expect(screen.getByText(/generic Draftboard created on desktop/)).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Sleeper mock draft URL'), {
      target: { value: 'https://sleeper.app/draft/nfl/1393634461312106496' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    expect(screen.getByLabelText<HTMLInputElement>('Sleeper mock draft URL').value).toBe('')
    fireEvent.change(screen.getByLabelText('Sleeper mock draft URL'), {
      target: { value: 'https://sleeper.app/draft/nfl/1393634461312106496' },
    })
    fireEvent.change(screen.getByLabelText('Sleeper username'), {
      target: { value: 'mtoppi' },
    })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Prepare draft' }))
    })

    const call = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      draft_id: 'real',
      username: 'mtoppi',
      mock_draft_id: 'https://sleeper.app/draft/nfl/1393634461312106496',
    })
  })

  const pick = (pick_no: number, name: string) => ({
    pick_no,
    round: 1,
    draft_slot: pick_no,
    roster_id: pick_no,
    player_id: `p${pick_no}`,
    name,
    position: 'WR',
    team: 'BUF',
  })

  const monitorState = (picks: ReturnType<typeof pick>[], current_pick_no: number) => ({
    draft_status: 'drafting',
    completed_picks: picks.length,
    recent_picks: picks,
    current_pick_no,
    current_roster_id: 2,
    user_roster_id: 1,
    user_on_clock: false,
    user_next_pick_no: 9,
    opponent_picks_until_next: 3,
  })

  const mockMonitor = (monitor: unknown) => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        response(String(url).endsWith('/api/draft-intel/monitor') ? monitor : { status: 'idle' }),
      ),
    )
  }

  it('shows every synced pick exactly once and updates across polls without duplicates', async () => {
    vi.useFakeTimers()
    try {
      mockMonitor({
        status: 'running',
        last_sync_at: 1_755_100_000,
        state: monitorState([pick(1, 'Alpha One'), pick(2, 'Bravo Two')], 3),
      })
      await act(async () => {
        render(<DraftIntel currentDraftId="real" />)
      })
      expect(screen.getAllByText('Alpha One')).toHaveLength(1)
      expect(screen.getAllByText('Bravo Two')).toHaveLength(1)

      mockMonitor({
        status: 'running',
        last_sync_at: 1_755_100_002,
        state: monitorState(
          [pick(1, 'Alpha One'), pick(2, 'Bravo Two'), pick(3, 'Charlie Three'), pick(4, 'Delta Four')],
          5,
        ),
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000)
      })

      const rows = screen.getAllByRole('listitem').filter((row) => row.className === 'pick-feed-row')
      expect(rows).toHaveLength(4)
      expect(screen.getAllByText('Charlie Three')).toHaveLength(1)
      expect(screen.getAllByText('Delta Four')).toHaveLength(1)
      expect(rows[0].textContent).toContain('Delta Four')
      expect(rows[3].textContent).toContain('Alpha One')
      expect(screen.getByText(/4 picks in/)).toBeTruthy()
      expect(screen.getByText('Watching the room')).toBeTruthy()
    } finally {
      vi.useRealTimers()
    }
  })

  it('refuses to show a recommendation computed for a different pick and notes discards', async () => {
    mockMonitor({
      status: 'running',
      recommendation_status: 'ready',
      recommendation_pick_no: 5,
      recommendation_discarded_pick_no: 4,
      recommendation: {
        model_status: 'baseline',
        rollout_count: 50,
        joint_outcome_count: 100,
        pick_no: 5,
        candidates: [
          {
            player_id: 'p9',
            name: 'Stale Player',
            position: 'RB',
            championship_probability: 0.2,
            playoff_probability: 0.5,
            expected_wins: 8,
          },
        ],
      },
      state: { ...monitorState([pick(1, 'Alpha One')], 6), user_on_clock: true },
    })
    await act(async () => {
      render(<DraftIntel currentDraftId="real" />)
    })
    expect(screen.queryByText('Stale Player')).toBeNull()
    expect(screen.getByText(/Pick 4 result discarded/)).toBeTruthy()
  })

  it('shows a matching recommendation with its source pick', async () => {
    mockMonitor({
      status: 'running',
      recommendation_status: 'ready',
      recommendation_pick_no: 6,
      recommendation: {
        model_status: 'baseline',
        rollout_count: 50,
        joint_outcome_count: 100,
        pick_no: 6,
        candidates: [
          {
            player_id: 'p9',
            name: 'Fresh Player',
            position: 'RB',
            championship_probability: 0.2,
            playoff_probability: 0.5,
            expected_wins: 8,
          },
        ],
      },
      state: { ...monitorState([pick(1, 'Alpha One')], 6), user_on_clock: true },
    })
    await act(async () => {
      render(<DraftIntel currentDraftId="real" />)
    })
    expect(screen.getByText('Fresh Player')).toBeTruthy()
    expect(screen.getByText(/Ready for pick 6/)).toBeTruthy()
    expect(screen.getByText('You are on the clock')).toBeTruthy()
  })

  it('shows deltas versus the top option and filters candidates by position', async () => {
    mockMonitor({
      status: 'running',
      recommendation_status: 'ready',
      recommendation_pick_no: 6,
      recommendation: {
        model_status: 'baseline',
        rollout_count: 50,
        joint_outcome_count: 100,
        pick_no: 6,
        paired_delta_vs_runner_up: { championship_probability_delta: 0.05 },
        candidates: [
          {
            player_id: 'p1',
            name: 'Lead Back',
            position: 'RB',
            championship_probability: 0.2,
            playoff_probability: 0.6,
            expected_wins: 9,
          },
          {
            player_id: 'p2',
            name: 'Second Wideout',
            position: 'WR',
            championship_probability: 0.15,
            playoff_probability: 0.5,
            expected_wins: 8,
          },
        ],
      },
      state: { ...monitorState([pick(1, 'Alpha One')], 6), user_on_clock: true },
    })
    await act(async () => {
      render(<DraftIntel currentDraftId="real" />)
    })
    expect(screen.getByText('+5.0% vs next')).toBeTruthy()
    expect(screen.getByText('-5.0%')).toBeTruthy()
    expect(screen.getByText('15.0% title')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'WR' }))
    expect(screen.queryByText('Lead Back')).toBeNull()
    expect(screen.getByText('Second Wideout')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'All' }))
    expect(screen.getByText('Lead Back')).toBeTruthy()
  })

  it.each([
    [
      { status: 'running', recommendation_status: 'calculating', recommendation_pick_no: 7 },
      /Calculating recommendations for pick 7/,
    ],
    [
      { status: 'running', recommendation_status: 'pending', recommendation_pick_no: 7 },
      /Recommendation pending for pick 7/,
    ],
    [
      {
        status: 'running',
        recommendation_status: 'failed',
        recommendation_pick_no: 7,
        recommendation_error: 'boom',
      },
      /Calculation failed for pick 7/,
    ],
    [{ status: 'completed' }, /Draft complete/],
    [{ status: 'stopped' }, /Monitoring stopped/],
  ])('renders the explicit computation state %#', async (overrides, expected) => {
    mockMonitor({
      state: { ...monitorState([pick(1, 'Alpha One')], 7), user_on_clock: true },
      ...overrides,
    })
    await act(async () => {
      render(<DraftIntel currentDraftId="real" />)
    })
    expect(screen.getByText(expected)).toBeTruthy()
  })
})
