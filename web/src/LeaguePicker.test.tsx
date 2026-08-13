import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeaguePicker } from './LeaguePicker'

const LEAGUES = [
  {
    league_id: 'l1',
    name: 'Dynasty - Triton',
    status: 'in_season',
    total_rosters: 10,
    season: '2026',
  },
  { league_id: 'l2', name: '🏈 Emoji League', status: 'drafting', total_rosters: 12, season: '2026' },
]

const DRAFTS = {
  league: LEAGUES[1],
  drafts: [
    {
      draft_id: 'd1',
      league_id: 'l2',
      name: 'Custom Draft',
      status: 'pre_draft',
      draft_type: 'auction',
      season: '2026',
      season_type: 'regular',
      teams: 12,
      rounds: 18,
      pick_timer: 60,
      scoring_type: 'custom_redraft',
      settings: { nomination_timer: 30 },
      metadata: { custom: 'preserved' },
      redraft_eligible: true,
      redraft_ineligibility_reasons: [],
    },
    {
      draft_id: 'd2',
      league_id: 'l2',
      name: 'Other Draft',
      status: 'complete',
      draft_type: 'linear',
      season: '2026',
      season_type: 'regular',
      teams: 12,
      rounds: 4,
      pick_timer: 120,
      scoring_type: 'dynasty_2qb',
      settings: {},
      metadata: {},
      redraft_eligible: false,
      redraft_ineligibility_reasons: ['dynasty'],
    },
  ],
}

function jsonResponse(body: unknown, status = 200) {
  return { ok: status < 400, status, json: () => Promise.resolve(body) } as Response
}

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

async function submitSearch(name: string) {
  const input = screen.getByLabelText('Sleeper username') as HTMLInputElement
  const form = input.closest('form')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!.call(
      input,
      name,
    )
    input.dispatchEvent(new Event('input', { bubbles: true }))
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  })
}

describe('LeaguePicker', () => {
  it('lists leagues for a username, preserving names exactly', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(LEAGUES))
    render(
      <LeaguePicker currentId="l1" currentDraftId={null} onReady={() => {}} onCancel={null} />,
    )

    await submitSearch('matt')

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/leagues?username=matt&season=2026'),
      undefined,
    )
    expect(screen.getByText('Dynasty - Triton')).toBeTruthy()
    expect(screen.getByText('🏈 Emoji League')).toBeTruthy()
    expect(screen.getByText(/in season · 10 teams · current/)).toBeTruthy()
  })

  it('shows the server message when the user is not found', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: 'Sleeper user not found: nobody' }, 404),
    )
    render(
      <LeaguePicker currentId={null} currentDraftId={null} onReady={() => {}} onCancel={null} />,
    )

    await submitSearch('nobody')

    expect(screen.getByRole('alert').textContent).toBe('Sleeper user not found: nobody')
  })

  it('validates an empty username without calling the server', async () => {
    render(
      <LeaguePicker currentId={null} currentDraftId={null} onReady={() => {}} onCancel={null} />,
    )

    await submitSearch('   ')

    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByRole('alert').textContent).toMatch(/Enter a Sleeper username/)
  })

  it('selects a league, polls the refresh, and reports ready', async () => {
    vi.useFakeTimers()
    const onReady = vi.fn()
    let polls = 0
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).includes('/api/leagues?')) return Promise.resolve(jsonResponse(LEAGUES))
      if (String(url).includes('/drafts')) return Promise.resolve(jsonResponse(DRAFTS))
      if (init?.method === 'POST')
        return Promise.resolve(
          jsonResponse({ status: 'running', league_id: 'l2', draft_id: 'd1' }, 202),
        )
      polls += 1
      return Promise.resolve(
        jsonResponse({
          league_id: 'l2',
          draft_id: 'd1',
          name: polls >= 2 ? '🏈 Emoji League' : null,
          ready: polls >= 2,
          refresh: {
            status: polls >= 2 ? 'ready' : 'running',
            league_id: 'l2',
            draft_id: 'd1',
            error: null,
          },
        }),
      )
    })

    render(
      <LeaguePicker currentId={null} currentDraftId={null} onReady={onReady} onCancel={null} />,
    )
    await submitSearch('matt')

    await act(async () => {
      screen.getByText('🏈 Emoji League').closest('button')!.click()
    })
    await act(async () => {})
    expect(screen.getByText(/auction · pre draft/)).toBeTruthy()
    expect(screen.getByText(/linear · complete/)).toBeTruthy()
    expect(screen.getByText(/dynasty$/)).toBeTruthy()
    await act(async () => {
      screen.getByText(/auction · pre draft/).closest('button')!.click()
    })
    expect(screen.getByText('Syncing league data')).toBeTruthy()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600)
    })
    expect(onReady).not.toHaveBeenCalled()

    for (let i = 0; i < 3 && onReady.mock.calls.length === 0; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1600)
      })
    }
    expect(onReady).toHaveBeenCalledTimes(1)
  })

  it('surfaces a failed refresh and returns to the list', async () => {
    vi.useFakeTimers()
    fetchMock
      .mockResolvedValueOnce(jsonResponse(LEAGUES))
      .mockResolvedValueOnce(jsonResponse(DRAFTS))
      .mockResolvedValueOnce(
        jsonResponse({ status: 'running', league_id: 'l2', draft_id: 'd1' }, 202),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          league_id: 'l2',
          draft_id: 'd1',
          name: null,
          ready: false,
          refresh: {
            status: 'failed',
            league_id: 'l2',
            draft_id: 'd1',
            error: 'Sleeper timed out',
          },
        }),
      )

    render(
      <LeaguePicker currentId={null} currentDraftId={null} onReady={() => {}} onCancel={null} />,
    )
    await submitSearch('matt')
    await act(async () => {
      screen.getByText('🏈 Emoji League').closest('button')!.click()
    })
    await act(async () => {})
    await act(async () => {
      screen.getByText(/auction · pre draft/).closest('button')!.click()
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600)
    })

    expect(screen.getByRole('alert').textContent).toBe('Sleeper timed out')
    expect(screen.getByText(/auction · pre draft/)).toBeTruthy()
  })

  it('rejects with the 409 detail when a simulation is running', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(LEAGUES))
      .mockResolvedValueOnce(jsonResponse(DRAFTS))
      .mockResolvedValueOnce(
        jsonResponse({ detail: 'A simulation is running; wait for it to finish' }, 409),
      )

    render(
      <LeaguePicker currentId={null} currentDraftId={null} onReady={() => {}} onCancel={null} />,
    )
    await submitSearch('matt')
    await act(async () => {
      screen.getByText('🏈 Emoji League').closest('button')!.click()
    })
    await act(async () => {})
    await act(async () => {
      screen.getByText(/auction · pre draft/).closest('button')!.click()
    })

    expect(screen.getByRole('alert').textContent).toMatch(/simulation is running/)
  })
})
