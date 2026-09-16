import { playerInfo, type HistoryEvent, type LeagueHistory, type Season } from './history.ts'

const dateFormat = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  timeZone: 'UTC',
})
export const timeFormat = new Intl.DateTimeFormat('en-US', {
  hour: 'numeric',
  minute: '2-digit',
  timeZone: 'UTC',
})
const eventLabels: Record<string, string> = {
  trade: 'Trade',
  waiver: 'Waiver',
  free_agent: 'Free agent',
  commissioner: 'Commissioner',
  draft: 'Draft',
}

export function date(at: number) {
  return dateFormat.format(at)
}
export function label(event: HistoryEvent) {
  return eventLabels[event.type] ?? 'Roster change'
}
export function teamName(season: Season, id: number) {
  return season.teams.find((team) => team.id === id)?.name ?? `Roster ${id}`
}

export function EventDetails({
  event,
  season,
  history,
}: {
  event: HistoryEvent
  season: Season
  history: LeagueHistory
}) {
  const rosterIds = [
    ...new Set([
      ...event.adds.map((move) => move.roster),
      ...event.drops.map((move) => move.roster),
      ...event.picks.flatMap((pick) => [pick.from, pick.to]),
      ...event.budget.flatMap((budget) => [budget.from, budget.to]),
    ]),
  ]
  return (
    <div className="event-detail">
      <p className="event-time">
        {timeFormat.format(event.at)} UTC{event.type === 'draft' ? ' · completed draft' : ''}
      </p>
      {rosterIds.map((id) => (
        <div key={id} className="event-team">
          <strong>{teamName(season, id)}</strong>
          {event.adds
            .filter((move) => move.roster === id)
            .map((move) => (
              <p key={`add:${move.player}`}>
                <span className="plus">+ </span>
                {playerInfo(history, move.player).name}
              </p>
            ))}
          {event.drops
            .filter((move) => move.roster === id)
            .map((move) => (
              <p key={`drop:${move.player}`}>
                <span className="minus">− </span>
                {playerInfo(history, move.player).name}
              </p>
            ))}
          {event.picks
            .filter((pick) => pick.to === id || pick.from === id)
            .map((pick) => (
              <p key={`${pick.season}:${pick.round}:${pick.original}`}>
                <span className={pick.to === id ? 'plus' : 'minus'}>{pick.to === id ? '+ ' : '− '}</span>
                {pick.season} round {pick.round} · originally {teamName(season, pick.original)}
              </p>
            ))}
          {event.budget
            .filter((budget) => budget.to === id || budget.from === id)
            .map((budget) => (
              <p key={`${budget.from}:${budget.to}:${budget.amount}`}>
                {budget.to === id ? '+' : '−'}${budget.amount} waiver budget
              </p>
            ))}
        </div>
      ))}
      {!rosterIds.length && <p>No player or draft-pick changes in this record.</p>}
    </div>
  )
}
