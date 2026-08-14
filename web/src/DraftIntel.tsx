import { useEffect, useState, type FormEvent } from 'react'
import {
  getDraftMonitor,
  getDraftPreparation,
  prepareDraft,
  simulateCompletedDraft,
  startDraftMonitor,
  stopDraftMonitor,
  type DraftLeagueSimulation,
  type DraftMonitor,
  type DraftPreparation,
  type DraftRecommendationCandidate,
  type WorkProgress,
} from './api'

const POLL_MS = 1000

const REC_STEPS = ['Queued', 'First board', 'Screening field', 'Refining finalists', 'Final suggestion']
const REC_PHASE: Record<string, number> = { pending: 0, calculating: 1, expanding: 2, refining: 3 }

function ProgressBar({ progress }: { progress: WorkProgress | null | undefined }) {
  const pct =
    progress && progress.total > 0
      ? Math.min(100, Math.round((100 * progress.done) / progress.total))
      : null
  return (
    <div className="progress-row">
      <div className={`progress-track${pct == null ? ' is-indeterminate' : ''}`}>
        <span
          className="progress-fill"
          style={pct == null ? undefined : { width: `${pct}%` }}
        />
      </div>
      {pct != null && <span className="progress-pct">{pct}%</span>}
    </div>
  )
}

function WhyThisPick({
  recommendation,
  leader,
  runnerUpName,
  currentPickNo,
}: {
  recommendation: NonNullable<DraftMonitor['recommendation']>
  leader: DraftRecommendationCandidate
  runnerUpName: string | null
  currentPickNo: number | null
}) {
  const delta = recommendation.paired_value_delta_vs_runner_up
  const tossUp = recommendation.decision_status === 'toss_up'
  const nextPick = leader.next_turn_pick_no ?? recommendation.next_user_pick_no ?? null
  const vona = leader.value_over_next_alternative
  const survival = leader.survives_to_next_pick
  const usualAlternative = leader.later_alternatives?.[0]
  const adpDrift =
    leader.adp != null && currentPickNo != null ? currentPickNo - leader.adp : null
  const reasons: Array<{ label: string; text: string }> = []
  if (!tossUp && delta && runnerUpName) {
    const winShare =
      delta.better_continuation_probability != null
        ? ` and comes out ahead in ${(delta.better_continuation_probability * 100).toFixed(0)}% of them`
        : ''
    reasons.push({
      label: 'Best final roster',
      text:
        `Across ${recommendation.rollout_count} simulated rest-of-drafts, taking ${leader.name} finishes with ` +
        `${delta.projected_value_delta >= 0 ? '+' : ''}${delta.projected_value_delta.toFixed(1)} more season points of ` +
        `starting-lineup value than ${runnerUpName} (95% range ${delta.interval[0].toFixed(1)} to ${delta.interval[1].toFixed(1)})${winShare}. ` +
        `That already accounts for everyone you could draft instead at every later pick.`,
    })
  }
  if (tossUp) {
    reasons.push({
      label: 'Statistical tie',
      text:
        `The tied options finish with the same final-roster value within simulation precision, so the order is decided by ` +
        `what waiting would cost, then by market value — among equals, ${leader.name} is the strongest asset to hold or trade.`,
    })
  }
  if (vona != null && nextPick != null) {
    if (vona > 1) {
      const survivalText =
        survival != null ? ` He is back on the board at pick ${nextPick} only ${(survival * 100).toFixed(0)}% of the time` : ''
      const alternativeText = usualAlternative
        ? `; if you pass, the simulations say your next turn usually offers ${usualAlternative.name} (${(usualAlternative.probability * 100).toFixed(0)}%) instead`
        : ''
      reasons.push({
        label: 'Waiting costs points',
        text: `Passing now gives back about ${vona.toFixed(1)} points versus the best pick at any position expected at pick ${nextPick}.${survivalText}${alternativeText}.`,
      })
    } else {
      reasons.push({
        label: 'No urgency',
        text: `Waiting is nearly free — comparable value should still be available at pick ${nextPick} — so he leads on overall value, not scarcity.`,
      })
    }
  }
  if (leader.positional_value_drop != null && leader.positional_value_drop > 1 && nextPick != null) {
    reasons.push({
      label: `${leader.position ?? 'Position'} cliff`,
      text:
        `He projects ${leader.positional_value_drop.toFixed(0)} points above the best ${leader.position} expected to reach your next turn. ` +
        `That is the same-position gap only — you are not forced to fill ${leader.position} next turn, so the real cost of waiting is the smaller any-position number above.`,
    })
  }
  if (adpDrift != null && Math.abs(adpDrift) >= 5) {
    reasons.push(
      adpDrift > 0
        ? {
            label: 'Market value',
            text: `The market drafts him around pick ${leader.adp!.toFixed(0)} — he has fallen ${adpDrift.toFixed(0)} picks, so you are buying below price.`,
          }
        : {
            label: 'Ahead of market',
            text: `This is ${Math.abs(adpDrift).toFixed(0)} picks before his ADP of ${leader.adp!.toFixed(0)} — the model believes the points justify the reach; expect the room to see it as early.`,
          },
    )
  }
  if (reasons.length === 0) return null
  return (
    <section className="why-panel" aria-label="Why this pick">
      <h4>Why {leader.name}</h4>
      <ul>
        {reasons.map((reason) => (
          <li key={reason.label}>
            <strong>{reason.label}.</strong> {reason.text}
          </li>
        ))}
      </ul>
      <small>
        Points are projected season output of your final starting lineup versus a replacement-level
        roster; comparisons simulate complete rest-of-drafts, not just this pick.
      </small>
    </section>
  )
}

export function DraftIntel({ currentDraftId }: { currentDraftId: string | null }) {
  const [draftId, setDraftId] = useState(currentDraftId ?? '')
  const [mockDraftId, setMockDraftId] = useState('')
  const [username, setUsername] = useState('')
  const [preparation, setPreparation] = useState<DraftPreparation>({ status: 'idle' })
  const [monitor, setMonitor] = useState<DraftMonitor>({ status: 'idle' })
  const [error, setError] = useState<string | null>(null)
  const [positionFilter, setPositionFilter] = useState<string | null>(null)
  const [simulation, setSimulation] = useState<DraftLeagueSimulation | null>(null)
  const [simulating, setSimulating] = useState(false)

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
      setSimulation(null)
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

  const simulate = async () => {
    setError(null)
    setSimulating(true)
    try {
      setSimulation(await simulateCompletedDraft())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not simulate the completed draft')
    } finally {
      setSimulating(false)
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
  const finalists = recommendationCurrent ? (monitor.recommendation?.candidates ?? []) : []
  const screenedCandidates = recommendationCurrent
    ? (monitor.recommendation?.screened_candidates ?? [])
    : []
  const candidates = [...finalists, ...screenedCandidates]
  const positions = [...new Set(candidates.flatMap((c) => (c.position ? [c.position] : [])))]
  const visibleFinalists = positionFilter
    ? finalists.filter((candidate) => candidate.position === positionFilter)
    : finalists
  const visibleScreened = positionFilter
    ? screenedCandidates.filter((candidate) => candidate.position === positionFilter)
    : screenedCandidates
  const visibleCandidates = [...visibleFinalists, ...visibleScreened]
  const boardSections = [
    {
      label: recStatus === 'expanding' ? 'Current screen' : 'Refined contenders',
      candidates: visibleFinalists,
      screened: false,
    },
    { label: 'Screened watchlist', candidates: visibleScreened, screened: true },
  ].filter((section) => section.candidates.length > 0)
  const leader = finalists[0] ?? candidates[0]
  const positionTiming = recommendationCurrent
    ? (monitor.recommendation?.position_timing ?? [])
    : []
  const leaderEdge =
    monitor.recommendation?.paired_value_delta_vs_runner_up?.projected_value_delta
  const tossUp = monitor.recommendation?.decision_status === 'toss_up'
  const coLeaderIds = new Set(monitor.recommendation?.co_leader_candidate_ids ?? [])
  const coLeaderNames = candidates.flatMap((candidate) =>
    coLeaderIds.has(candidate.player_id) ? [candidate.name] : [],
  )
  const backToBack =
    onClock &&
    currentPickNo != null &&
    monitor.state?.user_next_pick_no === currentPickNo + 1
  const feed = [...(monitor.state?.recent_picks ?? [])].reverse()
  const leagueRows = simulation?.rosters ?? monitor.league_equity?.rosters ?? []
  const leagueEquityCurrent =
    monitor.league_equity?.completed_picks === monitor.state?.completed_picks
  const leagueEquityUpdating = simulation
    ? false
    : ['pending', 'calculating'].includes(monitor.league_equity_status ?? 'idle') ||
      !leagueEquityCurrent
  const maxLeagueEquity = Math.max(
    ...leagueRows.map((row) => row.championship_probability),
    1e-9,
  )
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
              <div className="prepare-progress">
                <p className="draft-progress" role="status">
                  <span className="spinner" aria-hidden="true" />
                  {preparation.stage ?? 'Preparing inputs…'}
                  {preparation.stage_count != null && (
                    <> · step {preparation.stage_no ?? 0} of {preparation.stage_count}</>
                  )}
                </p>
                <ProgressBar
                  progress={
                    preparation.stage_count != null
                      ? { done: preparation.stage_no ?? 0, total: preparation.stage_count }
                      : null
                  }
                />
              </div>
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
                <div><dt>Odds updates</dt><dd>{monitor.league_equity_calculation_count ?? 0}</dd></div>
              </dl>
            )}
            {monitor.status === 'completed' && (
              <button
                type="button"
                className="button-run"
                disabled={simulating}
                onClick={() => void simulate()}
              >
                {simulating ? (
                  <>
                    <span className="spinner" aria-hidden="true" /> Simulating league…
                  </>
                ) : simulation ? (
                  'Run full simulation again'
                ) : (
                  'Run full league simulation'
                )}
              </button>
            )}
          </div>
          <div className="draft-live-body">
            <div className="draft-live-main">
          {monitoring && monitor.state && (
            recStatus === 'failed' ? (
              <p className="form-error" role="alert">
                Calculation failed for pick {monitor.recommendation_pick_no}:{' '}
                {monitor.recommendation_error}
              </p>
            ) : recStatus in REC_PHASE ? (
              <div className="rec-pipeline">
                <ol className="rec-steps" aria-hidden="true">
                  {REC_STEPS.map((label, index) => (
                    <li
                      key={label}
                      className={
                        index < REC_PHASE[recStatus]
                          ? 'is-done'
                          : index === REC_PHASE[recStatus]
                            ? 'is-active'
                            : ''
                      }
                    >
                      {index < REC_PHASE[recStatus] ? (
                        '✓'
                      ) : index === REC_PHASE[recStatus] ? (
                        <span className="spinner" />
                      ) : null}
                      {label}
                    </li>
                  ))}
                </ol>
                <ProgressBar
                  progress={
                    monitor.recommendation_progress ??
                    (recStatus === 'expanding' && monitor.recommendation?.candidate_pool
                      ? {
                          done: monitor.recommendation.candidates_evaluated ?? 0,
                          total: monitor.recommendation.candidate_pool,
                        }
                      : null)
                  }
                />
                <p className="draft-progress" role="status">
                  {recStatus === 'pending' ? (
                    <>Recommendation pending for pick {monitor.recommendation_pick_no}…</>
                  ) : recStatus === 'calculating' ? (
                    <>Calculating recommendations for pick {monitor.recommendation_pick_no}…</>
                  ) : recStatus === 'expanding' ? (
                    <>
                      Screening the board for pick {monitor.recommendation_pick_no} —{' '}
                      {monitor.recommendation?.candidates_evaluated} of{' '}
                      {monitor.recommendation?.candidate_pool} candidates evaluated…
                    </>
                  ) : (
                    <>Refining the top candidates for pick {monitor.recommendation_pick_no}…</>
                  )}
                </p>
              </div>
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
              {screenedCandidates.length > 0 && (
                <p className="controls-hint">
                  <strong>{candidates.length} options shown.</strong> {finalists.length} refined
                  contenders are ranked together; {screenedCandidates.length} earlier-stage
                  estimates remain in a separate watchlist.
                </p>
              )}
              {tossUp && (
                <p className="controls-hint" role="status">
                  <strong>No clear winner on projected value.</strong>{' '}
                  {coLeaderNames.join(', ')} form the top tier; they are ordered by value
                  over next available (VONA) — how much you lose by waiting until your
                  next pick instead of taking them now.
                </p>
              )}
              {backToBack && (
                <p className="controls-hint">
                  You also have pick {monitor.state?.user_next_pick_no}. Back-to-back
                  options often grade even because the model assumes you take the
                  runner-up with your next pick.
                </p>
              )}
              {positions.length > 1 && (
                <div className="pos-filter" role="group" aria-label="Filter candidates by position">
                  <button
                    type="button"
                    className={`pos-chip${positionFilter === null ? ' is-active' : ''}`}
                    onClick={() => setPositionFilter(null)}
                  >
                    All
                  </button>
                  {positions.map((position) => (
                    <button
                      key={position}
                      type="button"
                      className={`pos-chip${positionFilter === position ? ' is-active' : ''}`}
                      onClick={() => setPositionFilter(position)}
                    >
                      {position}
                    </button>
                  ))}
                </div>
              )}
              {visibleCandidates.length === 0 && (
                <p className="controls-hint">
                  No {positionFilter} among the evaluated candidates for this pick.
                </p>
              )}
              <p
                className={`board-state${recStatus === 'ready' ? ' is-final' : ''}`}
                role="status"
              >
                {recStatus === 'ready' ? (
                  <>
                    <strong>✓ Final suggestion</strong> — fully computed for pick{' '}
                    {monitor.recommendation?.pick_no}.
                  </>
                ) : (
                  <>
                    <span className="spinner" aria-hidden="true" />
                    <strong>First look</strong> — usable now, but rankings can still shift while
                    the model refines.
                  </>
                )}
              </p>
              {monitor.recommendation && leader && (
                <WhyThisPick
                  recommendation={monitor.recommendation}
                  leader={leader}
                  runnerUpName={
                    candidates.find(
                      (candidate) =>
                        candidate.player_id ===
                        monitor.recommendation?.runner_up_candidate_id,
                    )?.name ?? null
                  }
                  currentPickNo={monitor.recommendation.pick_no ?? null}
                />
              )}
              {boardSections.map((section) => {
                const maxValue = Math.max(
                  ...section.candidates.map((candidate) => candidate.projected_roster_value),
                  1e-9,
                )
                const List = section.screened ? 'ul' : 'ol'
                return (
                  <section className="board-section" key={section.label}>
                    <h4>{section.label}</h4>
                    <List
                      className={`board${section.screened ? ' is-screened' : ''}${
                        recStatus === 'ready' ? '' : ' is-preliminary'
                      }`}
                    >
                {section.candidates.map((candidate, rank) => {
                  const screened = section.screened
                  const inTopTier = tossUp && coLeaderIds.has(candidate.player_id)
                  const deltaVsLeader =
                    candidate.projected_roster_value - leader.projected_roster_value
                  return (
                    <li key={candidate.player_id} className="board-row">
                      <span className="board-rank">
                        {screened ? 'W' : inTopTier ? 'T1' : rank + 1}
                      </span>
                      <span className={`pos-badge pos-${candidate.position ?? 'NA'}`}>
                        {candidate.position ?? '—'}
                      </span>
                      <span className="board-player">
                        <strong>{candidate.name}</strong>
                        <small>
                          title {(candidate.championship_probability * 100).toFixed(1)}% ·{' '}
                          {(candidate.playoff_probability * 100).toFixed(0)}% playoffs ·{' '}
                          {candidate.expected_wins.toFixed(1)} wins
                        </small>
                        {candidate.adp != null && (
                          <small>
                            ADP {candidate.adp.toFixed(0)}
                            {candidate.survives_to_next_pick != null &&
                              (candidate.next_turn_pick_no ??
                                monitor.recommendation?.next_user_pick_no) != null && (
                                <> · {(candidate.survives_to_next_pick * 100).toFixed(0)}% chance back at pick{' '}
                                  {candidate.next_turn_pick_no ??
                                    monitor.recommendation?.next_user_pick_no}</>
                              )}
                          </small>
                        )}
                        {candidate.current_marginal_value != null &&
                          candidate.expected_best_later_value != null &&
                          candidate.next_turn_pick_no != null && (
                            <small>
                              Adds {candidate.current_marginal_value.toFixed(0)} to your roster now ·{' '}
                              {candidate.expected_best_later_value.toFixed(0)} expected best at pick{' '}
                              {candidate.next_turn_pick_no}
                              {candidate.positional_value_drop != null && (
                                <> · {candidate.positional_value_drop >= 0 ? '+' : ''}
                                  {candidate.positional_value_drop.toFixed(0)} {candidate.position} drop</>
                              )}
                              {candidate.later_alternatives?.[0] && (
                                <> · often {candidate.later_alternatives[0].name}{' '}
                                  ({(candidate.later_alternatives[0].probability * 100).toFixed(0)}%)</>
                              )}
                            </small>
                          )}
                      </span>
                      <span className="board-equity">
                        <span className="board-track" aria-hidden="true">
                          <span
                            className="board-fill"
                            style={{
                              width: `${Math.max(0, (candidate.projected_roster_value / maxValue) * 100)}%`,
                            }}
                          />
                        </span>
                        {screened ? (
                          <span className="board-numbers">
                            <strong className="board-delta">watchlist</strong>
                            <small>
                              {candidate.projected_roster_value.toFixed(1)} proj pts ·{' '}
                              {candidate.rollout_count ??
                                monitor.recommendation?.screened_rollout_count}{' '}
                              continuations
                            </small>
                          </span>
                        ) : rank === 0 ? (
                          <span className="board-numbers">
                            <strong>{candidate.projected_roster_value.toFixed(1)} pts</strong>
                            {tossUp ? (
                              <small>
                                top tier
                                {candidate.value_over_next_alternative != null && (
                                  <> · VONA {candidate.value_over_next_alternative >= 0 ? '+' : ''}
                                    {candidate.value_over_next_alternative.toFixed(1)}</>
                                )}
                              </small>
                            ) : leaderEdge != null && (
                              <small>
                                {Math.abs(leaderEdge) < 0.05
                                  ? 'even with next'
                                  : `+${leaderEdge.toFixed(1)} pts vs next`}
                              </small>
                            )}
                          </span>
                        ) : (
                          <span className="board-numbers">
                            <strong className="board-delta">
                              {inTopTier
                                ? candidate.value_over_next_alternative != null
                                  ? `VONA ${candidate.value_over_next_alternative >= 0 ? '+' : ''}${candidate.value_over_next_alternative.toFixed(1)}`
                                  : 'top tier'
                                : Math.abs(deltaVsLeader) < 0.05
                                ? 'even'
                                : `${deltaVsLeader.toFixed(1)} pts`}
                            </strong>
                            <small>{candidate.projected_roster_value.toFixed(1)} proj pts</small>
                          </span>
                        )}
                      </span>
                    </li>
                  )
                })}
                    </List>
                  </section>
                )
              })}
              <p className="board-footnote">
                {recStatus === 'ready'
                  ? 'Ready'
                  : recStatus === 'expanding'
                    ? 'Screening'
                    : recStatus === 'refining'
                      ? 'Refining'
                      : 'Preliminary'}{' '}
                for pick {monitor.recommendation?.pick_no} · projected lineup points over
                replacement for the completed roster if drafted now, ± vs the top option ·
                title odds shown as secondary telemetry · uncalibrated Sleeper-ADP baseline ·{' '}
                {monitor.recommendation?.rollout_count} draft continuations
                {screenedCandidates.length > 0 ? ' for finalists' : ''}
                {monitor.recommendation?.run_signature && (
                  <> · run {monitor.recommendation.run_signature.slice(0, 12)} · seed{' '}
                    {monitor.recommendation.seed} · engine v
                    {monitor.recommendation.decision_engine_version} · world{' '}
                    {monitor.recommendation.world_bank_version.slice(0, 8)} · model{' '}
                    {monitor.recommendation.draft_model_version}</>
                )}
                . Title odds include ADP-driven future drafts and the chance to select players
                who survive to later picks.
              </p>
              {positionTiming.length > 0 && (
                <div className="pick-feed position-timing">
                  <h4>QB &amp; TE ADP-only timing · next three turns</h4>
                  <div className="timing-grid">
                    {positionTiming.map((row) => (
                      <section key={row.position} className="timing-card">
                        <header>
                          <span className={`pos-badge pos-${row.position}`}>{row.position}</span>
                          <strong>
                            {row.recommendation === 'TAKE_NOW'
                              ? 'Take now'
                              : row.recommendation === 'WAIT_THROUGH_PICK'
                                ? `Wait through pick ${row.target_pick_no}`
                              : `Target by pick ${row.target_pick_no}`}
                          </strong>
                        </header>
                        <p>
                          Now: {row.best_now_name ?? row.best_now_player_id}{' '}
                          {row.best_now_points.toFixed(0)} pts · ADP {row.best_now_adp.toFixed(0)}
                        </p>
                        <ul>
                          {row.turns.map((turn) => (
                            <li key={turn.pick_no}>
                              <strong>Pick {turn.pick_no}</strong>
                              <span>
                                {turn.name ?? 'No ADP option'} · {turn.projected_points.toFixed(0)} pts
                                {turn.adp != null ? ` · ADP ${turn.adp.toFixed(0)}` : ''}
                              </span>
                              <small>−{turn.drop_from_now.toFixed(0)} vs now</small>
                            </li>
                          ))}
                        </ul>
                      </section>
                    ))}
                  </div>
                  <p className="board-footnote">
                    Deterministic ADP illustration only — not a survival probability. Modeled
                    return chances, next-turn value, and title equity appear above.
                  </p>
                </div>
              )}
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
            </div>
            <aside
              className="league-equity"
              aria-label="League championship odds"
              aria-live="polite"
            >
              <div className="league-equity-header">
                <div>
                  <p className="eyebrow">Live rankings</p>
                  <h4>{simulation ? 'Full simulation results' : 'Championship odds'}</h4>
                </div>
                {leagueEquityUpdating && (
                  <span className="draft-chip draft-chip-prep">
                    <span className="spinner" aria-hidden="true" />
                    Updating
                  </span>
                )}
              </div>
              {leagueRows.length > 0 && leagueEquityUpdating && (
                <ProgressBar progress={monitor.league_equity_progress} />
              )}
              {leagueRows.length > 0 ? (
                <ol className={`league-equity-list${leagueEquityUpdating ? ' is-preliminary' : ''}`}>
                  {leagueRows.map((row, index) => (
                    <li
                      key={row.roster_id}
                      className={`league-equity-row${row.is_user ? ' is-user' : ''}`}
                    >
                      <span className="league-equity-rank">{index + 1}</span>
                      <span className="league-equity-team">
                        <strong>{row.name}{row.is_user ? ' (You)' : ''}</strong>
                        <small>
                          {row.draft_slot != null ? `Slot ${row.draft_slot} · ` : ''}
                          {(row.playoff_probability * 100).toFixed(0)}% playoffs
                          {simulation && <> · {row.expected_wins.toFixed(1)} wins</>}
                        </small>
                        <span className="board-track" aria-hidden="true">
                          <span
                            className="board-fill"
                            style={{ width: `${(row.championship_probability / maxLeagueEquity) * 100}%` }}
                          />
                        </span>
                      </span>
                      <strong className="league-equity-odds">
                        {(row.championship_probability * 100).toFixed(1)}%
                      </strong>
                    </li>
                  ))}
                </ol>
              ) : monitor.league_equity_status === 'failed' ? (
                <p className="form-error" role="alert">
                  League odds failed: {monitor.league_equity_error}
                </p>
              ) : (
                <div className="rec-pipeline">
                  <ProgressBar progress={monitor.league_equity_progress} />
                  <p className="draft-progress" role="status">
                    Calculating league odds for pick {monitor.league_equity_pick_no ?? 'final'}…
                  </p>
                </div>
              )}
              {leagueRows.length > 0 && (
                <p className="board-footnote">
                  {simulation ? (
                    <>Exact final rosters · {simulation.joint_outcome_count} season worlds</>
                  ) : (
                    <>
                      {leagueEquityUpdating
                        ? `Refining for pick ${monitor.league_equity_pick_no ?? 'final'}`
                        : `Updated through pick ${monitor.league_equity?.completed_picks ?? 0}`}{' '}
                      · uncalibrated baseline · {monitor.league_equity?.rollout_count ?? 0} draft continuations
                    </>
                  )}
                </p>
              )}
            </aside>
          </div>
        </section>
      )}
    </div>
  )
}
