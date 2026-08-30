import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PersonalRanks } from './PersonalRanks'

const BOARD = {
  allowed_offsets: [-50, -40, -30, -25, -20, -15, -10, -5, 0, 5, 10, 15, 20, 25, 30, 40, 50],
  count: 1,
  players: [
    { player_id: 'sleeper:1', name: 'Josh Allen', position: 'QB', team: 'BUF', adp: 22.4, offset: 0 },
    { player_id: 'sleeper:2', name: "Ja'Marr Chase", position: 'WR', team: 'CIN', adp: 1.2, offset: 0 },
    { player_id: 'sleeper:3', name: 'Bijan Robinson', position: 'RB', team: 'ATL', adp: 3.1, offset: -10 },
    { player_id: 'sleeper:4', name: 'Mystery Rookie', position: 'WR', team: null, adp: null, offset: 0 },
  ],
}

function jsonResponse(body: unknown, status = 200) {
  return { ok: status < 400, status, json: () => Promise.resolve(body) } as Response
}

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body))
      return Promise.resolve(jsonResponse({ ...body, count: 2, applied: 'live' }))
    }
    return Promise.resolve(jsonResponse(BOARD))
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

async function renderBoard() {
  await act(async () => {
    render(<PersonalRanks />)
  })
}

describe('PersonalRanks', () => {
  it('renders rows sorted by market ADP with null ADP last', async () => {
    await renderBoard()
    const names = screen
      .getAllByRole('listitem')
      .map((row) => row.querySelector('strong')?.textContent)
    // Offsets are point opinions, not board moves: market ADP orders the
    // list (Chase 1.2, Bijan 3.1, Allen 22.4); null ADP sinks.
    expect(names).toEqual(["Ja'Marr Chase", 'Bijan Robinson', 'Josh Allen', 'Mystery Rookie'])
    expect(screen.getByText('1 rated · 0 boosts · 1 fade')).toBeTruthy()
    expect(screen.getByLabelText('Offset for Bijan Robinson').textContent).toBe('-10')
  })

  it('saves a stepped offset and updates the badge optimistically', async () => {
    await renderBoard()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Boost Josh Allen' }))
    })
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(String(call?.[0])).toContain('/api/personal-ranks')
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ player_id: 'sleeper:1', offset: 5 })
    expect(screen.getByLabelText('Offset for Josh Allen').textContent).toBe('+5')
    expect(screen.getByText('2 rated · 1 boost · 1 fade')).toBeTruthy()
    // A live save shows no pending notice.
    expect(screen.queryByText(/applies after next draft prep/)).toBeNull()
  })

  it('shows a pending notice when a save applies after the next draft prep', async () => {
    await renderBoard()
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        const body = JSON.parse(String(init.body))
        return Promise.resolve(jsonResponse({ ...body, count: 2, applied: 'next_prepare' }))
      }
      return Promise.resolve(jsonResponse(BOARD))
    })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Boost Josh Allen' }))
    })
    expect(screen.getByText('Saved — applies after next draft prep')).toBeTruthy()
  })

  it('reaches any allowed offset in two clicks via the expanded picker', async () => {
    await renderBoard()
    fireEvent.click(screen.getByRole('button', { name: 'All offsets for Josh Allen' }))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '-25' }))
    })
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ player_id: 'sleeper:1', offset: -25 })
    expect(screen.getByLabelText('Offset for Josh Allen').textContent).toBe('-25')
  })

  it('reverts the badge and shows an inline error when the save fails', async () => {
    await renderBoard()
    fetchMock.mockImplementation((_url: string, init?: RequestInit) =>
      Promise.resolve(
        init?.method === 'POST'
          ? jsonResponse({ detail: 'No market board cached' }, 409)
          : jsonResponse(BOARD),
      ),
    )
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Boost Josh Allen' }))
    })
    expect(screen.getByLabelText('Offset for Josh Allen').textContent).toBe('—')
    expect(screen.getByRole('alert').textContent).toBe('No market board cached')
  })

  it('surfaces the 409 detail with league guidance when loading fails', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'No league selected' }, 409))
    await renderBoard()
    expect(screen.getByRole('alert').textContent).toBe('No league selected')
    expect(screen.getByText(/Pick a league/)).toBeTruthy()
  })
})
