import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { getLeagueInfo, type LeagueInfo } from './api'
import { DraftIntel } from './DraftIntel'
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

export default function App() {
  const { live, results, startError, connection, start, busy } = useSimulation()
  const [activeTab, setActiveTab] = useState<'draft' | 'season'>('draft')
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
      <header className="masthead">
        <div>
          <p className="eyebrow">FFSim · Live Sim Center · 2026</p>
          <h1 className="wordmark">{league?.name ?? 'Pick a league'}</h1>
        </div>
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
        <DraftIntel currentDraftId={league?.draft_id ?? null} />
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
            {results && <Standings results={results} />}
          </div>
        </div>
      </div>
    </div>
  )
}
