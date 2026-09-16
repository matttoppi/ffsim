import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { importHistory } from './sleeper.ts'
import {
  parseLeagueId,
  playerInfo,
  rosterAt,
  seasonAt,
  seasonStart,
  timelineEvents,
  type HistoryEvent,
  type LeagueHistory,
  type Season,
  type Team,
} from './history.ts'

const DAY = 86_400_000
const dateFormat = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  timeZone: 'UTC',
})
const timeFormat = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'UTC' })
const eventLabels: Record<string, string> = {
  trade: 'Trade',
  waiver: 'Waiver',
  free_agent: 'Free agent',
  commissioner: 'Commissioner',
  draft: 'Draft',
}
const positions = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']

function date(at: number) {
  return dateFormat.format(at)
}
function label(event: HistoryEvent) {
  return eventLabels[event.type] ?? 'Roster change'
}
function teamName(season: Season, id: number) {
  return season.teams.find((team) => team.id === id)?.name ?? `Roster ${id}`
}

function TeamRoster({
  team,
  history,
  query,
  event,
}: {
  team: Team
  history: LeagueHistory
  query: string
  event?: HistoryEvent
}) {
  const teamMatch = `${team.name} ${team.manager}`.toLocaleLowerCase().includes(query)
  const players = team.players
    .map((id) => playerInfo(history, id))
    .filter((player) => teamMatch || player.name.toLocaleLowerCase().includes(query))
    .sort((a, b) => {
      const aPosition = positions.includes(a.position) ? positions.indexOf(a.position) : 99
      const bPosition = positions.includes(b.position) ? positions.indexOf(b.position) : 99
      return aPosition - bPosition || a.name.localeCompare(b.name)
    })
  if (query && !teamMatch && !players.length) return null
  const incoming = new Set(event?.adds.filter((add) => add.roster === team.id).map((add) => add.player))
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
      <div className="roster-scroll" tabIndex={0} aria-label={`${team.name} players`}>
        <ul className="player-list">
          {players.map((player) => (
            <li key={player.id} className={incoming.has(player.id) ? 'incoming' : ''}>
              <span className={`position position-${player.position.toLowerCase()}`}>{player.position}</span>
              <span>{player.name}</span>
              {incoming.has(player.id) && <span className="arrival">IN</span>}
            </li>
          ))}
        </ul>
        {!players.length && <p className="empty-roster">No players at this point.</p>}
      </div>
    </article>
  )
}

function EventDetails({
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

function HistoryViewer({
  history,
  initialAt,
  onChangeLeague,
}: {
  history: LeagueHistory
  initialAt: number
  onChangeLeague: () => void
}) {
  const first = seasonStart(history.seasons[0])
  const last = history.seasons[history.seasons.length - 1].fetchedAt
  const [at, setAt] = useState(() => Math.min(last, Math.max(first, initialAt || last)))
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [shareStatus, setShareStatus] = useState('')
  const { season, gap } = seasonAt(history, at)
  const state = useMemo(() => rosterAt(season, at), [season, at])
  const allEvents = useMemo(
    () => history.seasons.flatMap(timelineEvents).sort((a, b) => a.at - b.at),
    [history],
  )
  const events = useMemo(() => timelineEvents(season).reverse(), [season])
  const selected = events.find((event) => event.at === at)
  const previous = allEvents.findLast((event) => event.at < at)
  const next = allEvents.find((event) => event.at > at)
  const visibleEvents = events.filter((event) => filter === 'all' || event.type === filter)
  const search = query.trim().toLocaleLowerCase()
  const matchCount = state.teams.filter(
    (team) =>
      `${team.name} ${team.manager}`.toLocaleLowerCase().includes(search) ||
      team.players.some((id) => playerInfo(history, id).name.toLocaleLowerCase().includes(search)),
  ).length
  const unavailable = gap || state.issues.length > 0 || state.draft !== null

  function selectDate(value: number) {
    if (!Number.isFinite(value)) return
    const selectedAt = Math.min(last, Math.max(first, value))
    setAt(selectedAt)
    setShareStatus('')
    const url = new URL(window.location.href)
    url.search = new URLSearchParams({ league: history.leagueId, at: String(selectedAt) }).toString()
    window.history.replaceState(null, '', url)
  }

  async function share() {
    const url = new URL(window.location.href)
    url.search = new URLSearchParams({ league: history.leagueId, at: String(at) }).toString()
    window.history.replaceState(null, '', url)
    try {
      await navigator.clipboard.writeText(url.href)
      setShareStatus('Link copied')
    } catch {
      setShareStatus('Copy the link from your address bar')
    }
  }

  return (
    <>
      <div className="workspace-heading">
        <div>
          <p className="eyebrow">Your league, through time</p>
          <h1>{history.seasons[history.seasons.length - 1].name}</h1>
        </div>
        <div className="workspace-actions">
          <button type="button" onClick={share} className="button secondary">
            Copy this view <span aria-hidden="true">↗</span>
          </button>
          <button type="button" className="text-button" onClick={onChangeLeague}>
            Change league
          </button>
          <span role="status" className="share-status">
            {shareStatus}
          </span>
        </div>
      </div>
      <section className="timeline" aria-label="League timeline">
        <div className="timeline-heading">
          <div>
            <p className="eyebrow">League state as of</p>
            <p className="selected-date">{date(at)}</p>
            <p className="timeline-caption">
              {timeFormat.format(at)} UTC <span>·</span> {season.year} season
            </p>
          </div>
          <div className="timeline-controls">
            <label className="date-label">
              Jump to date
              <input
                type="date"
                value={new Date(at).toISOString().slice(0, 10)}
                min={new Date(first).toISOString().slice(0, 10)}
                max={new Date(last).toISOString().slice(0, 10)}
                onChange={(event) => {
                  if (event.target.value) selectDate(Date.parse(`${event.target.value}T23:59:59.999Z`))
                }}
              />
            </label>
            <div className="step-controls">
              <button
                type="button"
                aria-label="Previous event"
                title="Previous event"
                disabled={!previous}
                onClick={() => previous && selectDate(previous.at)}
              >
                ←
              </button>
              <button
                type="button"
                aria-label="Next event"
                title="Next event"
                disabled={!next}
                onClick={() => next && selectDate(next.at)}
              >
                →
              </button>
              <button type="button" onClick={() => selectDate(last)} disabled={at === last}>
                Latest
              </button>
            </div>
          </div>
        </div>
        <div className="timeline-track">
          <div className="event-marks" aria-hidden="true">
            {allEvents
              .filter((event) => event.type === 'trade' || event.type === 'draft')
              .map((event) => (
                <i
                  key={event.id}
                  className={event.type}
                  style={{ left: `${(100 * (event.at - first)) / Math.max(1, last - first)}%` }}
                />
              ))}
          </div>
          <input
            aria-label="League date"
            aria-valuetext={`${date(at)}, ${timeFormat.format(at)} UTC`}
            type="range"
            min={first}
            max={last}
            step={1}
            value={at}
            onChange={(event) => selectDate(Number(event.target.value))}
            onKeyDown={(event) => {
              if (['ArrowLeft', 'ArrowDown', 'ArrowRight', 'ArrowUp'].includes(event.key)) {
                event.preventDefault()
                selectDate(at + (['ArrowLeft', 'ArrowDown'].includes(event.key) ? -DAY : DAY))
              }
            }}
          />
        </div>
        <div className="season-buttons">
          {history.seasons.map((item) => (
            <button
              type="button"
              key={item.id}
              aria-pressed={season.id === item.id}
              onClick={() => selectDate(seasonStart(item))}
            >
              {item.year}
            </button>
          ))}
        </div>
        <div className="timeline-footer">
          <span>
            <i className="legend trade" />
            Trade <i className="legend draft" />
            Draft
          </span>
          <span>Drag to travel · arrow keys move one day</span>
        </div>
      </section>
      <div className="history-summary">
        <span>
          <b>{history.seasons.length}</b> seasons
        </span>
        <span>
          <b>{state.teams.length}</b> teams
        </span>
        <span>
          <b>{allEvents.filter((event) => event.type === 'trade').length}</b> trades
        </span>
        <span>
          <b>{allEvents.length.toLocaleString()}</b> recorded events
        </span>
        <span className="summary-note">Read-only Sleeper history</span>
      </div>
      <div className="history-layout">
        <section className="rosters" aria-labelledby="rosters-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">League overview</p>
              <h2 id="rosters-heading">Team rosters</h2>
            </div>
            <label className="search-label">
              <span className="sr-only">Find a player or team</span>
              <input
                type="search"
                placeholder="Find a player or team…"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
          </div>
          <p className="roster-note">
            All owned players, including reserves and taxi squads. Names reflect the saved season; lineup
            slots and name-change dates are not reconstructed.
          </p>
          {unavailable ? (
            <div className="coverage-message" role="status">
              <p className="eyebrow">History coverage</p>
              <h3>
                {state.draft
                  ? 'The draft was in progress.'
                  : gap
                    ? 'A change is missing between seasons.'
                    : 'This roster could not be verified.'}
              </h3>
              <p>
                {state.draft
                  ? 'Sleeper provides draft results without individual pick times. Choose the completed draft to see the resulting rosters.'
                  : gap
                    ? 'The closing roster and the next season’s opening roster differ. The date of that change is unknown, so rosters are hidden for this interval.'
                    : 'Some recorded changes do not match the saved rosters. Showing a team here could give you an incorrect history.'}
              </p>
              {state.draft && !state.draft.active && (
                <button type="button" className="button primary" onClick={() => selectDate(state.draft!.end)}>
                  View completed draft →
                </button>
              )}
              {state.draft?.active && <p>Import this league again after the draft finishes.</p>}
              {gap && next && (
                <button type="button" className="button primary" onClick={() => selectDate(next.at)}>
                  Go to next recorded event →
                </button>
              )}
              {state.issues.length > 0 && (
                <details>
                  <summary>
                    View {state.issues.length} source issue{state.issues.length === 1 ? '' : 's'}
                  </summary>
                  <ul>
                    {state.issues.map((issue) => (
                      <li key={issue}>{issue}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          ) : (
            <>
              <div className="team-grid">
                {state.teams.map((team) => (
                  <TeamRoster key={team.id} team={team} history={history} query={search} event={selected} />
                ))}
              </div>
              {!matchCount && <p className="no-results">No matching player or team at this date.</p>}
            </>
          )}
        </section>
        <aside className="activity" aria-labelledby="activity-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">The story of {season.year}</p>
              <h2 id="activity-heading">Activity</h2>
            </div>
            <span className="activity-count">{visibleEvents.length}</span>
          </div>
          <label className="activity-filter">
            <span className="sr-only">Filter activity</span>
            <select value={filter} onChange={(event) => setFilter(event.target.value)}>
              <option value="all">All activity</option>
              <option value="trade">Trades</option>
              <option value="draft">Drafts</option>
              <option value="waiver">Waivers</option>
              <option value="free_agent">Free agents</option>
              <option value="commissioner">Commissioner changes</option>
            </select>
          </label>
          <div className="activity-scroll" tabIndex={0} aria-label="Season activity">
            <ol className="event-list">
              {visibleEvents.map((event) => {
                const names = [
                  ...new Set(
                    [...event.adds, ...event.drops].map((move) => playerInfo(history, move.player).name),
                  ),
                ]
                const summary =
                  event.type === 'draft'
                    ? `${event.adds.length} players selected`
                    : names.length
                      ? `${names.slice(0, 2).join(', ')}${names.length > 2 ? ` +${names.length - 2}` : ''}`
                      : event.picks.length
                        ? `${event.picks.length} draft pick${event.picks.length === 1 ? '' : 's'}`
                        : 'Waiver budget or league update'
                return (
                  <li
                    key={event.id}
                    className={`${event.at === at ? 'selected' : ''} ${event.at > at ? 'future-event' : ''}`}
                  >
                    <button
                      type="button"
                      className="event-button"
                      aria-expanded={event.at === at}
                      onClick={() => selectDate(event.at)}
                    >
                      <span className="event-meta">
                        <span className={`event-type ${event.type}`}>{label(event)}</span>
                        <time dateTime={new Date(event.at).toISOString()}>{date(event.at)}</time>
                      </span>
                      <span className="event-summary">{summary}</span>
                      {event.at > at && <span className="future-label">After selected date</span>}
                    </button>
                    {event.at === at && <EventDetails event={event} season={season} history={history} />}
                  </li>
                )
              })}
            </ol>
            {!visibleEvents.length && <p className="no-results">No matching activity in this season.</p>}
          </div>
        </aside>
      </div>
      <footer className="source-footer">
        <span>
          Sourced from Sleeper · imported {date(last)} at {timeFormat.format(last)} UTC
        </span>
        <a href={`https://sleeper.com/leagues/${season.id}`} target="_blank" rel="noreferrer">
          Open this season in Sleeper ↗
        </a>
        <details>
          <summary>About this history</summary>
          <p>
            Rosters are reconstructed from saved season rosters, completed transactions, and draft results.
            Missing source records may limit accuracy. Team names and managers reflect each season’s retrieved
            record, not a dated history of ownership. Player positions use Sleeper’s latest catalog.
            Draft-pick transfers and waiver-budget transfers appear in activity; complete pick inventories and
            budget balances are not reconstructed. All dates use UTC.
          </p>
        </details>
      </footer>
    </>
  )
}

export default function App() {
  const [history, setHistory] = useState<LeagueHistory | null>(null)
  const [initialAt, setInitialAt] = useState(0)
  const [input, setInput] = useState('')
  const [progress, setProgress] = useState('')
  const [error, setError] = useState('')
  const controller = useRef<AbortController | null>(null)

  const load = useCallback(async (value: string, at = 0) => {
    let id: string
    try {
      id = parseLeagueId(value)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Check the league link.')
      return
    }
    controller.current?.abort()
    const request = new AbortController()
    controller.current = request
    setError('')
    setProgress('Connecting to Sleeper…')
    try {
      const result = await importHistory(id, request.signal, (message) => {
        if (!request.signal.aborted) setProgress(message)
      })
      setHistory(result)
      setInitialAt(at)
      const url = new URL(window.location.href)
      url.search = new URLSearchParams({ league: id, ...(at ? { at: String(at) } : {}) }).toString()
      window.history.replaceState(null, '', url)
    } catch (error) {
      if (!request.signal.aborted)
        setError(error instanceof Error ? error.message : 'Import failed. Please try again.')
    } finally {
      if (controller.current === request) {
        setProgress('')
        controller.current = null
      }
    }
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const league = params.get('league')
    const at = Number(params.get('at'))
    if (league) void load(league, Number.isSafeInteger(at) && at > 0 ? at : 0)
    return () => controller.current?.abort()
  }, [load])

  function submit(event: FormEvent) {
    event.preventDefault()
    void load(input)
  }
  function changeLeague() {
    controller.current?.abort()
    setHistory(null)
    setProgress('')
    window.history.replaceState(null, '', window.location.pathname)
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="app-header">
        <a className="brand" href={window.location.pathname}>
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span>
            League <b>History</b>
          </span>
        </a>
        <span className="header-note">
          A dynasty league archive <span aria-hidden="true">↗</span>
        </span>
      </header>
      <main id="main">
        {history ? (
          <HistoryViewer
            key={history.leagueId}
            history={history}
            initialAt={initialAt}
            onChangeLeague={changeLeague}
          />
        ) : (
          <div className="landing">
            <section className="intro">
              <p className="eyebrow">
                <span className="status-dot" />
                Built for Sleeper dynasty leagues
              </p>
              <h1>
                Every roster.
                <br />
                <em>Every turning point.</em>
              </h1>
              <p className="intro-copy">
                Go back to the draft that started it all. Revisit the trade that changed everything. See your
                entire league at a moment in time.
              </p>
              <form onSubmit={submit} className="import-form" aria-busy={Boolean(progress)}>
                <label htmlFor="league-input">Your Sleeper league</label>
                <div className="input-row">
                  <input
                    id="league-input"
                    type="text"
                    autoComplete="off"
                    placeholder="Paste a league link or ID"
                    value={input}
                    disabled={Boolean(progress)}
                    required
                    aria-invalid={Boolean(error)}
                    aria-describedby={error ? 'import-error' : 'import-hint'}
                    onChange={(event) => {
                      setInput(event.target.value)
                      setError('')
                    }}
                  />
                  <button type="submit" className="button primary" disabled={Boolean(progress)}>
                    {progress ? 'Importing…' : 'Explore league'}
                    <span aria-hidden="true">→</span>
                  </button>
                </div>
                <p id="import-hint">No sign-in needed. Your Sleeper league stays unchanged.</p>
              </form>
              {error && (
                <p id="import-error" className="import-error" role="alert">
                  {error}
                </p>
              )}
              {progress ? (
                <div className="import-progress">
                  <div className="progress-line" />
                  <p role="status">{progress}</p>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => {
                      controller.current?.abort()
                      setProgress('')
                    }}
                  >
                    Cancel import
                  </button>
                  <p className="progress-hint">A multi-season league usually takes about a minute.</p>
                </div>
              ) : (
                <button
                  type="button"
                  className="example-button"
                  onClick={() => {
                    setInput('1312074476493484032')
                    void load('1312074476493484032')
                  }}
                >
                  Try Dynasty - Triton <span>5 seasons of history →</span>
                </button>
              )}
            </section>
            <div className="archive-illustration" aria-hidden="true">
              <div className="archive-top">
                <span>THE LEAGUE ARCHIVE</span>
                <span>01 — ∞</span>
              </div>
              <div className="archive-title">
                Great teams
                <br />
                have a history.
              </div>
              <div className="archive-line">
                <i />
                <i />
                <i />
                <i />
                <i />
              </div>
              <div className="archive-labels">
                <span>Startup draft</span>
                <span>That trade</span>
                <span>Today</span>
              </div>
              <div className="archive-sheets">
                <div>
                  <span>QB</span>
                  <b>THE FOUNDATION</b>
                  <i />
                </div>
                <div>
                  <span>RB</span>
                  <b>THE REBUILD</b>
                  <i />
                </div>
                <div>
                  <span>WR</span>
                  <b>THE CONTENDER</b>
                  <i />
                </div>
                <div>
                  <span>TE</span>
                  <b>THE NEXT CHAPTER</b>
                  <i />
                </div>
              </div>
              <p>Move the timeline. Watch the league change.</p>
            </div>
            <div className="feature-row">
              <div>
                <span>01</span>
                <h2>Bring every season</h2>
                <p>One league link connects your available Sleeper seasons.</p>
              </div>
              <div>
                <span>02</span>
                <h2>Move through time</h2>
                <p>Scrub the timeline or jump straight to a date or transaction.</p>
              </div>
              <div>
                <span>03</span>
                <h2>See the whole league</h2>
                <p>View every team’s players and share the same moment with friends.</p>
              </div>
            </div>
            <footer className="landing-footer">
              <span>Built from FFsim · Independent of Sleeper</span>
              <a href="https://docs.sleeper.com/" target="_blank" rel="noreferrer">
                Powered by Sleeper’s public API ↗
              </a>
            </footer>
          </div>
        )}
      </main>
    </div>
  )
}
