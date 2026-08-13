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
