import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const getLeagueInfo = vi.hoisted(() => vi.fn())

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return {
    ...actual,
    getLeagueInfo,
    getDraftPreparation: vi.fn(() => new Promise(() => {})),
    getDraftMonitor: vi.fn(() => new Promise(() => {})),
  }
})

import App from './App'

describe('App', () => {
  beforeEach(() => {
    getLeagueInfo.mockReset()
    getLeagueInfo.mockImplementation(() => new Promise(() => {}))
  })

  it('keeps draft intelligence separate from the season simulator', () => {
    render(<App />)

    expect(screen.getByRole('tabpanel', { name: 'Draft intelligence' })).toBeTruthy()
    expect(document.getElementById('season-simulator-panel')?.hidden).toBe(true)

    fireEvent.click(screen.getByRole('tab', { name: 'Season simulator' }))

    expect(document.getElementById('draft-intelligence-panel')?.hidden).toBe(true)
    expect(screen.getByRole('form', { name: 'Simulation settings' })).toBeTruthy()
  })

  it('shows recent completed trades in the season simulator', async () => {
    getLeagueInfo.mockResolvedValue({
      league_id: 'league',
      draft_id: 'draft',
      name: 'Home League',
      draft: null,
      ready: true,
      refresh: { status: 'ready', league_id: 'league', draft_id: 'draft', error: null },
      recent_trades: [{
        transaction_id: 'trade-1',
        completed_at: 1_786_921_200_000,
        sides: [
          {
            roster_id: 1,
            name: 'Alpha',
            players: [{ player_id: 'p1', name: 'One Player', position: 'WR', team: 'BUF' }],
            draft_picks: [],
            faab: 7,
          },
          {
            roster_id: 2,
            name: 'Beta',
            players: [],
            draft_picks: [{ season: '2027', round: 2 }],
            faab: 0,
          },
        ],
      }],
    })
    render(<App />)

    fireEvent.click(screen.getByRole('tab', { name: 'Season simulator' }))

    expect(await screen.findByRole('region', { name: 'Recent trades' })).toBeTruthy()
    expect(screen.getByText(/One Player · WR BUF, \$7 FAAB/)).toBeTruthy()
    expect(screen.getByText('2027 round 2')).toBeTruthy()
  })
})
