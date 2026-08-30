import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ManagerScouting } from './ManagerScouting'

const report = {
  model_status: { use: 'descriptive_only', decision_eligible: false },
  target_context: { season: 2026, scoring_type: 'ppr', team_count: 12 },
  observation_count: 2197,
  managers: [
    {
      user_id: 'u1',
      roster_id: 2,
      display_name: 'Chris',
      team_name: 'Team C',
      draft_slot: 3,
      history: {
        draft_count: 7,
        pick_count: 98,
        weighted_draft_count: 4.2,
        qb_te_timing: {
          QB: {
            selected_drafts: 6,
            not_selected_drafts: 1,
            first_round_counts: { '5': 4, '7': 2 },
            sample_weight: 4.2,
            selected_weight: 3.9,
            weighted_first_rounds: { '5': 2.8, '7': 1.1 },
          },
        },
        four_round_starts: {
          sample_size: 5,
          rb_shape: { heavy_rb: 3, hero_rb: 2 },
          wr_heavy: 2,
          sample_weight: 3.4,
          weighted_rb_shape: { heavy_rb: 2.2, hero_rb: 1.2 },
          weighted_wr_heavy: 1.4,
        },
        position_picks: { RB: 30, WR: 24, QB: 8 },
      },
    },
    {
      user_id: 'u2',
      roster_id: 1,
      display_name: 'Ryan',
      team_name: null,
      draft_slot: 7,
      history: null,
    },
  ],
}

describe('ManagerScouting', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify(report), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })),
    ))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows history depth, tendencies, and population-only managers', async () => {
    await act(async () => {
      render(<ManagerScouting />)
    })

    expect(screen.getByText('Manager draft history')).toBeTruthy()
    expect(screen.getByText(/Target: 2026 · 12-team · ppr · 2,197 historical picks/)).toBeTruthy()
    expect(screen.getByText('Chris')).toBeTruthy()
    expect(screen.getByText(/7 drafts · 98 picks · weight 4.2/)).toBeTruthy()
    expect(screen.getByText(/usually R5 · drafted one in 6\/7 drafts/)).toBeTruthy()
    expect(screen.getByText(/RB-heavy starts · WR-heavy in 2\/5/)).toBeTruthy()
    expect(screen.getByText(/RB 30 · WR 24 · QB 8/)).toBeTruthy()
    expect(screen.getByText('Ryan')).toBeTruthy()
    expect(
      screen.getByText(/No eligible draft history — the population model covers this manager/),
    ).toBeTruthy()
    expect(screen.getByText(/not decision-eligible/)).toBeTruthy()
  })
})
