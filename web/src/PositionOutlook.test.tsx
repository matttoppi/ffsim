import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PositionOutlook } from './PositionOutlook'

const outlook = {
  availability_model: 'market_mixture_mean_field_survival',
  roster_assumption: 'current_roster_marginal_value',
  edge_basis: 'first_marginal_seat',
  value_basis: 'raw_projection',
  reach_rate: 0.15,
  future_turn_pick_nos: [19, 30, 43],
  positions: [
    {
      position: 'RB',
      open_dedicated_slots: 2,
      eligible_open_flex_slots: 1,
      remaining_starting_opportunities: 3,
      best_now_player_id: 'p1',
      best_now_name: 'Bijan Robinson',
      best_now_marginal_value: 82.0,
      best_now_points: 310.2,
      best_now_adp: 3.1,
      take_now_edge: 18.4,
      turns: [
        {
          pick_no: 19,
          player_id: 'p2',
          name: 'Kenneth Walker',
          marginal_value: 63.6,
          projected_points: 240.1,
          adp: 22.0,
          survival_probability: 0.62,
          drop_from_now: 18.4,
        },
      ],
      top_players: [
        {
          player_id: 'p1',
          name: 'Bijan Robinson',
          position_rank: 1,
          marginal_value: 82.0,
          projected_points: 310.2,
          adp: 3.1,
          edge_vs_waiting: 18.4,
        },
      ],
    },
    {
      position: 'QB',
      open_dedicated_slots: 0,
      eligible_open_flex_slots: 0,
      remaining_starting_opportunities: 0,
      best_now_player_id: 'q1',
      best_now_name: 'Josh Allen',
      best_now_marginal_value: 12.0,
      best_now_points: 388.2,
      best_now_adp: 21.4,
      take_now_edge: 2.0,
      turns: [],
      top_players: [],
    },
    {
      position: 'K',
      open_dedicated_slots: 1,
      eligible_open_flex_slots: 0,
      remaining_starting_opportunities: 1,
      best_now_player_id: 'k1',
      best_now_name: 'Brandon Aubrey',
      best_now_marginal_value: 8.3,
      best_now_points: 153,
      best_now_adp: 93,
      take_now_edge: 0.0,
      turns: [],
      top_players: [],
    },
  ],
}

describe('PositionOutlook', () => {
  it('shows falloff edges, seats, turns, and targets', () => {
    render(<PositionOutlook outlook={outlook} positionFilter={null} />)

    expect(screen.getByText('Cost of waiting — by position')).toBeTruthy()
    // The card edge is unsigned; the details table keeps signed edges.
    expect(screen.getByText('18.4')).toBeTruthy()
    expect(screen.getAllByText('+18.4').length).toBeGreaterThan(0)
    // Turn row columns: value and signed vs-now cost.
    expect(screen.getAllByText('best if waiting').length).toBeGreaterThan(0)
    expect(screen.getByText('63.6')).toBeTruthy()
    expect(screen.getByText('−18.4')).toBeTruthy()
    // The edge names its horizon: the position's next-turn pick.
    expect(screen.getByText(/roster value lost if you wait until pick 19/)).toBeTruthy()
    expect(screen.getByText(/2 seats open \+1 flex \(shared\)/)).toBeTruthy()
    expect(screen.getAllByText('Bijan Robinson').length).toBeGreaterThan(0)
    expect(screen.getByText('Pick 19')).toBeTruthy()
    expect(screen.getByText('Kenneth Walker')).toBeTruthy()
    // Later-turn targets show their chance of lasting.
    expect(screen.getByText('62%')).toBeTruthy()
    expect(screen.getByText(/starters filled/)).toBeTruthy()
    expect(screen.getByText('market view · your boosts excluded')).toBeTruthy()
    expect(screen.getByText(/simulation advice stays the final ranking/)).toBeTruthy()
    // The footnote defines "roster value" once for the whole section.
    expect(screen.getByText(/Roster value = projected points/)).toBeTruthy()
    // Zero-cost positions collapse into the safe strip instead of a card.
    expect(screen.getByText('No cost to wait:')).toBeTruthy()
    expect(screen.getByText(/Brandon Aubrey · 153 pts/)).toBeTruthy()
  })

  it('respects the skill filter', () => {
    render(<PositionOutlook outlook={outlook} positionFilter="SKILL" />)
    expect(screen.getAllByText('Bijan Robinson').length).toBeGreaterThan(0)
    expect(screen.queryByText('Josh Allen')).toBeNull()
  })
})
