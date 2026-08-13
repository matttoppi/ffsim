import { useEffect, useState, type FormEvent } from 'react'
import {
  getDraftMonitor,
  getDraftPreparation,
  prepareDraft,
  startDraftMonitor,
  stopDraftMonitor,
  type DraftMonitor,
  type DraftPreparation,
} from './api'

const POLL_MS = 1000

export function DraftIntel({ currentDraftId }: { currentDraftId: string | null }) {
  const [draftId, setDraftId] = useState(currentDraftId ?? '')
  const [mockDraftId, setMockDraftId] = useState('')
  const [username, setUsername] = useState('')
  const [preparation, setPreparation] = useState<DraftPreparation>({ status: 'idle' })
  const [monitor, setMonitor] = useState<DraftMonitor>({ status: 'idle' })
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!draftId && currentDraftId) setDraftId(currentDraftId)
  }, [currentDraftId, draftId])

  useEffect(() => {
    void getDraftPreparation().then(setPreparation, () => {})
    void getDraftMonitor().then(setMonitor, () => {})
  }, [])

  useEffect(() => {
    if (preparation.status !== 'running') return
    const timer = window.setInterval(() => {
      void getDraftPreparation().then(setPreparation, (cause) => {
        setError(cause instanceof Error ? cause.message : 'Preparation status failed')
      })
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [preparation.status])

  useEffect(() => {
    if (!['starting', 'running'].includes(monitor.status)) return
    const timer = window.setInterval(() => {
      void getDraftMonitor().then(
        (value) => {
          setMonitor(value)
          setError(null)
        },
        (cause) => {
          setError(cause instanceof Error ? cause.message : 'Monitor status failed')
        },
      )
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [monitor.status])

  const prepare = async (event: FormEvent) => {
    event.preventDefault()
    if (!draftId.trim() || !username.trim()) {
      setError('Real draft ID and Sleeper username are required.')
      return
    }
    setError(null)
    try {
      setPreparation(
        await prepareDraft({
          draft_id: draftId.trim(),
          username: username.trim(),
          ...(mockDraftId.trim() ? { mock_draft_id: mockDraftId.trim() } : {}),
        }),
      )
      setMonitor({ status: 'idle' })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Draft preparation failed')
    }
  }

  const start = async () => {
    setError(null)
    try {
      setMonitor(await startDraftMonitor())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not start monitoring')
    }
  }

  const stop = async () => {
    try {
      setMonitor(await stopDraftMonitor())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not stop monitoring')
    }
  }

  const monitoring = ['starting', 'running'].includes(monitor.status)
  const ready = preparation.status === 'ready'
  const preparing = preparation.status === 'running'
  const chip = monitoring
    ? { label: 'Live', tone: 'live' }
    : preparing
      ? { label: 'Preparing', tone: 'prep' }
      : ready
        ? { label: 'Ready', tone: 'ready' }
        : preparation.status === 'failed'
          ? { label: 'Failed', tone: 'failed' }
          : { label: 'Not prepared', tone: 'idle' }

  const onClock = monitor.state?.user_on_clock ?? false
  const currentPickNo = monitor.state?.current_pick_no ?? null
  const recStatus = monitor.recommendation_status ?? 'idle'
  const recommendationCurrent =
    monitor.recommendation?.pick_no != null &&
    monitor.recommendation.pick_no === currentPickNo
  const candidates = recommendationCurrent ? (monitor.recommendation?.candidates ?? []) : []
  const maxEquity = Math.max(...candidates.map((c) => c.championship_probability), 1e-9)
  const feed = [...(monitor.state?.recent_picks ?? [])].reverse()
  const lastSync = monitor.last_sync_at
    ? new Date(monitor.last_sync_at * 1000).toLocaleTimeString()
    : null
  const heading =
    monitor.status === 'completed'
      ? 'Draft complete'
      : monitor.status === 'stopped'
        ? 'Monitoring stopped'
        : monitor.status === 'failed'
          ? 'Monitoring failed'
          : !monitor.state
            ? 'Synchronizing with Sleeper…'
            : onClock
              ? 'You are on the clock'
              : 'Watching the room'

  return (
    <div className="draft-intel">
      <section className="panel" aria-label="Draft intelligence setup">
        <header className="draft-intel-header">
          <div>
            <p className="eyebrow">Draft intelligence</p>
            <h2>Prepare once, then monitor live</h2>
          </div>
          <span className={`draft-chip draft-chip-${chip.tone}`}>
            <span className="draft-chip-dot" aria-hidden="true" />
            {chip.label}
          </span>
        </header>

        <form className="draft-form" onSubmit={prepare}>
          <div className="field">
            <label htmlFor="real-draft-id">Real Sleeper draft ID</label>
            <input
              id="real-draft-id"
              value={draftId}
              onChange={(event) => setDraftId(event.target.value)}
              placeholder="e.g. 1131…"
            />
          </div>
          <div className="field">
            <label htmlFor="draft-username">Sleeper username</label>
            <input
              id="draft-username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Identifies your roster"
            />
          </div>
          <div className="field field-wide">
            <div className="field-label-row">
              <label htmlFor="mock-draft-id">Sleeper mock draft URL</label>
              <span className="field-optional">Optional</span>
            </div>
            <div className="input-with-action">
              <input
                id="mock-draft-id"
                value={mockDraftId}
                onChange={(event) => setMockDraftId(event.target.value)}
                onFocus={(event) => event.currentTarget.select()}
                placeholder="https://sleeper.app/draft/nfl/…"
              />
              {mockDraftId && (
                <button type="button" className="button-ghost" onClick={() => setMockDraftId('')}>
                  Clear
                </button>
              )}
            </div>
            <p className="field-help">
              In the Sleeper mobile app, open the real pre-draft league and choose its Mock
              Draft action, then copy that mock URL. A generic Draftboard created on desktop
              may not inherit the league settings.
            </p>
          </div>
          <div className="draft-form-actions">
            <button type="submit" className="button-run" disabled={preparing || monitoring}>
              {preparing ? 'Preparing…' : 'Prepare draft'}
            </button>
            {preparing && (
              <p className="draft-progress" role="status">
                <span className="draft-chip-dot" aria-hidden="true" />
                {preparation.stage ?? 'Preparing inputs…'}
              </p>
            )}
          </div>
        </form>

        {(error || preparation.error || monitor.error) && (
          <p className="form-error" role="alert">{error ?? preparation.error ?? monitor.error}</p>
        )}

        {ready && (
          <div className="draft-readiness">
            <dl className="readiness-grid">
              <div><dt>League</dt><dd>{preparation.league_name}</dd></div>
              <div><dt>Format</dt><dd>{preparation.teams} tm · {preparation.rounds} rd</dd></div>
              <div><dt>Your slot</dt><dd>{preparation.user_slot ?? 'TBD'}</dd></div>
              <div><dt>ADP players</dt><dd>{preparation.market_players}</dd></div>
              <div><dt>Manager history</dt><dd>{preparation.history?.managers_with_eligible_history}/{preparation.history?.managers}</dd></div>
              <div><dt>Season worlds</dt><dd>{preparation.world_bank?.worlds ?? 0}</dd></div>
            </dl>
            {preparation.mock_compatibility?.status === 'mismatch' && (
              <div className="mock-warning" role="alert">
                <strong>Mock does not match the real league.</strong>
                <ul>
                  {preparation.mock_compatibility.reasons.map((reason) => (
                    <li key={reason.code}>
                      {reason.label}: expected {JSON.stringify(reason.expected)}, got {JSON.stringify(reason.actual)}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {preparation.mock_compatibility?.status === 'exact' && (
              <p className="mock-verified">✓ League mock verified against the real draft settings.</p>
            )}
            <div className="draft-actions">
              <button
                type="button"
                className="button-run"
                disabled={!preparation.monitor_ready || monitoring}
                onClick={() => void start()}
              >
                {monitoring ? 'Monitoring…' : 'Start monitoring'}
              </button>
              {monitoring && (
                <button type="button" className="button-ghost" onClick={() => void stop()}>
                  Stop
                </button>
              )}
            </div>
            {!preparation.monitor_ready && preparation.blockers && (
              <p className="controls-hint">Resolve: {preparation.blockers.join(', ').replace(/_/g, ' ')}</p>
            )}
          </div>
        )}
      </section>

      {(monitoring || monitor.state) && (
        <section
          className={`panel draft-live${onClock ? ' is-on-clock' : ''}`}
          aria-label="Live draft board"
        >
          <div className="clock-hero" role="status">
            <div>
              <p className="eyebrow">{onClock ? 'Your pick' : 'Live draft'}</p>
              <h3>{heading}</h3>
              {lastSync && (
                <p className="sync-meta">
                  Synced {lastSync} · {monitor.state?.completed_picks ?? 0} picks in
                </p>
              )}
            </div>
            {monitor.state && (
              <dl className="clock-facts">
                <div><dt>Current pick</dt><dd>{monitor.state.current_pick_no ?? '—'}</dd></div>
                <div><dt>Picks in</dt><dd>{monitor.state.completed_picks}</dd></div>
                <div><dt>Your next</dt><dd>{monitor.state.user_next_pick_no ?? '—'}</dd></div>
                <div><dt>Rec passes</dt><dd>{monitor.calculation_count ?? 0}</dd></div>
              </dl>
            )}
          </div>
          {monitoring && monitor.state && (
            recStatus === 'pending' ? (
              <p className="draft-progress" role="status">
                Recommendation pending for pick {monitor.recommendation_pick_no}…
              </p>
            ) : recStatus === 'calculating' ? (
              <p className="draft-progress" role="status">
                Calculating recommendations for pick {monitor.recommendation_pick_no}…
              </p>
            ) : recStatus === 'failed' ? (
              <p className="form-error" role="alert">
                Calculation failed for pick {monitor.recommendation_pick_no}:{' '}
                {monitor.recommendation_error}
              </p>
            ) : !onClock ? (
              <p className="controls-hint">Recommendations appear when you are on the clock.</p>
            ) : null
          )}
          {monitoring &&
            monitor.recommendation_discarded_pick_no != null &&
            !recommendationCurrent && (
              <p className="controls-hint" role="status">
                Pick {monitor.recommendation_discarded_pick_no} result discarded — the draft
                advanced.
              </p>
            )}
          {candidates.length > 0 && (
            <>
              <ol className="board">
                {candidates.map((candidate, index) => (
                  <li key={candidate.player_id} className="board-row">
                    <span className="board-rank">{index + 1}</span>
                    <span className={`pos-badge pos-${candidate.position ?? 'NA'}`}>
                      {candidate.position ?? '—'}
                    </span>
                    <span className="board-player">
                      <strong>{candidate.name}</strong>
                      <small>
                        {(candidate.playoff_probability * 100).toFixed(0)}% playoffs ·{' '}
                        {candidate.expected_wins.toFixed(1)} wins
                      </small>
                    </span>
                    <span className="board-equity">
                      <span className="board-track" aria-hidden="true">
                        <span
                          className="board-fill"
                          style={{ width: `${(candidate.championship_probability / maxEquity) * 100}%` }}
                        />
                      </span>
                      <strong>{(candidate.championship_probability * 100).toFixed(1)}%</strong>
                    </span>
                  </li>
                ))}
              </ol>
              <p className="board-footnote">
                {recStatus === 'ready' ? 'Ready' : 'Preliminary'} for pick{' '}
                {monitor.recommendation?.pick_no} · championship equity · uncalibrated
                Sleeper-ADP baseline · {monitor.recommendation?.rollout_count} draft
                continuations
              </p>
            </>
          )}
          {feed.length > 0 && (
            <div className="pick-feed">
              <h4>Pick feed</h4>
              <ol className="pick-feed-list">
                {feed.map((pick) => (
                  <li key={pick.pick_no} className="pick-feed-row">
                    <span className="feed-pick">
                      R{pick.round} · #{pick.pick_no}
                    </span>
                    <span className={`pos-badge pos-${pick.position ?? 'NA'}`}>
                      {pick.position ?? '—'}
                    </span>
                    <span className="feed-player">
                      <strong>{pick.name}</strong>
                      <small>
                        {pick.team ?? 'FA'} · slot {pick.draft_slot}
                        {pick.roster_id != null ? ` · roster ${pick.roster_id}` : ''}
                      </small>
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
