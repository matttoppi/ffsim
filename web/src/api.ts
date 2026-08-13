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
  ready: boolean
  refresh: RefreshState
}

export interface DraftPreparation {
  status: 'idle' | 'running' | 'ready' | 'failed'
  stage?: string | null
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
}

export interface DraftMonitor {
  status: 'idle' | 'starting' | 'running' | 'completed' | 'stopped' | 'failed'
  draft_id?: string
  poll_seconds?: number
  sync_count?: number
  calculation_count?: number
  last_sync_at?: number | null
  recommendation_status?: 'idle' | 'pending' | 'calculating' | 'expanding' | 'ready' | 'failed'
  recommendation_pick_no?: number | null
  recommendation_error?: string | null
  recommendation_discarded_pick_no?: number | null
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
    pick_no?: number | null
    candidates_evaluated?: number
    candidate_pool?: number
    paired_delta_vs_runner_up?: {
      championship_probability_delta: number
    } | null
    candidates: Array<{
      player_id: string
      name: string
      position: string | null
      championship_probability: number
      playoff_probability: number
      expected_wins: number
    }>
  } | null
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
}) =>
  request<DraftPreparation>('/api/draft-intel/prepare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })

export const getDraftPreparation = () =>
  request<DraftPreparation>('/api/draft-intel/prepare')

export const startDraftMonitor = () =>
  request<DraftMonitor>('/api/draft-intel/monitor', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  })

export const getDraftMonitor = () =>
  request<DraftMonitor>('/api/draft-intel/monitor')

export const stopDraftMonitor = () =>
  request<DraftMonitor>('/api/draft-intel/monitor/stop', { method: 'POST' })

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
