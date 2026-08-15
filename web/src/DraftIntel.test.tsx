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

  it('shows league championship rankings while an opponent is on the clock', async () => {
    mockMonitor({
      status: 'running',
      league_equity_status: 'calculating',
      league_equity_pick_no: 5,
      league_equity_progress: { done: 12, total: 50 },
      league_equity: {
        model_status: 'baseline',
        pick_no: 5,
        completed_picks: 4,
        rollout_count: 12,
        joint_outcome_count: 36,
        rosters: [
          {
            roster_id: 1,
            name: 'Alpha',
            draft_slot: 1,
            is_user: true,
            championship_probability: 0.125,
            championship_standard_error: 0.02,
            championship_interval: [0.1, 0.15],
            playoff_probability: 0.6,
            expected_wins: 8,
            expected_points: 100,
          },
          {
            roster_id: 2,
            name: 'Bravo',
            draft_slot: 2,
            is_user: false,
            championship_probability: 0.1,
            championship_standard_error: 0.02,
            championship_interval: [0.08, 0.12],
            playoff_probability: 0.5,
            expected_wins: 7,
            expected_points: 90,
          },
        ],
      },
      state: monitorState(
        [pick(1, 'One'), pick(2, 'Two'), pick(3, 'Three'), pick(4, 'Four')],
        5,
      ),
    })
    await act(async () => {
      render(<DraftIntel currentDraftId="real" />)
    })

    expect(screen.getByText('Championship odds')).toBeTruthy()
    expect(screen.getByText('Alpha (You)')).toBeTruthy()
    expect(screen.getByText('Bravo')).toBeTruthy()
    expect(screen.getByText('12.5%')).toBeTruthy()
    expect(screen.getByText(/Refining for pick 5/)).toBeTruthy()
    expect(screen.getByText('24%')).toBeTruthy()
    expect(screen.getByText('Watching the room')).toBeTruthy()
  })

  it('runs the exact final-roster simulation after the draft completes', async () => {
    const monitor = {
      status: 'completed',
      state: { ...monitorState([pick(1, 'One')], 2), current_pick_no: null },
    }
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      Promise.resolve(response(
        String(url).endsWith('/api/draft-intel/simulation') && init?.method === 'POST'
          ? {
              model_status: 'observed_final_rosters',
              simulation_type: 'completed_draft',
              pick_no: null,
              completed_picks: 1,
              rollout_count: 1,
              joint_outcome_count: 300,
              rosters: [{
                roster_id: 1,
                name: 'Alpha',
                draft_slot: 1,
                is_user: true,
                championship_probability: 0.25,
                championship_standard_error: 0.01,
                championship_interval: [0.23, 0.27],
                playoff_probability: 0.7,
                expected_wins: 8.5,
                expected_points: 1400,
              }],
            }
          : String(url).endsWith('/api/draft-intel/monitor')
            ? monitor
            : { status: 'idle' },
      )),
    )
    await act(async () => {
      render(<DraftIntel currentDraftId="real" />)
    })

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Run full league simulation' }))
    })

    expect(screen.getByText('Full simulation results')).toBeTruthy()
    expect(screen.getByText('Alpha (You)')).toBeTruthy()
    expect(screen.getByText(/Exact final rosters · 300 season worlds/)).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/draft-intel/simulation'),
      { method: 'POST' },
    )
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
        next_user_pick_no: 9,
        bench_asset_factor: 0.25,
        candidates: [
          {
            player_id: 'p9',
            name: 'Fresh Player',
            position: 'RB',
            projected_roster_value: 812.4,
            championship_probability: 0.2,
            playoff_probability: 0.5,
            expected_wins: 8,
            adp: 42.4,
            survives_to_next_pick: 0.82,
            best_wait_candidate_id: 'p10',
            survival_branch_root_candidate_id: 'p10',
            opportunity_evidence_branch_root_candidate_id: 'p9',
            target_available_count: 41,
            target_selected_when_available_count: 20,
            target_rollout_count: 50,
            current_marginal_value: 84,
            expected_best_later_value: 78,
            effective_tie_break_urgency: 6,
            positional_value_drop: 6,
            next_turn_pick_no: 9,
            opportunity_sample_count: 50,
            opportunity_model_version: 'next-turn-vona-v1:conditional-hazard',
            later_alternatives: [{
              player_id: 'p10',
              name: 'Patient Quarterback',
              position: 'QB',
              probability: 0.64,
            }],
          },
        ],
        position_timing: [
          {
            position: 'QB',
            best_now_player_id: 'p9',
            best_now_name: 'Fresh Player',
            best_now_points: 350.2,
            best_now_adp: 7.1,
            advantage_now_vs_next_turn: 31.3,
            target_pick_no: 9,
            recommendation: 'TARGET_BY_PICK',
            turns: [
              {
                pick_no: 9,
                player_id: 'p10',
                name: 'Patient Quarterback',
                projected_points: 318.9,
                adp: 10.2,
                drop_from_now: 31.3,
              },
              {
                pick_no: 16,
                player_id: 'p11',
                name: 'Later Quarterback',
                projected_points: 280,
                adp: 20,
                drop_from_now: 70.2,
              },
            ],
          },
          {
            position: 'TE',
            best_now_player_id: 'p10',
            best_now_name: 'Elite Tight End',
            best_now_points: 240,
            best_now_adp: 12,
            advantage_now_vs_next_turn: 60,
            target_pick_no: 6,
            recommendation: 'TAKE_NOW',
            turns: [
              {
                pick_no: 9,
                player_id: 'p12',
                name: 'Later Tight End',
                projected_points: 180,
                adp: 18,
                drop_from_now: 60,
              },
            ],
          },
        ],
      },
      state: { ...monitorState([pick(1, 'Alpha One')], 6), user_on_clock: true },
    })
    await act(async () => {
      render(<DraftIntel currentDraftId="real" />)
    })
    expect(screen.getByText('Fresh Player')).toBeTruthy()
    expect(screen.getByText('✓ Final suggestion')).toBeTruthy()
    expect(screen.queryByText('First look')).toBeNull()
    expect(screen.getByText('ADP 42')).toBeTruthy()
    expect(screen.getByText(/Fresh Player-root local opportunity evidence.*84 current marginal.*78 expected best at pick 9.*\+6 RB drop.*Patient Quarterback.*64%/)).toBeTruthy()
    expect(screen.getByText('Why Fresh Player')).toBeTruthy()
    expect(screen.getByText(/RB cliff/)).toBeTruthy()
    expect(screen.getByText(/same-position value falls 6 points by pick 9/)).toBeTruthy()
    expect(screen.getByText(/36 picks before Fresh Player's ADP of 42/)).toBeTruthy()
    expect(screen.getByText(/Ready for pick 6/)).toBeTruthy()
    expect(screen.getByText('You are on the clock')).toBeTruthy()
    expect(screen.getByText('QB & TE ADP-only timing · next three turns')).toBeTruthy()
    expect(screen.getByText(/not a survival probability/)).toBeTruthy()
    expect(screen.getByText('Target by pick 9')).toBeTruthy()
    expect(screen.getByText('Take now')).toBeTruthy()
    expect(screen.getByText(/Patient Quarterback · 319 pts/)).toBeTruthy()
    expect(screen.getByText('−31 vs now')).toBeTruthy()
  })

  it('labels an in-progress board as a first look with pipeline steps', async () => {
    mockMonitor({
      status: 'running',
      recommendation_status: 'refining',
      recommendation_pick_no: 6,
      recommendation_progress: { done: 2500, total: 5000 },
      recommendation: {
        model_status: 'baseline',
        rollout_count: 50,
        joint_outcome_count: 100,
        pick_no: 6,
        bench_asset_factor: 0.25,
        candidates: [
          {
            player_id: 'p1',
            name: 'Early Leader',
            position: 'RB',
            projected_roster_value: 810,
            championship_probability: 0.2,
            playoff_probability: 0.6,
            expected_wins: 9,
          },
        ],
      },
      state: { ...monitorState([pick(1, 'Alpha One')], 6), user_on_clock: true },
    })
    await act(async () => {
      render(<DraftIntel currentDraftId="real" />)
    })
    expect(screen.getByText('First look')).toBeTruthy()
    expect(screen.queryByText('✓ Final suggestion')).toBeNull()
    expect(screen.getByText('Refining finalists')).toBeTruthy()
    expect(screen.getByText(/Refining the top candidates for pick 6/)).toBeTruthy()
    expect(screen.getByText('50%')).toBeTruthy()
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
        decision_status: 'clear_leader',
        bench_asset_factor: 0.25,
        paired_value_delta_vs_runner_up: {
          candidate_id: 'p1',
          baseline_candidate_id: 'p2',
          projected_value_delta: 5.2,
          standard_error: 0.5,
          interval: [4.2, 6.2],
          better_continuation_probability: 0.8,
          tied_continuation_probability: 0.1,
          worse_continuation_probability: 0.1,
        },
        screened_rollout_count: 12,
        candidates: [
          {
            player_id: 'p1',
            name: 'Lead Back',
            position: 'RB',
            projected_roster_value: 815.4,
            championship_probability: 0.2,
            playoff_probability: 0.6,
            expected_wins: 9,
          },
          {
            player_id: 'p2',
            name: 'Second Wideout',
            position: 'WR',
            projected_roster_value: 810.2,
            championship_probability: 0.15,
            playoff_probability: 0.5,
            expected_wins: 8,
          },
        ],
        screened_candidates: [
          {
            player_id: 'p3',
            name: 'Screened Quarterback',
            position: 'QB',
            projected_roster_value: 802.7,
            championship_probability: 0.14,
            playoff_probability: 0.48,
            expected_wins: 7.8,
            rollout_count: 25,
          },
        ],
      },
      state: { ...monitorState([pick(1, 'Alpha One')], 6), user_on_clock: true },
    })
    await act(async () => {
      render(<DraftIntel currentDraftId="real" />)
    })
    expect(screen.getByText('+5.2 pts vs next')).toBeTruthy()
    expect(screen.getByText('-5.2 pts')).toBeTruthy()
    expect(screen.getByText('810.2 proj pts')).toBeTruthy()
    expect(screen.getByText('3 options shown.')).toBeTruthy()
    expect(screen.getByText('Refined contenders')).toBeTruthy()
    expect(screen.getByText('Screened watchlist')).toBeTruthy()
    expect(screen.getByText('Screened Quarterback')).toBeTruthy()
    expect(screen.getByText('802.7 proj pts · 25 continuations')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'QB' }))
    expect(screen.queryByText('Lead Back')).toBeNull()
    expect(screen.getByText('Screened Quarterback')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'WR' }))
    expect(screen.queryByText('Lead Back')).toBeNull()
    expect(screen.getByText('Second Wideout')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'All' }))
    expect(screen.getByText('Lead Back')).toBeTruthy()
  })

  it('separates paired value, alternative-root availability, selection, and local opportunity evidence', async () => {
    mockMonitor({
      status: 'running',
      recommendation_status: 'ready',
      recommendation_pick_no: 6,
      recommendation: {
        model_status: 'baseline',
        rollout_count: 300,
        joint_outcome_count: 600,
        pick_no: 6,
        next_user_pick_no: 9,
        decision_status: 'clear_leader',
        practical_tie_points: 0.1,
        headline_tie_break_basis: null,
        bench_asset_factor: 0.25,
        q_leader_candidate_id: 'p1',
        reason_codes: ['PAIRED_VALUE_EDGE'],
        recommended_candidate_id: 'p1',
        runner_up_candidate_id: 'p2',
        co_leader_candidate_ids: ['p1'],
        paired_value_delta_vs_runner_up: {
          candidate_id: 'p1',
          baseline_candidate_id: 'p2',
          projected_value_delta: 2.4,
          standard_error: 0.7,
          interval: [1.1, 3.7],
          better_continuation_probability: 0.4,
          tied_continuation_probability: 0.05,
          worse_continuation_probability: 0.55,
        },
        candidates: [
          {
            player_id: 'p1',
            name: 'Oronde Gadsden',
            position: 'TE',
            projected_roster_value: 815.4,
            championship_probability: 0.2,
            playoff_probability: 0.6,
            expected_wins: 9,
            survives_to_next_pick: 1,
            best_wait_candidate_id: 'p2',
            survival_branch_root_candidate_id: 'p2',
            opportunity_evidence_branch_root_candidate_id: 'p1',
            target_available_count: 300,
            target_selected_when_available_count: 0,
            target_rollout_count: 300,
            current_marginal_value: 80,
            expected_best_later_value: 77,
            effective_tie_break_urgency: 3,
            next_turn_pick_no: 9,
            later_alternatives: [{
              player_id: 'p3',
              name: 'Late Tight End',
              position: 'TE',
              probability: 0.65,
            }],
          },
          {
            player_id: 'p2',
            name: 'Patient Wideout',
            position: 'WR',
            projected_roster_value: 813.0,
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
    const why = screen.getByLabelText('Why this pick').textContent ?? ''
    expect(screen.getByText('Why Oronde Gadsden')).toBeTruthy()
    expect(why).toMatch(/taking Oronde Gadsden instead of Patient Wideout/)
    expect(why).toMatch(/risk-neutral expected projected completed-roster value by \+2\.4 points/)
    expect(why).toMatch(/higher in 40%, tied in 5%, and lower in 55%/)
    expect(why).toMatch(/branch rooted at taking Patient Wideout.*available at pick 9 in 300\/300/)
    expect(why).toMatch(/selects Oronde Gadsden in 0\/300 continuations where it is available/)
    expect(why).toMatch(/Oronde Gadsden-root local opportunity evidence/)
    expect(why).toMatch(/most common local later alternative is Late Tight End \(65%\)/)
    expect(why).toMatch(/best-legal-lineup points over replacement.*bench value discounted by a 0\.25 factor/)
    expect(document.body.textContent).not.toMatch(
      /Best final roster|starting-lineup value|Statistical tie|if you pass|passing still drafts|runner-up with your next pick/i,
    )
  })

  it('reports a market-ordered practical toss-up without exposing raw DEF VONA as urgency', async () => {
    mockMonitor({
      status: 'running',
      recommendation_status: 'ready',
      recommendation_pick_no: 24,
      recommendation: {
        model_status: 'baseline',
        rollout_count: 50,
        joint_outcome_count: 50,
        seed: 2026,
        decision_engine_version: 2,
        draft_model_version: 'sleeper-adp:t0.11:vor2',
        world_bank_version: 'abcdef1234567890',
        league_evaluator_version: 'league-v1',
        state_signature: 'state-signature',
        run_signature: '1234567890abcdef',
        decision_status: 'toss_up',
        practical_tie_points: 0.1,
        headline_tie_break_basis: 'market_adp',
        bench_asset_factor: 0.25,
        q_leader_candidate_id: 'p2',
        reason_codes: ['MARKET_ADP_TIEBREAK'],
        co_leader_candidate_ids: ['p1', 'p2'],
        pick_no: 24,
        paired_value_delta_vs_runner_up: {
          candidate_id: 'p1',
          baseline_candidate_id: 'p2',
          projected_value_delta: 0,
          standard_error: 2.1,
          interval: [-4.1, 4.1],
          better_continuation_probability: 0.45,
          tied_continuation_probability: 0.1,
          worse_continuation_probability: 0.45,
        },
        candidates: [
          {
            player_id: 'p1',
            name: 'Lead Defense',
            position: 'DEF',
            projected_roster_value: 820.3,
            championship_probability: 0.3,
            playoff_probability: 0.92,
            expected_wins: 9.7,
            adp: 24,
            value_over_next_alternative: 99,
            effective_tie_break_urgency: 0,
          },
          {
            player_id: 'p2',
            name: 'Even Wideout',
            position: 'WR',
            projected_roster_value: 820.3,
            championship_probability: 0.3,
            playoff_probability: 0.9,
            expected_wins: 9.8,
            adp: 25,
            value_over_next_alternative: 99,
            effective_tie_break_urgency: 0,
          },
        ],
      },
      state: {
        ...monitorState([pick(1, 'Alpha One')], 24),
        user_on_clock: true,
        user_next_pick_no: 25,
      },
    })
    await act(async () => {
      render(<DraftIntel currentDraftId="real" />)
    })
    const page = document.body.textContent ?? ''
    expect(page).toMatch(/Practical toss-up under the 0\.1-point gate/)
    expect(page).toMatch(/Lead Defense, Even Wideout form the top tier/)
    expect(page).toMatch(/Lead Defense leads on market ADP, a draft-position proxy, not trade value/)
    expect(screen.getAllByText('T1')).toHaveLength(2)
    expect(screen.getAllByText(/urgency \+0\.0/)).toHaveLength(2)
    expect(screen.queryByText('+0.0 pts vs next')).toBeNull()
    expect(page).not.toMatch(/VONA|99\.0|statistical equality/i)
    expect(screen.getByText(/run 1234567890ab/)).toBeTruthy()
    expect(screen.getByText(/model sleeper-adp:t0.11:vor2/)).toBeTruthy()
    expect(page).not.toMatch(/runner-up with your next pick/)
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
        recommendation_status: 'expanding',
        recommendation_pick_no: 7,
        recommendation: {
          model_status: 'baseline',
          rollout_count: 50,
          joint_outcome_count: 100,
          pick_no: 7,
          candidates_evaluated: 13,
          candidate_pool: 40,
          candidates: [],
        },
      },
      /Screening the board for pick 7 — 13 of 40 candidates evaluated/,
    ],
    [
      { status: 'running', recommendation_status: 'refining', recommendation_pick_no: 7 },
      /Refining the top candidates for pick 7/,
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
