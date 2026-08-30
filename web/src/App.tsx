import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { getLeagueInfo, type LeagueInfo, type RecentTrade } from './api'
import { ManagerScouting } from './ManagerScouting'
import { DraftIntel } from './DraftIntel'
import { PersonalRanks } from './PersonalRanks'
import { LeaguePicker } from './LeaguePicker'
import { RaceBoard } from './RaceBoard'
import { Standings } from './Standings'
import { useCountUp } from './useCountUp'
import { useSimulation } from './useSimulation'

const PHASE_LABEL: Record<string, string> = {
  idle: 'Ready',
  starting: 'Starting…',
  queued: 'Queued',
  loading: 'Loading league…',
  running: 'Live',
  completed: 'Complete',
  failed: 'Failed',
}

function formatElapsed(seconds: number): string {
  if (seconds >= 60) {
    const minutes = Math.floor(seconds / 60)
    return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
  }
  return `${seconds.toFixed(1)}s`
}

function Ticker({
  completed,
  total,
  perSecond,
  elapsed,
}: {
  completed: number
  total: number
  perSecond: number
  elapsed: number
}) {
  const displayCompleted = useCountUp(completed)
  const progress = total > 0 ? completed / total : 0
  return (
    <section className="panel ticker" aria-label="Simulation progress">
      <p className="eyebrow">Seasons simulated</p>
      <div className="ticker-main">
        <span className="ticker-count">{Math.round(displayCompleted)}</span>
        <span className="ticker-total">/ {total.toLocaleString()}</span>
      </div>
      <div
        className="ticker-track"
        role="progressbar"
        aria-label="Seasons simulated"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={completed}
      >
        <span className="ticker-fill" style={{ width: `${progress * 100}%` }} />
      </div>
      <dl className="ticker-stats">
        <div>
          <dt>Speed</dt>
          <dd>{perSecond.toFixed(1)}/s</dd>
        </div>
        <div>
          <dt>Elapsed</dt>
          <dd>{formatElapsed(elapsed)}</dd>
        </div>
        <div>
          <dt>Progress</dt>
          <dd>{(progress * 100).toFixed(0)}%</dd>
        </div>
      </dl>
    </section>
  )
}

const tradeDate = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
})

function RecentTrades({ trades }: { trades: RecentTrade[] }) {
  return (
    <section className="panel trades" aria-label="Recent trades">
      <header className="race-header">
        <h2 className="panel-title">Recent trades</h2>
        <p className="standings-meta">Latest 30 completed league deals</p>
      </header>
      {trades.length === 0 ? (
        <p className="detail-empty">No completed trades yet.</p>
      ) : (
        <ol className="trade-list">
          {trades.map((trade) => (
            <li key={trade.transaction_id}>
              <time
                dateTime={
                  trade.completed_at ? new Date(trade.completed_at).toISOString() : undefined
                }
              >
                {trade.completed_at ? tradeDate.format(trade.completed_at) : 'Date unavailable'}
              </time>
              <div className="trade-sides">
                {trade.sides.map((side) => {
                  const assets = [
                    ...side.players.map((player) =>
                      `${player.name}${player.position ? ` · ${player.position}` : ''}${
                        player.team ? ` ${player.team}` : ''
                      }`,
                    ),
                    ...side.draft_picks.map((pick) => `${pick.season} round ${pick.round}`),
                    ...(side.faab ? [`$${side.faab} FAAB`] : []),
                  ]
                  return (
                    <p key={side.roster_id}>
                      <strong>{side.name}</strong>
                      <span>{assets.length ? assets.join(', ') : 'No incoming assets listed'}</span>
                    </p>
                  )
                })}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

export default function App() {
  const { live, results, startError, connection, start, busy } = useSimulation()
  const [activeTab, setActiveTab] = useState<'draft' | 'ranks' | 'scouting' | 'season'>('draft')
  const [serverUp, setServerUp] = useState<boolean | null>(null)
  const [league, setLeague] = useState<LeagueInfo | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [form, setForm] = useState({
    simulations: '300',
    seed: '2026',
    workers: '4',
    teamsOnly: false,
  })
  const [formError, setFormError] = useState<string | null>(null)

  const loadLeague = useCallback(
    () =>
      getLeagueInfo().then(
        (info) => {
          setServerUp(true)
          setLeague(info)
          if (!info.ready) setPickerOpen(true)
          return info
        },
        () => {
          setServerUp(false)
          return null
        },
      ),
    [],
  )

  useEffect(() => {
    void loadLeague()
  }, [loadLeague])

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const simulations = Number(form.simulations)
    const seed = Number(form.seed)
    const workers = Number(form.workers)
    if (!Number.isInteger(simulations) || simulations < 1 || simulations > 10000) {
      setFormError('Simulations must be a whole number from 1 to 10,000.')
      return
    }
    if (!Number.isInteger(seed)) {
      setFormError('Seed must be a whole number.')
      return
    }
    if (!Number.isInteger(workers) || workers < 1 || workers > 32) {
      setFormError('Workers must be a whole number from 1 to 32.')
      return
    }
    setFormError(null)
    setServerUp(true)
    void start({ simulations, seed, workers, teams_only: form.teamsOnly })
  }

  const snapshot = live.snapshot
  const phaseLabel = PHASE_LABEL[live.phase] ?? live.phase
  const errorMessage = startError ?? (live.phase === 'failed' ? live.error : null)
  const showPicker = pickerOpen || (serverUp === true && league !== null && !league.ready)

  return (
    <div className="shell">
      <header className="appbar">
        <div className="appbar-brand">
          <p className="wordmark">FFSim</p>
          <div className="appbar-league">
            <span className="appbar-league-name">{league?.name ?? 'Pick a league'}</span>
            <span className="appbar-league-meta">Live Sim Center · 2026</span>
          </div>
        </div>
        <nav className="app-tabs" aria-label="FFSim tools" role="tablist">
          <button
            id="draft-intelligence-tab"
            type="button"
            className="app-tab"
            role="tab"
            aria-controls="draft-intelligence-panel"
            aria-selected={activeTab === 'draft'}
            onClick={() => setActiveTab('draft')}
          >
            Draft intelligence
          </button>
          <button
            id="league-scouting-tab"
            type="button"
            className="app-tab"
            role="tab"
            aria-controls="league-scouting-panel"
            aria-selected={activeTab === 'scouting'}
            onClick={() => setActiveTab('scouting')}
          >
            League scouting
          </button>
          <button
            id="my-ranks-tab"
            type="button"
            className="app-tab"
            role="tab"
            aria-controls="my-ranks-panel"
            aria-selected={activeTab === 'ranks'}
            onClick={() => setActiveTab('ranks')}
          >
            My ranks
          </button>
          <button
            id="season-simulator-tab"
            type="button"
            className="app-tab"
            role="tab"
            aria-controls="season-simulator-panel"
            aria-selected={activeTab === 'season'}
            onClick={() => setActiveTab('season')}
          >
            Season simulator
          </button>
        </nav>
        <div className="masthead-actions">
          {activeTab === 'season' && (
            <p className={`status-chip status-${live.phase}`} role="status">
              <span
                className={`status-dot${connection === 'reconnecting' ? ' is-reconnecting' : ''}`}
                aria-hidden="true"
              />
              {connection === 'reconnecting' ? 'Reconnecting…' : phaseLabel}
            </p>
          )}
          {league?.ready && !showPicker && (
            <button
              type="button"
              className="button-ghost"
              onClick={() => setPickerOpen(true)}
              disabled={busy}
            >
              Switch league
            </button>
          )}
        </div>
      </header>

      {serverUp === false && (
        <div className="banner banner-error" role="alert">
          <p>
            The simulation server is offline. Start it with{' '}
            <code>./.venv/bin/python -m ffsim serve</code>, then retry.
          </p>
          <button type="button" className="button-ghost" onClick={() => void loadLeague()}>
            Retry connection
          </button>
        </div>
      )}
      {showPicker && (
        <LeaguePicker
          currentId={league?.league_id ?? null}
          currentDraftId={league?.draft_id ?? null}
          onReady={() => {
            setPickerOpen(false)
            void loadLeague()
          }}
          onCancel={league?.ready ? () => setPickerOpen(false) : null}
        />
      )}

      <div
        id="draft-intelligence-panel"
        role="tabpanel"
        aria-labelledby="draft-intelligence-tab"
        hidden={activeTab !== 'draft'}
      >
        <DraftIntel
          currentDraftId={league?.draft_id ?? null}
          onOpenRanks={() => setActiveTab('ranks')}
        />
      </div>

      <div
        id="league-scouting-panel"
        role="tabpanel"
        aria-labelledby="league-scouting-tab"
        hidden={activeTab !== 'scouting'}
      >
        {league?.ready && activeTab === 'scouting' ? (
          <ManagerScouting />
        ) : (
          <p className="controls-hint">Pick a league to load manager history.</p>
        )}
      </div>

      <div
        id="my-ranks-panel"
        role="tabpanel"
        aria-labelledby="my-ranks-tab"
        hidden={activeTab !== 'ranks'}
      >
        {activeTab === 'ranks' && <PersonalRanks />}
      </div>

      <div
        id="season-simulator-panel"
        role="tabpanel"
        aria-labelledby="season-simulator-tab"
        hidden={activeTab !== 'season'}
      >
        {errorMessage && (
          <div className="banner banner-error" role="alert">
            <p>{errorMessage}</p>
          </div>
        )}
        {live.phase === 'completed' && snapshot && (
          <div className="banner banner-final" role="status">
            <p>
              Final: {snapshot.completed.toLocaleString()} seasons simulated in{' '}
              {formatElapsed(snapshot.elapsed_seconds)}.
            </p>
          </div>
        )}
        <div className="layout">
          <form className="panel controls" onSubmit={onSubmit} aria-label="Simulation settings">
            <h2 className="panel-title">Run setup</h2>
            <label htmlFor="simulations">Simulations</label>
            <input
              id="simulations"
              type="number"
              inputMode="numeric"
              min={1}
              max={10000}
              required
              value={form.simulations}
              onChange={(e) => setForm({ ...form, simulations: e.target.value })}
            />
            <label htmlFor="seed">Seed</label>
            <input
              id="seed"
              type="number"
              inputMode="numeric"
              required
              value={form.seed}
              onChange={(e) => setForm({ ...form, seed: e.target.value })}
            />
            <label htmlFor="workers">Workers</label>
            <input
              id="workers"
              type="number"
              inputMode="numeric"
              min={1}
              max={32}
              required
              value={form.workers}
              onChange={(e) => setForm({ ...form, workers: e.target.value })}
            />
            <label className="check">
              <input
                type="checkbox"
                checked={form.teamsOnly}
                onChange={(e) => setForm({ ...form, teamsOnly: e.target.checked })}
              />
              Teams only (skip player tracking)
            </label>
            {formError && (
              <p className="form-error" role="alert">
                {formError}
              </p>
            )}
            <button
              type="submit"
              className="button-run"
              disabled={busy || !league?.ready || showPicker}
            >
              {busy ? 'Running…' : live.phase === 'idle' ? 'Run simulation' : 'Run again'}
            </button>
            {!league?.ready && serverUp && (
              <p className="controls-hint">Pick a league above to unlock the sim.</p>
            )}
            {live.lastResult && live.phase === 'running' && (
              <aside className="spotlight" aria-label="Latest champion">
                <span className="spotlight-label">Last crowned</span>
                <span className="spotlight-team" key={snapshot?.completed}>
                  {live.lastResult.champion}
                </span>
              </aside>
            )}
          </form>

          <div className="stage">
            {snapshot && (
              <Ticker
                completed={snapshot.completed}
                total={snapshot.total}
                perSecond={snapshot.simulations_per_second}
                elapsed={snapshot.elapsed_seconds}
              />
            )}
            <RaceBoard
              snapshot={snapshot}
              lastResult={live.lastResult}
              completed={live.phase === 'completed'}
            />
            {league?.ready && <RecentTrades trades={league.recent_trades ?? []} />}
            {results && <Standings results={results} />}
          </div>
        </div>
      </div>
    </div>
  )
}
