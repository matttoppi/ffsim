import {
  parseLeagueId,
  type Draft,
  type HistoryEvent,
  type LeagueHistory,
  type Movement,
  type Player,
  type Season,
  type Team,
} from './history.ts'

const BASE = 'https://api.sleeper.app/v1/'
const DAY = 86_400_000
type JsonObject = Record<string, unknown>

function object(value: unknown): JsonObject {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    throw new Error('Sleeper returned an invalid object.')
  return value as JsonObject // Validated object boundary; individual fields are checked below.
}

function list(value: unknown): unknown[] {
  if (!Array.isArray(value)) throw new Error('Sleeper returned an invalid list.')
  return value
}

function text(value: unknown): string {
  if (typeof value !== 'string' || !value) throw new Error('Sleeper returned a missing identifier or name.')
  return value
}

function optionalText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function integer(value: unknown): number {
  const number = typeof value === 'string' && /^\d+$/.test(value) ? Number(value) : value
  if (typeof number !== 'number' || !Number.isSafeInteger(number) || number < 0)
    throw new Error('Sleeper returned an invalid numeric field.')
  return number
}

function timestamp(value: unknown): number {
  const number = integer(value)
  if (number < 1_000_000_000_000 || number > Date.now() + DAY)
    throw new Error('Sleeper returned an invalid event date.')
  return number
}

function movements(value: unknown): Movement[] {
  if (value == null) return []
  return Object.entries(object(value)).map(([player, roster]) => ({ player, roster: integer(roster) }))
}

export function normalizeSeason(
  leagueValue: unknown,
  rosterValue: unknown,
  userValue: unknown,
  transactionValue: unknown[],
  draftValues: { draft: unknown; picks: unknown }[],
  fetchedAt: number,
): Season {
  const league = object(leagueValue)
  const id = parseLeagueId(text(league.league_id))
  if (league.sport !== 'nfl') throw new Error('This viewer supports Sleeper NFL leagues.')
  const users = new Map(
    list(userValue).map((value) => {
      const user = object(value)
      return [text(user.user_id), user]
    }),
  )
  const teams: Team[] = list(rosterValue)
    .map((value) => {
      const roster = object(value)
      const rosterId = integer(roster.roster_id)
      const user = users.get(optionalText(roster.owner_id))
      const metadata = user?.metadata == null ? {} : object(user.metadata)
      const manager = optionalText(user?.display_name) || optionalText(user?.username) || 'Unassigned manager'
      const players = list(roster.players ?? []).map(text)
      const reserve = list(roster.reserve ?? []).map(text)
      const taxi = list(roster.taxi ?? []).map(text)
      return {
        id: rosterId,
        name: optionalText(metadata.team_name) || manager,
        manager,
        players: [...new Set([...players, ...reserve, ...taxi])],
      }
    })
    .sort((a, b) => a.id - b.id)
  if (!teams.length || new Set(teams.map((team) => team.id)).size !== teams.length)
    throw new Error('Sleeper returned missing or duplicate rosters.')
  if (teams.length !== integer(league.total_rosters))
    throw new Error('The league roster response is incomplete. Try importing again.')
  const issues: string[] = []
  const events = new Map<string, HistoryEvent>()
  for (const value of transactionValue) {
    const transaction = object(value)
    if (transaction.status !== 'complete') continue
    const eventId = text(transaction.transaction_id)
    if (events.has(eventId)) continue
    if (!transaction.status_updated) {
      issues.push(`Completed transaction ${eventId} has no completion date.`)
      continue
    }
    events.set(eventId, {
      id: eventId,
      at: timestamp(transaction.status_updated),
      type: text(transaction.type),
      adds: movements(transaction.adds),
      drops: movements(transaction.drops),
      picks: list(transaction.draft_picks ?? []).map((value) => {
        const pick = object(value)
        return {
          season: text(pick.season),
          round: integer(pick.round),
          original: integer(pick.roster_id),
          from: integer(pick.previous_owner_id),
          to: integer(pick.owner_id),
        }
      }),
      budget: list(transaction.waiver_budget ?? []).map((value) => {
        const transfer = object(value)
        return {
          from: integer(transfer.sender),
          to: integer(transfer.receiver),
          amount: integer(transfer.amount),
        }
      }),
    })
  }
  const drafts: Draft[] = []
  for (const { draft: value, picks: pickValues } of draftValues) {
    const draft = object(value)
    const picks = list(pickValues).map(object)
    if (draft.status === 'pre_draft' && !picks.length) continue
    if (!draft.start_time || !draft.last_picked) {
      issues.push(`Draft ${text(draft.draft_id)} has no reliable start or completion date.`)
      continue
    }
    const start = timestamp(draft.start_time)
    const end = timestamp(draft.last_picked)
    if (end < start) throw new Error('Sleeper returned a draft that ends before it starts.')
    drafts.push({
      id: text(draft.draft_id),
      start,
      end,
      active: draft.status !== 'complete',
      adds: picks
        .filter((pick) => pick.is_keeper !== true)
        .map((pick) => ({ player: text(pick.player_id), roster: integer(pick.roster_id) })),
    })
  }
  const previous = optionalText(league.previous_league_id)
  return {
    id,
    year: text(league.season),
    name: text(league.name),
    previous: previous && previous !== '0' ? parseLeagueId(previous) : null,
    teams,
    events: [...events.values()].sort((a, b) => a.at - b.at || a.id.localeCompare(b.id)),
    drafts,
    fetchedAt,
    issues,
  }
}

async function playerCatalog(signal: AbortSignal): Promise<Record<string, Player>> {
  // The large player endpoint should be fetched at most once daily per browser.
  let cache: Cache | undefined
  try {
    cache = await caches.open('ffsim-league-history-players-v1')
  } catch {
    /* Private browsing may disable persistent storage. */
  }
  const saved = await cache?.match(`${BASE}players/nfl`)
  let payload: unknown
  if (saved && Date.now() - Number(saved.headers.get('x-saved-at')) < DAY) {
    payload = await saved.json()
  } else {
    const response = await fetch(`${BASE}players/nfl`, {
      signal: AbortSignal.any([signal, AbortSignal.timeout(30_000)]),
    })
    if (!response.ok) throw new Error(`Sleeper player catalog failed (${response.status}). Try again later.`)
    const body = await response.text()
    payload = JSON.parse(body)
    try {
      await cache?.put(
        `${BASE}players/nfl`,
        new Response(body, { headers: { 'x-saved-at': String(Date.now()) } }),
      )
    } catch {
      /* Import still works when browser storage is full. */
    }
  }
  return Object.fromEntries(
    Object.entries(object(payload)).map(([id, value]) => {
      const player = object(value)
      const name =
        optionalText(player.full_name) ||
        `${optionalText(player.first_name)} ${optionalText(player.last_name)}`.trim() ||
        `Player ${id}`
      return [id, { id, name, position: optionalText(player.position) || '—' }]
    }),
  )
}

export async function importHistory(
  input: string,
  signal: AbortSignal,
  progress: (message: string) => void,
): Promise<LeagueHistory> {
  const leagueId = parseLeagueId(input)
  const seasons: Season[] = []
  const seen = new Set<string>()
  let id: string | null = leagueId
  let nextRequestAt = 0
  async function get(path: string): Promise<unknown> {
    signal.throwIfAborted()
    const delay = Math.max(0, nextRequestAt - Date.now())
    nextRequestAt = Math.max(nextRequestAt, Date.now()) + 150
    if (delay) await new Promise((resolve) => setTimeout(resolve, delay))
    signal.throwIfAborted()
    const response = await fetch(`${BASE}${path}`, {
      signal: AbortSignal.any([signal, AbortSignal.timeout(30_000)]),
    })
    if (!response.ok)
      throw new Error(
        `Sleeper request failed (${response.status}). ${response.status === 429 ? 'Please wait a minute before trying again.' : 'Try importing again.'}`,
      )
    return response.json()
  }
  while (id) {
    if (seen.has(id)) throw new Error('Sleeper returned a loop in the league season links.')
    seen.add(id)
    const league = object(await get(`league/${id}`))
    if (league.league_id !== id)
      throw new Error('Sleeper did not return the requested league. Check the link.')
    progress(`Importing ${text(league.season)} · teams and drafts`)
    const [users, draftList] = await Promise.all([get(`league/${id}/users`), get(`league/${id}/drafts`)])
    const draftValues = []
    for (const value of list(draftList)) {
      const draft = object(value)
      if (draft.league_id !== id) throw new Error('Sleeper returned a draft from another league.')
      const draftId = text(draft.draft_id)
      const picks = await get(`draft/${draftId}/picks`)
      draftValues.push({ draft, picks })
    }
    const transactions: unknown[] = []
    // NFL league transactions are week buckets, not calendar weeks. Include
    // offseason bucket 0 and postseason buckets; do not stop at an empty week.
    for (let week = 0; week <= 22; week += 3) {
      progress(`Importing ${text(league.season)} · transaction weeks ${week}–${Math.min(22, week + 2)}`)
      const paths = Array.from(
        { length: Math.min(3, 23 - week) },
        (_, offset) => `league/${id}/transactions/${week + offset}`,
      )
      const results = await Promise.all(paths.map(get))
      for (const result of results) transactions.push(...list(result))
    }
    const rosters = await get(`league/${id}/rosters`)
    const season = normalizeSeason(league, rosters, users, transactions, draftValues, Date.now())
    seasons.push(season)
    id = season.previous
  }
  progress('Loading player names · the first visit takes a little longer')
  const players = await playerCatalog(signal)
  signal.throwIfAborted()
  return { leagueId, seasons: seasons.reverse(), players }
}
