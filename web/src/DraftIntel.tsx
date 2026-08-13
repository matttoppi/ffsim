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
      void getDraftMonitor().then(setMonitor, (cause) => {
        setError(cause instanceof Error ? cause.message : 'Monitor status failed')
      })
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

  return (
    <section className="panel draft-intel" aria-label="Draft intelligence setup">
      <header className="draft-intel-header">
        <div>
          <p className="eyebrow">Draft intelligence</p>
          <h2>Prepare once, then monitor live</h2>
        </div>
        <span className={`draft-state draft-state-${monitoring ? 'live' : preparation.status}`}>
          {monitoring ? 'Monitoring' : preparation.status.replace(/_/g, ' ')}
        </span>
      </header>

      <form className="draft-intel-form" onSubmit={prepare}>
        <label htmlFor="real-draft-id">Real Sleeper draft ID</label>
        <input
          id="real-draft-id"
          value={draftId}
          onChange={(event) => setDraftId(event.target.value)}
          placeholder="Required"
        />
        <label htmlFor="mock-draft-id">Sleeper mock draft URL</label>
        <div className="draft-input-with-action">
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
          Optional: in the Sleeper mobile app, open the real pre-draft league and
          choose its Mock Draft action, then copy that mock URL. A generic Draftboard
          created on desktop may not inherit the league settings.
        </p>
        <label htmlFor="draft-username">Sleeper username</label>
        <input
          id="draft-username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          placeholder="Required to identify your roster"
        />
        <button type="submit" className="button-run" disabled={preparation.status === 'running' || monitoring}>
          {preparation.status === 'running' ? 'Preparing…' : 'Prepare draft'}
        </button>
      </form>

      {preparation.status === 'running' && (
        <p className="draft-progress" role="status">{preparation.stage ?? 'Preparing inputs…'}</p>
      )}
      {(error || preparation.error || monitor.error) && (
        <p className="form-error" role="alert">{error ?? preparation.error ?? monitor.error}</p>
      )}

      {preparation.status === 'ready' && (
        <div className="draft-readiness">
          <dl>
            <div><dt>League</dt><dd>{preparation.league_name}</dd></div>
            <div><dt>Format</dt><dd>{preparation.teams} teams · {preparation.rounds} rounds</dd></div>
            <div><dt>Your slot</dt><dd>{preparation.user_slot ?? 'Waiting on Sleeper'}</dd></div>
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
            <p className="mock-verified">League mock verified against the real draft settings.</p>
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

      {monitor.state && (
        <div className="live-draft-state" role="status">
          <strong>{monitor.state.user_on_clock ? 'You are on the clock' : 'Watching the room'}</strong>
          <span>Pick {monitor.state.current_pick_no ?? 'complete'} · {monitor.state.completed_picks} picks synced</span>
          <span>{monitor.calculation_count ?? 0} recommendation passes</span>
        </div>
      )}

      {monitor.recommendation && (
        <div className="draft-candidates">
          <p className="controls-hint">Uncalibrated Sleeper-ADP baseline · {monitor.recommendation.rollout_count} draft continuations</p>
          <ol>
            {monitor.recommendation.candidates.map((candidate) => (
              <li key={candidate.player_id}>
                <span><strong>{candidate.name}</strong> {candidate.position}</span>
                <span>{(candidate.championship_probability * 100).toFixed(1)}% title</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  )
}
