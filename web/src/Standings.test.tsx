import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Standings } from './Standings'
import type { FinalResults, TeamResult } from './api'

const team = (overrides: Partial<TeamResult> = {}): TeamResult => ({
  average_wins: 9,
  average_points: 1800,
  average_points_per_week: 128.6,
  playoff_probability: 0.7,
  division_win_probability: 0,
  championship_probability: 0.2,
  win_percentiles: { '10': 6, '25': 8, '50': 9, '75': 10, '90': 12 },
  points_percentiles: { '10': 1500, '25': 1650, '50': 1800, '75': 1950, '90': 2100 },
  seed_probabilities: { '1': 0.3, '2': 0.2, '3': 0.5 },
  top_two_probability: 0.5,
  bottom_two_probability: 0.1,
  ...overrides,
})

const results: FinalResults = {
  league: { id: 'league', name: 'Test League' },
  simulations: 100,
  seed: 7,
  teams: {
    Alpha: team({ championship_probability: 0.6 }),
    Beta: team({ average_points_per_week: 140, championship_probability: 0.1 }),
  },
  players: {
    player: {
      name: 'Player One',
      team: 'Alpha',
      position: 'WR',
      average_score: 14.2,
      games_per_simulation: 13.5,
      minimum_score: 0,
      maximum_score: 35,
      average_games_missed: 0.5,
    },
  },
}

describe('Standings', () => {
  it('shows run insights and opens team-specific simulation details', () => {
    render(<Standings results={results} />)

    expect(screen.getByText('Title favorite')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Alpha' }))

    const details = screen.getByRole('region', { name: 'Alpha simulation details' })
    expect(within(details).getByText('Player One')).toBeTruthy()
    expect(within(details).getByText('60.0%')).toBeTruthy()
    expect(screen.queryByRole('columnheader', { name: 'Division' })).toBeNull()
  })
})
