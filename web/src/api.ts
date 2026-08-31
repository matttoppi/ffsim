export const API_BASE: string =
  import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

export interface SimulationParams {
  simulations: number
  seed: number
  workers: number
  teams_only: boolean
}

export interface LastResult {
  champion: string
  playoff_teams: string[]
  division_winners: string[]
}

export type JobStatus = 'queued' | 'loading' | 'running' | 'completed' | 'failed'

export interface JobSnapshot {
  id: string
  status: JobStatus
  completed: number
  total: number
  progress: number
  seed: number
  workers: number
  teams_only: boolean
  elapsed_seconds: number
  simulations_per_second: number
  championships: Record<string, number>
  playoff_appearances: Record<string, number>
  division_wins: Record<string, number>
  error: string | null
  last_result?: LastResult
}

export interface TeamResult {
  average_wins: number
  average_points: number
  average_points_per_week: number
  playoff_probability: number
  division_win_probability: number
  championship_probability: number
  win_percentiles: Record<string, number>
  points_percentiles: Record<string, number>
  seed_probabilities: Record<string, number>
  top_two_probability: number
  bottom_two_probability: number
}

export interface PlayerResult {
  name: string
  team: string
  position: string
  average_score: number
  games_per_simulation: number
  minimum_score: number
  maximum_score: number
  average_games_missed: number
}

export interface FinalResults {
  league: { id: string; name: string }
  simulations: number
  seed: number
  teams: Record<string, TeamResult>
  players?: Record<string, PlayerResult>
  team_only?: boolean
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, init)
  } catch {
    throw new ApiError('Cannot reach the simulation server', 0)
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, response.status)
  }
  return response.json() as Promise<T>
}

export interface LeagueSummary {
  league_id: string
  name: string
  status: string
  total_rosters: number | null
  season: string | null
  season_type: string | null
  roster_positions: string[]
  settings: Record<string, unknown>
  scoring_settings: Record<string, number>
}

export interface DraftSummary {
  draft_id: string
  league_id: string
  name: string
  status: string
  draft_type: string
  season: string | null
  season_type: string | null
  teams: number | null
  rounds: number | null
  pick_timer: number | null
  scoring_type: string | null
  settings: Record<string, unknown>
  metadata: Record<string, unknown>
  redraft_eligible: boolean
  redraft_ineligibility_reasons: string[]
}

export interface RefreshState {
  status: 'idle' | 'running' | 'ready' | 'failed'
  league_id: string | null
  draft_id: string | null
  error: string | null
}

export interface LeagueInfo {
  league_id: string | null
  draft_id: string | null
  name: string | null
  draft: DraftSummary | null
  recent_trades: RecentTrade[]
  ready: boolean
  refresh: RefreshState
}

export interface RecentTrade {
  transaction_id: string
  completed_at: number | null
  sides: Array<{
    roster_id: number
    name: string
    players: Array<{
      player_id: string
      name: string
      position: string | null
      team: string | null
    }>
    draft_picks: Array<{ season: string; round: number }>
    faab: number
  }>
}

export interface WorkProgress {
  done: number
  total: number
}

export interface DraftPreparation {
  status: 'idle' | 'running' | 'ready' | 'failed'
  stage?: string | null
  stage_no?: number
  stage_count?: number
  error?: string | null
  draft_id?: string
  mock_draft_id?: string | null
  live_draft_id?: string
  league_name?: string
  teams?: number
  rounds?: number
  user_slot?: number | null
  market_players?: number
  monitor_ready?: boolean
  blockers?: string[]
  history?: {
    managers: number
    managers_with_eligible_history: number
    draft_discoveries: number
    unique_drafts: number
    duplicate_discoveries_removed: number
    model_eligible_picks: number
  }
  mock_compatibility?: {
    status: 'not_used' | 'exact' | 'mismatch'
    reasons: Array<{
      code: string
      label: string
      expected: unknown
      actual: unknown
    }>
  }
  world_bank?: { version: string | null; worlds: number; players: number }
  personal_ranks?: { players: number; hash: string | null }
}

export interface DraftRecommendationCandidate {
  player_id: string
  name: string
  position: string | null
  projected_roster_value: number
  projected_roster_value_standard_error: number
  personal_offset: number
  preference_adjusted_value: number | null
  preference_adjusted_value_standard_error: number | null
  championship_probability: number
  playoff_probability: number
  expected_wins: number
  adp: number | null
  survives_to_next_pick: number | null
  best_wait_candidate_id: string | null
  survival_branch_root_candidate_id: string | null
  opportunity_evidence_branch_root_candidate_id: string | null
  target_available_count: number | null
  target_selected_when_available_count: number | null
  target_rollout_count: number | null
  rollout_count?: number
  current_marginal_value?: number | null
  expected_best_later_value?: number | null
  expected_same_position_later_value?: number | null
  value_over_next_alternative?: number | null
  effective_tie_break_urgency: number
  positional_value_drop?: number | null
  next_turn_pick_no?: number | null
  later_alternatives?: Array<{
    player_id: string
    name: string
    position: string | null
    probability: number
  }>
  later_alternative_other_probability?: number
  opportunity_sample_count?: number
  opportunity_model_version?: string | null
}

export interface DraftLeagueSimulation {
  model_status: string
  simulation_type?: 'completed_draft'
  pick_no: number | null
  completed_picks: number
  rollout_count: number
  season_worlds_per_rollout?: number
  joint_outcome_count: number
  rosters: Array<{
    roster_id: number
    name: string
    draft_slot: number | null
    is_user: boolean
    championship_probability: number
    championship_standard_error: number
    championship_interval: [number, number]
    playoff_probability: number
    expected_wins: number
    expected_points: number
  }>
}

export type DraftRecommendationMode = 'simulation' | 'projection'


export interface DraftProjectionBoard {
  model_status: 'deterministic_projection_lookahead'
  model_version: number
  route_model_status: 'approximate_adp_opponent_choice_lookahead'
  worp_calibration: {
    status: string
    team_count: number
    scoring_format: string | null
    model_version?: string
    training_games?: number
    validation_games?: number
    decision_reference?: string
  }
  pick_no: number
  next_user_pick_no: number | null
  recommended_player_id: string | null
  recommended_position: string | null
  plans: Array<{
    position: string
    player_id: string
    name: string
    projected_points: number
    value_over_replacement: number
    wins_over_replacement: number | null
    current_roster_value: number
    later_value: number
    route_value: number
    adp: number | null
  }>
  points_source: 'fantasypros_primary_offense'
  special_teams_points_source: 'pff'
  points_players: Array<{
    player_id: string
    name: string
    position: string
    team: string | null
    position_rank: number
    projected_points: number
    personal_offset: number
    projection_source?: string | null
    projection_source_outlier?: boolean
  }>
  players: Array<{
    player_id: string
    name: string
    position: string
    team: string | null
    position_rank: number
    projected_points: number
    replacement_points: number
    value_over_replacement: number
    wins_over_replacement: number | null
    current_roster_value: number
    adp: number | null
    personal_offset: number
    projection_source?: string | null
    projection_source_outlier?: boolean
  }>
  position_outlook?: {
    availability_model: string
    survival_model?: string
    roster_assumption: string
    edge_basis: string
    value_basis: string
    reach_rate: number
    future_turn_pick_nos: number[]
    positions: PositionFalloff[]
  }
}

export interface PositionFalloff {
  position: string
  open_dedicated_slots: number
  eligible_open_flex_slots: number
  remaining_starting_opportunities: number
  best_now_player_id: string
  best_now_name: string
  best_now_marginal_value: number
  best_now_points: number
  best_now_personal_offset?: number
  best_now_adp: number | null
  take_now_edge: number
  turns: Array<{
    pick_no: number
    player_id: string | null
    name: string | null
    marginal_value: number
    projected_points: number | null
    personal_offset?: number
    adp: number | null
    survival_probability?: number
    probability_best?: number
    drop_from_now: number
  }>
  top_players: Array<{
    player_id: string
    name: string
    position_rank: number
    marginal_value: number
    projected_points: number
    personal_offset?: number
    adp: number | null
    edge_vs_waiting: number
  }>
}

export interface DraftAlphaShadowCandidate {
  player_id: string
  name: string
  position: string | null
  team: string | null
  engine_rank: number
  market_rank: number | null
  return_probability: number | null
  return_interval_95: [number, number] | null
  direct_support: number
  pooled_support: number | null
  support_status: string
  timing_label: 'safe_to_wait' | 'urgent' | 'uncertain' | 'outside_model'
  current_roster_value: number
  wait_delta: number | null
}

export interface DraftAlphaShadow {
  status: 'ready'
  decision_active: false
  draft_id: string
  pick_no: number
  terminal_recommendation_id: string | null
  terminal_q_leader_id: string | null
  terminal_co_leader_candidate_ids: string[]
  survival_model_version: string
  survival_manifest_hash: string
  manager_model_version: string | null
  manager_manifest_hash: string | null
  manager_probability_blend: number | null
  top_ten_capture_complete: boolean
  candidates: DraftAlphaShadowCandidate[]
  recommended_branch_next_turn: Array<{
    player_id: string
    market_rank: number
    position: string | null
    eligible_next_turn: boolean
    return_probability: number | null
    return_interval_95: [number, number] | null
    direct_support: number
    pooled_support: number | null
    timing_label: 'safe_to_wait' | 'urgent' | 'uncertain' | 'outside_model'
  }>
  manager_support: {
    supported_rosters: number
    population_fallback_rosters: number
    total_opponent_rosters: number
  }
  manager_shadow: {
    status: 'ready' | 'unavailable'
    reason?: string
    rollouts?: number
    probability_blend?: number
    terminal_leader_candidate_id?: string | null
    shadow_leader_candidate_id?: string
    shadow_leader_in_terminal_practical_tier?: boolean
    ranking?: string[]
    callback_calls?: Record<string, number>
  }
  duration_seconds: number
  limitations: string[]
}



export interface DraftAlphaShadowAudit {
  audit_version: string
  status: 'research'
  metrics: {
    sessions: number
    ready_states: number
    failed_events: number
    discarded_events: number
    failure_rate: number | null
    duration_seconds: {
      median: number | null
      p95: number | null
      maximum: number | null
    }
    top_ten_capture_rate: number | null
    manager_practical_retention_rate: number | null
    manager_exact_agreement_rate: number | null
    manager_callback_calls: Record<string, number>
  }
  development_gate: Record<string, boolean>
  live_evidence_gate: Record<string, boolean>
}


export interface DraftMonitor {
  status: 'idle' | 'starting' | 'running' | 'completed' | 'stopped' | 'failed'
  draft_id?: string
  poll_seconds?: number
  recommendation_mode?: DraftRecommendationMode
  sync_count?: number
  calculation_count?: number
  last_sync_at?: number | null
  recommendation_status?: 'idle' | 'pending' | 'calculating' | 'expanding' | 'refining' | 'ready' | 'failed'
  recommendation_pick_no?: number | null
  recommendation_error?: string | null
  recommendation_discarded_pick_no?: number | null
  recommendation_progress?: WorkProgress | null
  league_equity_status?: 'idle' | 'pending' | 'calculating' | 'ready' | 'failed'
  league_equity_progress?: WorkProgress | null
  league_equity_pick_no?: number | null
  league_equity_error?: string | null
  league_equity_calculation_count?: number
  alpha_shadow_status?: 'disabled' | 'idle' | 'pending' | 'ready' | 'stale' | 'failed'
  alpha_shadow_pick_no?: number | null
  alpha_shadow?: DraftAlphaShadow | null
  alpha_shadow_error?: string | null
  alpha_shadow_duration_seconds?: number | null
  alpha_shadow_calculation_count?: number
  projection_board?: DraftProjectionBoard | null
  projection_board_error?: string | null
  error?: string | null
  state?: {
    draft_status: string
    completed_picks: number
    recent_picks?: Array<{
      pick_no: number
      round: number
      draft_slot: number
      roster_id: number | null
      player_id: string
      name: string
      position: string | null
      team: string | null
    }>
    current_pick_no: number | null
    current_roster_id: number | null
    user_roster_id: number | null
    user_on_clock: boolean
    user_next_pick_no: number | null
    opponent_picks_until_next: number | null
  } | null
  recommendation?: {
    model_status: string
    rollout_count: number
    joint_outcome_count: number
    seed: number
    decision_engine_version: number
    draft_model_version: string
    world_bank_version: string
    league_evaluator_version: string
    state_signature: string
    run_signature: string
    decision_status: 'clear_leader' | 'toss_up'
    practical_tie_points: number
    headline_tie_break_basis: 'urgency' | 'market_adp' | 'engine_rank' | null
    bench_asset_factor: number
    q_leader_candidate_id: string
    reason_codes: string[]
    co_leader_candidate_ids: string[]
    order_symmetric_candidate_ids?: string[]
    paired_value_delta_basis?: string
    pair_plan?: {
      next_pick_no: number
      sample_count: number
      companions: Array<{
        player_id: string
        name: string
        position: string | null
        share: number
      }>
    } | null
    recommended_candidate_id?: string
    runner_up_candidate_id?: string | null
    projected_roster_value?: number
    projected_roster_value_interval?: [number, number]
    paired_value_delta_vs_runner_up?: {
      candidate_id: string
      baseline_candidate_id: string
      projected_value_delta: number
      standard_error: number
      interval: [number, number]
      better_continuation_probability: number
      tied_continuation_probability: number
      worse_continuation_probability: number
    } | null
    next_user_pick_no?: number | null
    pick_no?: number | null
    candidates_evaluated?: number
    candidate_pool?: number
    screened_rollout_count?: number
    paired_delta_vs_runner_up?: {
      championship_probability_delta: number
      interval: [number, number]
    } | null
    position_timing?: Array<{
      position: string
      best_now_player_id: string
      best_now_name?: string
      best_now_points: number
      best_now_adp: number
      advantage_now_vs_next_turn: number
      target_pick_no: number
      recommendation: 'TAKE_NOW' | 'TARGET_BY_PICK' | 'WAIT_THROUGH_PICK'
      turns: Array<{
        pick_no: number
        player_id: string | null
        name: string | null
        projected_points: number
        adp: number | null
        drop_from_now: number
      }>
    }> | null
    candidates: DraftRecommendationCandidate[]
    screened_candidates?: DraftRecommendationCandidate[]
  } | null
  league_equity?: DraftLeagueSimulation | null
}

export const getHealth = () => request<{ status: string }>('/api/health')

export const getLeagueInfo = () => request<LeagueInfo>('/api/league')

export const findLeagues = (username: string, season = 2026) =>
  request<LeagueSummary[]>(
    `/api/leagues?username=${encodeURIComponent(username)}&season=${season}`,
  )

export const findDrafts = (league_id: string) =>
  request<{ league: LeagueSummary; drafts: DraftSummary[] }>(
    `/api/leagues/${encodeURIComponent(league_id)}/drafts`,
  )

export const selectLeague = (league_id: string, draft_id: string) =>
  request<{ status: string; league_id: string; draft_id: string }>('/api/league', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ league_id, draft_id }),
  })

export const prepareDraft = (params: {
  draft_id: string
  username: string
  mock_draft_id?: string
  force_refresh?: boolean
}) =>
  request<DraftPreparation>('/api/draft-intel/prepare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })

export const getDraftPreparation = () =>
  request<DraftPreparation>('/api/draft-intel/prepare')

export const startDraftMonitor = (recommendationMode: DraftRecommendationMode = 'simulation') =>
  request<DraftMonitor>('/api/draft-intel/monitor', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ recommendation_mode: recommendationMode }),
  })

export const getDraftMonitor = () =>
  request<DraftMonitor>('/api/draft-intel/monitor')

export const getDraftAlphaShadow = () =>
  request<{
    status: DraftMonitor['alpha_shadow_status']
    pick_no: number | null
    evidence: DraftAlphaShadow | null
    error: string | null
    duration_seconds: number | null
    calculation_count?: number
  }>('/api/draft-intel/alpha-shadow')

export const getDraftAlphaShadowAudit = () =>
  request<DraftAlphaShadowAudit>('/api/draft-intel/alpha-shadow/audit')

export interface ManagerHistoryProfile {
  draft_count: number
  pick_count: number
  weighted_draft_count: number
  qb_te_timing: Record<string, {
    selected_drafts: number
    not_selected_drafts: number
    first_round_counts: Record<string, number>
    sample_weight: number
    selected_weight: number
    weighted_first_rounds: Record<string, number>
  }>
  four_round_starts: {
    sample_size: number
    rb_shape: Record<string, number>
    wr_heavy: number
    sample_weight: number
    weighted_rb_shape: Record<string, number>
    weighted_wr_heavy: number
  }
  position_picks: Record<string, number>
}

export interface ManagerScoutingReport {
  model_status: { use: string; decision_eligible: boolean }
  target_context: { season: number; scoring_type: string | null; team_count: number }
  observation_count: number
  managers: Array<{
    user_id: string | null
    roster_id: number | null
    display_name: string
    team_name: string | null
    draft_slot: number | null
    history: ManagerHistoryProfile | null
  }>
}

export const getManagerScouting = () =>
  request<ManagerScoutingReport>('/api/draft-intel/managers')

export const stopDraftMonitor = () =>
  request<DraftMonitor>('/api/draft-intel/monitor/stop', { method: 'POST' })

export const simulateCompletedDraft = () =>
  request<DraftLeagueSimulation>('/api/draft-intel/simulation', { method: 'POST' })

export const startSimulation = (params: SimulationParams) =>
  request<JobSnapshot>('/api/simulations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })

export const getSimulation = (id: string) =>
  request<JobSnapshot>(`/api/simulations/${id}`)

export const getResults = (id: string) =>
  request<FinalResults>(`/api/simulations/${id}/results`)

export const eventsUrl = (id: string) =>
  `${API_BASE}/api/simulations/${id}/events`

export interface PersonalRankPlayer {
  player_id: string
  name: string
  position: string
  team: string | null
  adp: number | null
  offset: number
}

export interface PersonalRanksBoard {
  allowed_offsets: number[]
  count: number
  players: PersonalRankPlayer[]
}

export const fetchPersonalRanks = () =>
  request<PersonalRanksBoard>('/api/personal-ranks')

export const savePersonalRank = (playerId: string, offset: number) =>
  request<{
    player_id: string
    offset: number
    count: number
    applied: 'live' | 'next_prepare'
  }>('/api/personal-ranks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ player_id: playerId, offset }),
  })
