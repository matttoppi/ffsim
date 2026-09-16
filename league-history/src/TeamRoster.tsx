import { playerInfo, type HistoryEvent, type LeagueHistory, type Team, type TeamChange } from './history.ts'

const positions = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']

export function TeamRoster({
  team,
  history,
  query,
  event,
  change,
  onPlayer,
}: {
  team: Team
  history: LeagueHistory
  query: string
  event?: HistoryEvent
  change?: TeamChange
  onPlayer: (player: string, removed: boolean) => void
}) {
  const teamMatch = `${team.name} ${team.manager}`.toLocaleLowerCase().includes(query)
  const matches = (id: string) =>
    teamMatch || playerInfo(history, id).name.toLocaleLowerCase().includes(query)
  const players = team.players
    .map((id) => playerInfo(history, id))
    .filter((player) => matches(player.id))
    .sort((a, b) => {
      const aPosition = positions.includes(a.position) ? positions.indexOf(a.position) : 99
      const bPosition = positions.includes(b.position) ? positions.indexOf(b.position) : 99
      return aPosition - bPosition || a.name.localeCompare(b.name)
    })
  const removed = (change?.removed ?? []).filter(matches)
  if (query && !teamMatch && !players.length && !removed.length) return null
  const incoming = new Set(
    change?.added ?? event?.adds.filter((add) => add.roster === team.id).map((add) => add.player),
  )

  function playerRow(id: string, departed = false) {
    const player = playerInfo(history, id)
    const status = departed ? 'outgoing' : incoming.has(id) ? 'incoming' : ''
    return (
      <li key={id} className={status}>
        <button
          type="button"
          className="player-button"
          onClick={() => onPlayer(id, departed)}
          aria-label={`View ${player.name} history`}
          aria-haspopup="dialog"
        >
          <span className={`position position-${player.position.toLowerCase()}`}>{player.position}</span>
          <span className="player-name">{player.name}</span>
          {status && <span className="arrival">{departed ? 'OUT' : 'IN'}</span>}
          <span className="player-chevron" aria-hidden="true">
            ›
          </span>
        </button>
      </li>
    )
  }

  return (
    <article className="team-card">
      <header className="team-heading">
        <span className="team-number" aria-hidden="true">
          {String(team.id).padStart(2, '0')}
        </span>
        <div>
          <h3>{team.name}</h3>
          <p>{team.manager}</p>
        </div>
        <span className="roster-count" title="Total players on this roster">
          {team.players.length}
        </span>
      </header>
      <div className="position-counts" aria-label="Roster composition">
        {positions
          .filter((position) => team.players.some((id) => playerInfo(history, id).position === position))
          .map((position) => (
            <span key={position}>
              {position}{' '}
              <b>{team.players.filter((id) => playerInfo(history, id).position === position).length}</b>
            </span>
          ))}
      </div>
      {change && (
        <p className="team-change-count">
          <span className="plus">{change.added.length} in</span>
          <span className="minus">{change.removed.length} out</span>
          <span>vs. comparison date</span>
        </p>
      )}
      <div className="roster-scroll" tabIndex={0} aria-label={`${team.name} players`}>
        {removed.length > 0 && (
          <section className="removed-players" aria-label="Players no longer on this roster">
            <h4>Out of this roster</h4>
            <ul className="player-list">{removed.map((id) => playerRow(id, true))}</ul>
          </section>
        )}
        <ul className="player-list">{players.map((player) => playerRow(player.id))}</ul>
        {!players.length && (
          <p className="empty-roster">{query ? 'No current players match.' : 'No players at this point.'}</p>
        )}
      </div>
    </article>
  )
}
