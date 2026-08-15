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

function tieBreakText(
  basis: NonNullable<DraftMonitor['recommendation']>['headline_tie_break_basis'],
  leaderName: string,
) {
  if (basis === 'urgency') return `${leaderName} leads on effective next-turn urgency.`
  if (basis === 'market_adp') {
    return `${leaderName} leads on market ADP, a draft-position proxy, not trade value.`
  }
  if (basis === 'engine_rank') return `${leaderName} leads on the engine's deterministic rank.`
  return 'No secondary tie-break basis was recorded.'
}

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
  currentPickNo,
}: {
  recommendation: NonNullable<DraftMonitor['recommendation']>
  leader: DraftRecommendationCandidate
  currentPickNo: number | null
}) {
  const delta = recommendation.paired_value_delta_vs_runner_up
  const tossUp = recommendation.decision_status === 'toss_up'
  const nextPick = leader.next_turn_pick_no ?? recommendation.next_user_pick_no ?? null
  const rows = [...recommendation.candidates, ...(recommendation.screened_candidates ?? [])]
  const candidateName = (candidateId: string) =>
    rows.find((candidate) => candidate.player_id === candidateId)?.name ?? candidateId
  const survivalRoot = leader.survival_branch_root_candidate_id
  const opportunityRoot = leader.opportunity_evidence_branch_root_candidate_id
  const usualAlternative = leader.later_alternatives?.[0]
  const adpDrift =
    leader.adp != null && currentPickNo != null ? currentPickNo - leader.adp : null
  const reasons: Array<{ label: string; text: string }> = []
  if (!tossUp && delta) {
    const pairedCandidate = candidateName(delta.candidate_id)
    const baselineCandidate = candidateName(delta.baseline_candidate_id)
    reasons.push({
      label: 'Paired expected value',
      text:
        `Across ${recommendation.rollout_count} paired simulated rest-of-drafts, taking ${pairedCandidate} instead of ${baselineCandidate} changes ` +
        `risk-neutral expected projected completed-roster value by ${delta.projected_value_delta >= 0 ? '+' : ''}${delta.projected_value_delta.toFixed(1)} points ` +
        `(paired interval ${delta.interval[0].toFixed(1)} to ${delta.interval[1].toFixed(1)}). ${pairedCandidate} is higher in ` +
        `${(delta.better_continuation_probability * 100).toFixed(0)}%, tied in ${(delta.tied_continuation_probability * 100).toFixed(0)}%, ` +
        `and lower in ${(delta.worse_continuation_probability * 100).toFixed(0)}% of continuations.`,
    })
  }
  if (tossUp) {
    reasons.push({
      label: 'Practical toss-up',
      text: `These candidates are a practical toss-up under the ${recommendation.practical_tie_points.toFixed(1)}-point gate. ${tieBreakText(recommendation.headline_tie_break_basis, leader.name)}`,
    })
  }
  if (
    survivalRoot &&
    nextPick != null &&
    leader.target_available_count != null &&
    leader.target_rollout_count != null
  ) {
    const selection =
      leader.target_selected_when_available_count != null && leader.target_available_count > 0
        ? ` The future-user policy selects ${leader.name} in ${leader.target_selected_when_available_count}/${leader.target_available_count} continuations where it is available.`
        : ''
    reasons.push({
      label: 'Alternative-root availability',
      text:
        `Under the branch rooted at taking ${candidateName(survivalRoot)}, ${leader.name} is available at pick ${nextPick} in ` +
        `${leader.target_available_count}/${leader.target_rollout_count} continuations.${selection}`,
    })
  }
  if (opportunityRoot && nextPick != null && leader.effective_tie_break_urgency != null) {
    const marginal =
      leader.current_marginal_value != null && leader.expected_best_later_value != null
        ? ` Current marginal value is ${leader.current_marginal_value.toFixed(1)} points and expected best marginal value at pick ${nextPick} is ${leader.expected_best_later_value.toFixed(1)} points.`
        : ''
    const alternative = usualAlternative
      ? ` The most common local later alternative is ${usualAlternative.name} (${(usualAlternative.probability * 100).toFixed(0)}%).`
      : ''
    reasons.push({
      label: 'Candidate-root opportunity',
      text:
        `This is ${candidateName(opportunityRoot)}-root local opportunity evidence, not the paired alternative-root comparison.${marginal} ` +
        `Effective tie-break urgency is ${leader.effective_tie_break_urgency.toFixed(1)} points.${alternative}`,
    })
  }
  if (
    opportunityRoot &&
    leader.positional_value_drop != null &&
    leader.positional_value_drop > 1 &&
    nextPick != null
  ) {
    reasons.push({
      label: `${leader.position ?? 'Position'} cliff`,
      text:
        `In ${candidateName(opportunityRoot)}-root local opportunity evidence, same-position value falls ` +
        `${leader.positional_value_drop.toFixed(0)} points by pick ${nextPick}; this is not a requirement to draft ${leader.position} then.`,
    })
  }
  if (adpDrift != null && Math.abs(adpDrift) >= 5) {
    reasons.push(
      adpDrift > 0
        ? {
            label: 'Market ADP',
            text: `Market ADP is a draft-position proxy, not trade value. ${leader.name} usually goes around pick ${leader.adp!.toFixed(0)} and has fallen ${adpDrift.toFixed(0)} picks.`,
          }
        : {
            label: 'Ahead of market',
            text: `Market ADP is a draft-position proxy, not trade value. This is ${Math.abs(adpDrift).toFixed(0)} picks before ${leader.name}'s ADP of ${leader.adp!.toFixed(0)}.`,
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
        Projected roster value is deterministic best-legal-lineup points over replacement plus
        positive bench value discounted by a {recommendation.bench_asset_factor.toFixed(2)} factor;
        comparisons simulate complete rest-of-drafts, not just this pick.
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
                  <strong>
                    Practical toss-up under the{' '}
                    {monitor.recommendation?.practical_tie_points.toFixed(1)}-point gate.
                  </strong>{' '}
                  {coLeaderNames.join(', ')} form the top tier.{' '}
                  {leader && monitor.recommendation &&
                    tieBreakText(monitor.recommendation.headline_tie_break_basis, leader.name)}
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
                  const survivalRootName = candidate.survival_branch_root_candidate_id
                    ? candidates.find(
                        (row) => row.player_id === candidate.survival_branch_root_candidate_id,
                      )?.name ?? candidate.survival_branch_root_candidate_id
                    : null
                  const opportunityRootName = candidate.opportunity_evidence_branch_root_candidate_id
                    ? candidates.find(
                        (row) =>
                          row.player_id === candidate.opportunity_evidence_branch_root_candidate_id,
                      )?.name ?? candidate.opportunity_evidence_branch_root_candidate_id
                    : null
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
                          <small>ADP {candidate.adp.toFixed(0)}</small>
                        )}
                        {candidate.target_available_count != null &&
                          candidate.target_rollout_count != null &&
                          survivalRootName &&
                          (candidate.next_turn_pick_no ??
                            monitor.recommendation?.next_user_pick_no) != null && (
                            <small>
                              Available {candidate.target_available_count}/{candidate.target_rollout_count} at pick{' '}
                              {candidate.next_turn_pick_no ??
                                monitor.recommendation?.next_user_pick_no} under {survivalRootName}-root
                            </small>
                        )}
                        {candidate.current_marginal_value != null &&
                          candidate.expected_best_later_value != null &&
                          opportunityRootName &&
                          candidate.next_turn_pick_no != null && (
                            <small>
                              {opportunityRootName}-root local opportunity evidence ·{' '}
                              {candidate.current_marginal_value.toFixed(0)} current marginal ·{' '}
                              {candidate.expected_best_later_value.toFixed(0)} expected best at pick{' '}
                              {candidate.next_turn_pick_no}
                              {candidate.positional_value_drop != null && (
                                <> · {candidate.positional_value_drop >= 0 ? '+' : ''}
                                  {candidate.positional_value_drop.toFixed(0)} {candidate.position} drop</>
                              )}
                              {candidate.later_alternatives?.[0] && (
                                <> · common local later alternative {candidate.later_alternatives[0].name}{' '}
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
                                {candidate.effective_tie_break_urgency != null && (
                                  <> · urgency {candidate.effective_tie_break_urgency >= 0 ? '+' : ''}
                                    {candidate.effective_tie_break_urgency.toFixed(1)}</>
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
                                ? candidate.effective_tie_break_urgency != null
                                  ? `urgency ${candidate.effective_tie_break_urgency >= 0 ? '+' : ''}${candidate.effective_tie_break_urgency.toFixed(1)}`
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
                for pick {monitor.recommendation?.pick_no} · projected roster value is deterministic
                best-legal-lineup points over replacement plus positive bench value discounted by a{' '}
                {monitor.recommendation?.bench_asset_factor.toFixed(2)} factor, ± vs the top option ·
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
                .
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
