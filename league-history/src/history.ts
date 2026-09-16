export type Player = { id: string; name: string; position: string }
export type Team = { id: number; name: string; manager: string; players: string[] }
export type Pick = { season: string; round: number; original: number }
export type PickTransfer = Pick & { from: number; to: number }
export type Movement = { player: string; roster: number }
export type HistoryEvent = {
  id: string
  at: number
  type: string
  adds: Movement[]
  drops: Movement[]
  picks: PickTransfer[]
  budget: { from: number; to: number; amount: number }[]
}
export type Draft = {
  id: string
  start: number
  end: number
  adds: Movement[]
  active: boolean
}
export type Season = {
  id: string
  year: string
  name: string
  previous: string | null
  teams: Team[]
  events: HistoryEvent[]
  drafts: Draft[]
  fetchedAt: number
  issues: string[]
}
export type LeagueHistory = { leagueId: string; seasons: Season[]; players: Record<string, Player> }
export type RosterState = { teams: Team[]; issues: string[]; draft: Draft | null }

export function seasonStart(season: Season): number {
  const times = [...season.events.map((event) => event.at), ...season.drafts.map((draft) => draft.start)]
  return times.length ? Math.min(...times) : season.fetchedAt
}

export function seasonLastEvent(season: Season): number {
  return Math.max(
    seasonStart(season),
    ...season.events.map((event) => event.at),
    ...season.drafts.map((draft) => draft.end),
  )
}

export function timelineEvents(season: Season): HistoryEvent[] {
  return [
    ...season.events,
    ...season.drafts.map((draft) => ({
      id: `draft:${draft.id}`,
      at: draft.end,
      type: 'draft',
      adds: draft.adds,
      drops: [],
      picks: [],
      budget: [],
    })),
  ].sort((a, b) => a.at - b.at || a.id.localeCompare(b.id))
}

export function rosterAt(season: Season, at: number): RosterState {
  const teams = season.teams.map((team) => ({ ...team, players: [...team.players] }))
  const issues = at >= season.fetchedAt ? [] : [...season.issues]
  const draft = season.drafts.find((item) => at >= item.start && (item.active || at < item.end)) ?? null
  const ownership = new Map<string, number>()
  for (const team of teams) {
    for (const player of team.players) {
      if (ownership.has(player)) issues.push(`Player ${player} appears on multiple saved rosters.`)
      ownership.set(player, team.id)
    }
  }
  // Draft picks have no individual timestamps. Apply them at the start only
  // for replay outside the draft interval; never display an in-draft roster.
  const operations = [
    ...season.events,
    ...season.drafts.map((item) => ({
      id: `draft:${item.id}`,
      at: item.start,
      adds: item.adds,
      drops: [],
    })),
  ]
    .filter((event) => event.at > at)
    .sort((a, b) => b.at - a.at || b.id.localeCompare(a.id))
  const teamIds = new Set(teams.map((team) => team.id))
  let previousTime = 0
  const sameTimePlayers = new Set<string>()
  for (const event of operations) {
    if (event.at !== previousTime) sameTimePlayers.clear()
    for (const player of new Set([...event.adds, ...event.drops].map((move) => move.player))) {
      if (sameTimePlayers.has(player))
        issues.push(`Changes at ${new Date(event.at).toISOString()} have an unknown order.`)
      sameTimePlayers.add(player)
    }
    previousTime = event.at
    for (const add of event.adds) {
      if (!teamIds.has(add.roster) || ownership.get(add.player) !== add.roster) {
        issues.push(`Change ${event.id}: player ${add.player} does not match the recorded receiving roster.`)
      }
    }
    if (issues.length) break
    // Remove every incoming asset before restoring outgoing assets. This
    // keeps multi-team trades atomic, including a swap of two players.
    for (const add of event.adds) ownership.delete(add.player)
    for (const drop of event.drops) {
      if (!teamIds.has(drop.roster) || ownership.has(drop.player)) {
        issues.push(`Change ${event.id}: player ${drop.player} cannot be restored to the recorded roster.`)
      }
      ownership.set(drop.player, drop.roster)
    }
    if (issues.length) break
  }
  for (const team of teams) team.players = []
  const byId = new Map(teams.map((team) => [team.id, team]))
  for (const [player, owner] of ownership) byId.get(owner)?.players.push(player)
  return { teams, issues: [...new Set(issues)], draft }
}

export function rosterDifference(before: Team[], after: Team[]): number {
  const left = new Set(before.flatMap((team) => team.players.map((player) => `${team.id}:${player}`)))
  const right = new Set(after.flatMap((team) => team.players.map((player) => `${team.id}:${player}`)))
  return [...left].filter((key) => !right.has(key)).length + [...right].filter((key) => !left.has(key)).length
}

export function seasonAt(history: LeagueHistory, at: number): { season: Season; gap: boolean } {
  const seasons = history.seasons
  const index = seasons.findLastIndex((season) => seasonStart(season) <= at)
  const season = seasons[Math.max(0, index)]
  const next = seasons[Math.max(0, index) + 1]
  if (!next || at <= seasonLastEvent(season)) return { season, gap: false }
  const opening = rosterAt(next, seasonStart(next) - 1)
  const sameTeams =
    season.teams.length === next.teams.length &&
    season.teams.every((team) => next.teams.some((other) => team.id === other.id))
  return {
    season,
    gap: !sameTeams || opening.issues.length > 0 || rosterDifference(season.teams, opening.teams) > 0,
  }
}

export function playerInfo(history: LeagueHistory, id: string): Player {
  return history.players[id] ?? { id, name: `Player ${id}`, position: '—' }
}

export type PlayerMove = { event: HistoryEvent; season: Season; start: number }

export function playerHistory(history: LeagueHistory, player: string): PlayerMove[] {
  return history.seasons
    .flatMap((season) =>
      timelineEvents(season)
        .filter((event) => [...event.adds, ...event.drops].some((move) => move.player === player))
        .map((event) => ({
          event,
          season,
          // A draft is an interval, not a fabricated individual pick timestamp.
          start: season.drafts.find((draft) => `draft:${draft.id}` === event.id)?.start ?? event.at,
        })),
    )
    .sort((a, b) => a.start - b.start || a.event.id.localeCompare(b.event.id))
}

export function playerContext(moves: PlayerMove[], player: string, roster: number, at: number) {
  const arrival = moves.findLast(
    ({ event }) =>
      event.at <= at && event.adds.some((move) => move.player === player && move.roster === roster),
  )
  const departure = moves.find(
    ({ event, start }) =>
      start > at && event.drops.some((move) => move.player === player && move.roster === roster),
  )
  return { arrival, departure }
}

export type TeamChange = { added: string[]; removed: string[] }
export type RosterComparison = { changes: Map<number, TeamChange>; issue: string | null }

export function compareRosters(history: LeagueHistory, from: number, to: number): RosterComparison {
  const before = seasonAt(history, from)
  const after = seasonAt(history, to)
  const left = rosterAt(before.season, from)
  const right = rosterAt(after.season, to)
  if (before.gap || after.gap || left.draft || right.draft || left.issues.length || right.issues.length) {
    return { changes: new Map(), issue: 'Choose two dates with verified rosters to compare changes.' }
  }
  if (
    left.teams.length !== right.teams.length ||
    left.teams.some((team) => !right.teams.some((other) => other.id === team.id))
  ) {
    return {
      changes: new Map(),
      issue: 'The roster slots changed between these dates. Choose dates within one season.',
    }
  }
  return {
    changes: new Map(
      right.teams.map((team) => {
        const previous = left.teams.find((other) => other.id === team.id)!
        return [
          team.id,
          {
            added: team.players.filter((id) => !previous.players.includes(id)),
            removed: previous.players.filter((id) => !team.players.includes(id)),
          },
        ]
      }),
    ),
    issue: null,
  }
}

export function parseLeagueId(input: string): string {
  const value = input.trim()
  if (/^\d{15,22}$/.test(value)) return value
  let url: URL
  try {
    url = new URL(value)
  } catch {
    throw new Error('Enter a Sleeper league URL or its numeric league ID.')
  }
  if (
    !['sleeper.com', 'sleeper.app', 'www.sleeper.com', 'www.sleeper.app'].includes(url.hostname) ||
    url.protocol !== 'https:'
  ) {
    throw new Error('Use an https://sleeper.com or https://sleeper.app league link.')
  }
  const match = url.pathname.match(/^\/(?:leagues|league)\/(\d{15,22})(?:\/|$)/)
  if (!match)
    throw new Error(
      'This link does not contain a league ID. Copy the league page URL, not an invitation link.',
    )
  return match[1]
}
