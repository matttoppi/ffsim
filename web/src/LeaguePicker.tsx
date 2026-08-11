import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  findLeagues,
  getLeagueInfo,
  selectLeague,
  type LeagueSummary,
} from './api'
import { monogram, teamHue } from './events'

const POLL_MS = 1500

/**
 * Username → league list → select → wait for the server-side data refresh.
 * Calls onReady once the chosen league's snapshots are synced.
 */
export function LeaguePicker({
  currentId,
  onReady,
  onCancel,
}: {
  currentId: string | null
  onReady: () => void
  onCancel: (() => void) | null
}) {
  const [username, setUsername] = useState('')
  const [searching, setSearching] = useState(false)
  const [leagues, setLeagues] = useState<LeagueSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [syncingId, setSyncingId] = useState<string | null>(null)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const search = async (event: FormEvent) => {
    event.preventDefault()
    if (!username.trim()) {
      setError('Enter a Sleeper username to look up leagues.')
      return
    }
    setSearching(true)
    setError(null)
    setLeagues(null)
    try {
      const found = await findLeagues(username.trim())
      if (!alive.current) return
      setLeagues(found)
      if (found.length === 0) setError('No 2026 NFL leagues found for that user.')
    } catch (cause) {
      if (!alive.current) return
      setError(cause instanceof Error ? cause.message : 'League lookup failed')
    } finally {
      if (alive.current) setSearching(false)
    }
  }

  const choose = async (league: LeagueSummary) => {
    setError(null)
    setSyncingId(league.league_id)
    try {
      await selectLeague(league.league_id)
      while (alive.current) {
        await new Promise((resolve) => setTimeout(resolve, POLL_MS))
        const info = await getLeagueInfo()
        if (!alive.current) return
        if (info.refresh.status === 'ready') {
          onReady()
          return
        }
        if (info.refresh.status === 'failed') {
          setError(info.refresh.error ?? 'League sync failed')
          setSyncingId(null)
          return
        }
      }
    } catch (cause) {
      if (!alive.current) return
      setError(cause instanceof Error ? cause.message : 'Could not select league')
      setSyncingId(null)
    }
  }

  return (
    <section className="panel picker" aria-label="League select">
      <header className="picker-header">
        <h2 className="panel-title">League select</h2>
        {onCancel && (
          <button type="button" className="button-ghost" onClick={onCancel}>
            Keep current league
          </button>
        )}
      </header>

      {syncingId ? (
        <div className="picker-sync" role="status">
          <span className="sync-pulse" aria-hidden="true" />
          <div>
            <p className="sync-title">Syncing league data</p>
            <p className="sync-detail">
              Downloading rosters, projections, and matchups from Sleeper. This
              takes a minute the first time.
            </p>
          </div>
        </div>
      ) : (
        <>
          <form className="picker-form" onSubmit={search}>
            <label htmlFor="sleeper-username">Sleeper username</label>
            <div className="picker-row">
              <input
                id="sleeper-username"
                type="text"
                autoComplete="username"
                placeholder="e.g. matttoppi"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
              <button type="submit" className="button-run picker-go" disabled={searching}>
                {searching ? 'Searching…' : 'Find leagues'}
              </button>
            </div>
          </form>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {leagues && leagues.length > 0 && (
            <ul className="league-list">
              {leagues.map((league) => (
                <li key={league.league_id}>
                  <button
                    type="button"
                    className="league-card"
                    aria-pressed={league.league_id === currentId}
                    onClick={() => void choose(league)}
                  >
                    <span
                      className="mono"
                      style={{ ['--hue' as string]: teamHue(league.name) }}
                      aria-hidden="true"
                    >
                      {monogram(league.name)}
                    </span>
                    <span className="league-card-body">
                      <span className="league-card-name">{league.name}</span>
                      <span className="league-card-meta">
                        {league.status.replace(/_/g, ' ')}
                        {league.total_rosters ? ` · ${league.total_rosters} teams` : ''}
                        {league.league_id === currentId ? ' · current' : ''}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
