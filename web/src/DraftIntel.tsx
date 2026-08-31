import { useEffect, useRef, useState, type FormEvent } from 'react'
import { BoostChip, ProjectionBoard } from './ProjectionBoard'
import { PositionOutlook } from './PositionOutlook'
import {
  getDraftAlphaShadowAudit,
  getDraftMonitor,
  getDraftPreparation,
  prepareDraft,
  simulateCompletedDraft,
  startDraftMonitor,
  stopDraftMonitor,
  type DraftAlphaShadowAudit,
  type DraftLeagueSimulation,
  type DraftMonitor,
  type DraftPreparation,
  type DraftRecommendationCandidate,
  type WorkProgress,
} from './api'

const POLL_MS = 500

const SKILL_POSITIONS = ['RB', 'WR', 'TE']
const KNOWN_POSITIONS = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']
const REC_STEPS = ['Queued', 'First board', 'Screening field', 'Refining finalists', 'Final suggestion']
const REC_PHASE: Record<string, number> = { pending: 0, calculating: 1, expanding: 2, refining: 3 }
const ALPHA_TIMING_LABEL = {
  safe_to_wait: 'likely back',
  urgent: 'unlikely back',
  uncertain: 'live decision',
  outside_model: 'outside model',
} as const

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

export function AlphaShadowPanel({
  monitor,
  currentPickNo,
  audit,
}: {
  monitor: DraftMonitor
  currentPickNo: number | null
  audit?: DraftAlphaShadowAudit | null
}) {
  const status = monitor.alpha_shadow_status ?? 'disabled'
  const shadow = monitor.alpha_shadow
  const current = shadow?.pick_no === currentPickNo
  if (status !== 'ready' || !shadow || !current) {
    const message =
      status === 'pending'
        ? 'Computing return lanes and the manager shadow…'
        : status === 'stale'
          ? 'The draft advanced. Waiting for the current pick’s shadow.'
          : status === 'failed'
            ? `Shadow failed: ${monitor.alpha_shadow_error ?? 'unknown error'}`
            : status === 'disabled'
              ? `Shadow unavailable${monitor.alpha_shadow_error ? `: ${monitor.alpha_shadow_error}` : '.'}`
              : 'Shadow evidence runs after the final terminal suggestion.'
    return (
      <aside className={`alpha-shadow is-${status}`} aria-label="Draft alpha shadow">
        <div className="alpha-shadow-header">
          <div>
            <p className="eyebrow">Draft alpha</p>
            <h4>Return odds · experimental</h4>
          </div>
          <span className="alpha-shadow-chip">Evidence only — never changes the pick</span>
        </div>
        <p className="alpha-shadow-message" role="status">{message}</p>
      </aside>
    )
  }

  const measured = shadow.candidates.slice(0, 6)
  const manager = shadow.manager_shadow
  const managerAgrees =
    manager.status === 'ready' && manager.shadow_leader_in_terminal_practical_tier
  const nextTurn = shadow.recommended_branch_next_turn
    .filter((player) => player.eligible_next_turn)
    .slice(0, 3)


  return (
    <aside className="alpha-shadow is-ready" aria-label="Draft alpha shadow">
      <div className="alpha-shadow-header">
        <div>
          <p className="eyebrow">Draft alpha</p>
          <h4>Return odds · experimental</h4>
        </div>
        <span className="alpha-shadow-chip">Evidence only — never changes the pick</span>
      </div>
      <p className="alpha-shadow-manager">
        <strong>10% manager lens:</strong>{' '}
        {manager.status !== 'ready'
          ? 'unavailable'
          : managerAgrees
            ? 'inside the terminal practical tier'
            : 'disagrees — logged only'}
        {' · '}
        {shadow.manager_support.supported_rosters}/{shadow.manager_support.total_opponent_rosters}{' '}
        opponents personalized
      </p>
      <ol className="alpha-shadow-list">
        {measured.map((candidate) => (
          <li
            key={candidate.player_id}
            className={`is-${candidate.timing_label}`}
          >
            <span className={`pos-badge pos-${candidate.position ?? 'NA'}`}>
              {candidate.position ?? '—'}
            </span>
            <span className="alpha-shadow-player">
              <strong>{candidate.name}</strong>
              <small>
                #{candidate.engine_rank} terminal · market {candidate.market_rank ?? '—'} ·{' '}
                {ALPHA_TIMING_LABEL[candidate.timing_label]}
              </small>
            </span>
            <span className="alpha-shadow-probability">
              <strong>
                {candidate.return_probability == null
                  ? '—'
                  : `${Math.round(candidate.return_probability * 100)}%`}
              </strong>
              <small>
                {candidate.return_interval_95
                  ? `${Math.round(candidate.return_interval_95[0] * 100)}–${Math.round(
                      candidate.return_interval_95[1] * 100,
                    )}%`
                  : 'not measured'}
              </small>
            </span>
          </li>
        ))}
      </ol>
      {nextTurn.length > 0 && (
        <p className="alpha-shadow-next">
          <strong>After taking the terminal leader:</strong>{' '}
          {nextTurn.map((player) => (
            <span key={player.player_id}>
              #{player.market_rank} {player.position}{' '}
              {player.return_probability == null
                ? '—'
                : `${Math.round(player.return_probability * 100)}%`}
            </span>
          ))}
        </p>
      )}
      {audit && (
        <dl className="alpha-shadow-audit">
          <div>
            <dt>Observed states</dt>
            <dd>{audit.metrics.ready_states}</dd>
          </div>
          <div>
            <dt>p95 latency</dt>
            <dd>
              {audit.metrics.duration_seconds.p95 == null
                ? '—'
                : `${audit.metrics.duration_seconds.p95.toFixed(1)}s`}
            </dd>
          </div>
          <div>
            <dt>Tier retained</dt>
            <dd>
              {audit.metrics.manager_practical_retention_rate == null
                ? '—'
                : `${Math.round(audit.metrics.manager_practical_retention_rate * 100)}%`}
            </dd>
          </div>
          <div>
            <dt>Live gate</dt>
            <dd>{audit.live_evidence_gate.passes ? 'Passed' : 'Collecting'}</dd>
          </div>
        </dl>
      )}
      <small className="alpha-shadow-footnote">
        Historical return evidence and a {manager.rollouts ?? 0}-rollout manager shadow.
        Neither changes the recommendation.
      </small>
    </aside>
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

export function DraftIntel({
  currentDraftId,
  onOpenRanks,
}: {
  currentDraftId: string | null
  onOpenRanks?: () => void
}) {
  const [draftId, setDraftId] = useState(currentDraftId ?? '')
  const [mockDraftId, setMockDraftId] = useState('')
  const [username, setUsername] = useState('')
  const [preparation, setPreparation] = useState<DraftPreparation>({ status: 'idle' })
  const [monitor, setMonitor] = useState<DraftMonitor>({ status: 'idle' })
  const [error, setError] = useState<string | null>(null)
  const [positionFilter, setPositionFilter] = useState<string | null>(null)
  const [simulation, setSimulation] = useState<DraftLeagueSimulation | null>(null)
  const [simulating, setSimulating] = useState(false)
  const [alphaAudit, setAlphaAudit] = useState<DraftAlphaShadowAudit | null>(null)
  const [liveView, setLiveView] = useState<'board' | 'sim'>('board')
  const [setupOpen, setSetupOpen] = useState(true)
  const [lastSyncAt, setLastSyncAt] = useState<number | null>(null)
  const [forceRefresh, setForceRefresh] = useState(false)

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

  // Reuse previous object references for unchanged payload sections so
  // memoized children skip re-rendering, and skip the state update entirely
  // when only the sync clock moved — the monitor payload is large and
  // replacing it twice a second re-rendered every table between picks.
  const monitorRef = useRef<DraftMonitor | null>(null)
  const monitorPartsRef = useRef<Record<string, [string, unknown]>>({})
  const stabilizeMonitor = (next: DraftMonitor): DraftMonitor => {
    const previous = monitorRef.current
    const nextRecord = next as unknown as Record<string, unknown>
    const stable: Record<string, unknown> = { ...nextRecord }
    const parts = monitorPartsRef.current
    for (const key of [
      'state',
      'recommendation',
      'projection_board',
      'league_equity',
      'alpha_shadow',
      'recommendation_progress',
      'league_equity_progress',
    ]) {
      const serialized = JSON.stringify(nextRecord[key] ?? null)
      const cached = parts[key]
      if (cached && cached[0] === serialized) {
        stable[key] = cached[1]
      } else {
        parts[key] = [serialized, nextRecord[key]]
      }
    }
    const previousRecord = previous as unknown as Record<string, unknown> | null
    if (
      previousRecord &&
      Object.keys(stable).every(
        (key) =>
          key === 'last_sync_at' ||
          key === 'sync_count' ||
          stable[key] === previousRecord[key],
      ) &&
      Object.keys(previousRecord).length === Object.keys(stable).length
    ) {
      return previous as DraftMonitor
    }
    const result = stable as unknown as DraftMonitor
    monitorRef.current = result
    return result
  }

  useEffect(() => {
    if (!['starting', 'running'].includes(monitor.status)) return
    const timer = window.setInterval(() => {
      void getDraftMonitor().then(
        (value) => {
          setLastSyncAt(value.last_sync_at ?? null)
          setMonitor(stabilizeMonitor(value))
          setError(null)
        },
        (cause) => {
          setError(cause instanceof Error ? cause.message : 'Monitor status failed')
        },
      )
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [monitor.status])

  useEffect(() => {
    if ((monitor.alpha_shadow_calculation_count ?? 0) < 1) return
    void getDraftAlphaShadowAudit().then(setAlphaAudit, () => {})
  }, [monitor.alpha_shadow_calculation_count])

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
          ...(forceRefresh ? { force_refresh: true } : {}),
        }),
      )
      setMonitor({ status: 'idle' })
      setSimulation(null)
      setAlphaAudit(null)
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
  useEffect(() => {
    if (monitoring) setSetupOpen(false)
  }, [monitoring])
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
  const filterPositions =
    positionFilter === 'SKILL'
      ? new Set(SKILL_POSITIONS)
      : positionFilter
        ? new Set([positionFilter])
        : null
  const positionPool = new Set([
    ...candidates.flatMap((c) => (c.position ? [c.position] : [])),
    ...(monitor.projection_board?.points_players ?? []).map((p) => p.position),
  ])
  const positions = KNOWN_POSITIONS
    .filter((position) => positionPool.has(position))
    .concat(
      [...positionPool].filter((position) => !KNOWN_POSITIONS.includes(position)),
    )
  const hasSkill = positions.some((position) => SKILL_POSITIONS.includes(position))
  const visibleFinalists = filterPositions
    ? finalists.filter(
        (c) => c.position != null && filterPositions.has(c.position),
      )
    : finalists
  const visibleScreened = filterPositions
    ? screenedCandidates.filter(
        (c) => c.position != null && filterPositions.has(c.position),
      )
    : screenedCandidates
  const visibleCandidates = [...visibleFinalists, ...visibleScreened]
  const boardSections = [
    {
      label: recStatus === 'expanding' ? 'Current screen' : 'Refined contenders',
      candidates: visibleFinalists,
      screened: false,
    },
    {
      label: 'Rough early estimates · not ranked with contenders',
      candidates: visibleScreened,
      screened: true,
    },
  ].filter((section) => section.candidates.length > 0)
  const leader = finalists[0] ?? candidates[0]
  const positionTiming = recommendationCurrent
    ? (monitor.recommendation?.position_timing ?? [])
    : []
  // Keep the last board mounted while the next pick's board computes; the
  // header shows an updating chip instead of blanking the whole tab.
  const projectionBoard = monitor.projection_board ?? null
  const projectionCurrent =
    projectionBoard?.pick_no != null && projectionBoard.pick_no === currentPickNo
  const leaderEdge =
    monitor.recommendation?.paired_value_delta_vs_runner_up?.projected_value_delta
  const tossUp = monitor.recommendation?.decision_status === 'toss_up'
  const coLeaderIds = new Set(monitor.recommendation?.co_leader_candidate_ids ?? [])
  const coLeaderNames = candidates.flatMap((candidate) =>
    coLeaderIds.has(candidate.player_id) ? [candidate.name] : [],
  )
  const orderSymmetricIds = new Set(
    monitor.recommendation?.order_symmetric_candidate_ids ?? [],
  )
  const orderSymmetricNames = candidates.flatMap((candidate) =>
    orderSymmetricIds.has(candidate.player_id) ? [candidate.name] : [],
  )
  // Every non-headline co-leader completes to the exact same final roster
  // in either take order — the "co-leader" is a later pick shown early.
  const orderSymmetricTier =
    tossUp &&
    orderSymmetricNames.length > 0 &&
    coLeaderIds.size === orderSymmetricIds.size + 1
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
  const lastSync = lastSyncAt ? new Date(lastSyncAt * 1000).toLocaleTimeString() : null
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

  const simEngine = (monitor.recommendation_mode ?? 'simulation') === 'simulation'
  const railHasContent = simEngine || simulation != null || feed.length > 0

  return (
    <div className="draft-intel">
      {(monitoring || monitor.state) && (
        <section
          className={`panel draft-live${onClock ? ' is-on-clock' : ''}`}
          aria-label="Live draft board"
        >
          <div className="command-strip" role="status">
            <div className="command-pick" aria-hidden="true">
              <span className="command-pick-label">Pick</span>
              <span className="command-pick-no">{currentPickNo ?? '—'}</span>
            </div>
            <div className="command-state">
              <p className="eyebrow">{onClock ? 'Your pick' : 'Live draft'}</p>
              <h3>{heading}</h3>
              {lastSync && (
                <p className="sync-meta">
                  Synced {lastSync} · {monitor.state?.completed_picks ?? 0} picks in
                </p>
              )}
            </div>
            {simEngine && leader && recommendationCurrent && (
              <div className="command-rec">
                <p className="command-rec-label">
                  {tossUp
                    ? orderSymmetricTier
                      ? 'Either order — same final roster'
                      : 'Top tier — take either'
                    : 'Draft'}
                </p>
                <p className="command-rec-player">
                  <span className={`pos-badge pos-${leader.position ?? 'NA'}`}>
                    {leader.position ?? '—'}
                  </span>
                  <strong>{leader.name}</strong>
                </p>
                <p className="command-rec-meta">
                  {leader.projected_roster_value.toFixed(1)} pts
                  {!tossUp && leaderEdge != null && leaderEdge >= 0.05 && (
                    <> · +{leaderEdge.toFixed(1)} vs next</>
                  )}
                  {' · '}
                  {recStatus === 'ready'
                    ? 'final'
                    : recStatus === 'expanding'
                      ? 'provisional — first board'
                      : 'refining…'}
                </p>
                {(() => {
                  const pairPlan = monitor.recommendation?.pair_plan
                  const companion = pairPlan?.companions[0]
                  if (!pairPlan || !companion) return null
                  return (
                    <p className="command-rec-meta">
                      then {companion.name} at pick {pairPlan.next_pick_no} (
                      {(companion.share * 100).toFixed(0)}% of sims)
                    </p>
                  )
                })()}
              </div>
            )}
            {!(simEngine && leader && recommendationCurrent) && projectionBoard && (() => {
              const plan = projectionBoard.plans.find(
                (row) => row.player_id === projectionBoard.recommended_player_id,
              )
              if (!plan) return null
              return (
                <div className="command-rec is-projection">
                  <p className="command-rec-label">Current-turn plan</p>
                  <p className="command-rec-player">
                    <span className={`pos-badge pos-${plan.position}`}>{plan.position}</span>
                    <strong>{plan.name}</strong>
                  </p>
                  <p className="command-rec-meta">
                    {plan.route_value.toFixed(1)} approx route value · no simulation
                  </p>
                </div>
              )
            })()}
            {monitor.state && (
              <dl className="clock-facts">
                <div><dt>Your next</dt><dd>{monitor.state.user_next_pick_no ?? '—'}</dd></div>
                <div><dt>Until you</dt><dd>{monitor.state.opponent_picks_until_next ?? '—'}</dd></div>
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
          <div className={`draft-live-body${railHasContent ? '' : ' is-solo'}`}>
            <div className="draft-live-main">
          {positions.length > 0 && (
            <div className="pos-filter" role="group" aria-label="Filter players by position">
              <button
                type="button"
                className={`pos-chip${positionFilter === null ? ' is-active' : ''}`}
                onClick={() => setPositionFilter(null)}
              >
                All
              </button>
              {hasSkill && (
                <button
                  type="button"
                  className={`pos-chip${positionFilter === 'SKILL' ? ' is-active' : ''}`}
                  onClick={() => setPositionFilter('SKILL')}
                >
                  Skill · RB/WR/TE
                </button>
              )}
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
          <div className="live-tabs" role="tablist" aria-label="Draft intelligence views">
            <button
              id="live-board-tab"
              type="button"
              role="tab"
              aria-selected={liveView === 'board'}
              aria-controls="live-board-view"
              onClick={() => setLiveView('board')}
            >
              Live board
            </button>
            <button
              id="live-sim-tab"
              type="button"
              role="tab"
              aria-selected={liveView === 'sim'}
              aria-controls="live-sim-view"
              onClick={() => setLiveView('sim')}
            >
              Simulation advice
              {simEngine && recStatus === 'ready' && recommendationCurrent ? ' ✓' : ''}
            </button>
          </div>
          <div
            id="live-sim-view"
            role="tabpanel"
            aria-labelledby="live-sim-tab"
            hidden={liveView !== 'sim'}
          >
          <section className="engine-section" aria-label="Simulation pick advice">
            <p className="engine-note">
              Simulates the rest of the draft in the background and ranks picks by
              completed-roster value. The championship odds and experimental evidence
              on the right belong to this view.
            </p>
          {!simEngine && (
            <p className="controls-hint">
              This monitoring session was started without the simulation engine.
              Stop and start monitoring to enable pick advice.
            </p>
          )}
          {simEngine && monitoring && monitor.state && (
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
          {simEngine && monitoring &&
            monitor.recommendation_discarded_pick_no != null &&
            !recommendationCurrent && (
              <p className="controls-hint" role="status">
                Pick {monitor.recommendation_discarded_pick_no} result discarded — the draft
                advanced.
              </p>
            )}
          {simEngine && candidates.length > 0 && (
            <>
              {tossUp && (
                <p className="controls-hint" role="status">
                  <strong>
                    Practical toss-up under the{' '}
                    {monitor.recommendation?.practical_tie_points.toFixed(1)}-point gate.
                  </strong>{' '}
                  {coLeaderNames.join(', ')} form the top tier.{' '}
                  {orderSymmetricNames.length > 0 && (
                    <>
                      Taking {orderSymmetricNames.join(' or ')} now or at your
                      next pick builds the exact same final roster — order does
                      not matter; the scarcer player is listed first.{' '}
                    </>
                  )}
                  {leader && monitor.recommendation &&
                    tieBreakText(monitor.recommendation.headline_tie_break_basis, leader.name)}
                </p>
              )}
              {visibleCandidates.length === 0 && (
                <p className="controls-hint">
                  No {positionFilter === 'SKILL' ? 'skill players' : positionFilter} among
                  the evaluated candidates for this pick.
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
                    <div className="board-head" aria-hidden="true">
                      <span>#</span>
                      <span>Pos</span>
                      <span>Player · evidence</span>
                      <span>Proj roster value</span>
                    </div>
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
                      <div className="board-player">
                        <strong>{candidate.name}</strong>
                        <small>
                          title {(candidate.championship_probability * 100).toFixed(1)}% ·{' '}
                          {(candidate.playoff_probability * 100).toFixed(0)}% playoffs ·{' '}
                          {candidate.expected_wins.toFixed(1)} wins
                          {candidate.adp != null && <> · ADP {candidate.adp.toFixed(0)}</>}
                        </small>
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
                            <details className="board-evidence">
                              <summary>Opportunity evidence</summary>
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
                            </details>
                          )}
                      </div>
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
                            <strong className="board-delta">rough est.</strong>
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
                        {!!candidate.personal_offset &&
                          candidate.preference_adjusted_value != null &&
                          Math.abs(
                            candidate.preference_adjusted_value -
                              candidate.projected_roster_value,
                          ) >= 0.05 && (
                            <small className="board-yours">
                              yours {candidate.preference_adjusted_value.toFixed(1)}
                              <BoostChip offset={candidate.personal_offset} />
                            </small>
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
                for pick {monitor.recommendation?.pick_no} ·{' '}
                {monitor.recommendation?.rollout_count} draft continuations
                {screenedCandidates.length > 0 ? ' for finalists' : ''}.
              </p>
              {monitor.recommendation?.run_signature && (
                <details className="run-details">
                  <summary>Run details</summary>
                  <p className="board-footnote">
                    run {monitor.recommendation.run_signature.slice(0, 12)} · seed{' '}
                    {monitor.recommendation.seed} · engine v
                    {monitor.recommendation.decision_engine_version} · world{' '}
                    {monitor.recommendation.world_bank_version.slice(0, 8)} · model{' '}
                    {monitor.recommendation.draft_model_version} · uncalibrated Sleeper-ADP
                    baseline.
                  </p>
                </details>
              )}
              {positionTiming.length > 0 && (
                <div className="pick-feed position-timing">
                  <h4>
                    When to draft QB / TE · market timing
                    <span className="market-chip">market view · your boosts excluded</span>
                  </h4>
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
                    ADP order only · next three turns · the ranked advice above stays
                    authoritative.
                  </p>
                </div>
              )}
            </>
          )}
          </section>
          </div>
          <div
            id="live-board-view"
            role="tabpanel"
            aria-labelledby="live-board-tab"
            hidden={liveView !== 'board'}
          >
          <section className="engine-section" aria-label="Projection board">
            <p className="engine-note">
              Pure projection math — no simulation. Updates after every synced pick,
              including other managers' picks.
              {projectionBoard && !projectionCurrent && (
                <span className="updating-chip" role="status">
                  <span className="spinner" aria-hidden="true" /> updating for pick{' '}
                  {currentPickNo ?? '—'}
                </span>
              )}
            </p>
            {projectionBoard ? (
              <>
                {projectionBoard.position_outlook &&
                  projectionBoard.position_outlook.positions.length > 0 && (
                    <PositionOutlook
                      outlook={projectionBoard.position_outlook}
                      positionFilter={positionFilter}
                    />
                  )}
                <ProjectionBoard
                  board={projectionBoard}
                  positionFilter={positionFilter}
                  onPositionFilterChange={setPositionFilter}
                />
              </>
            ) : monitor.projection_board_error ? (
              <p className="form-error" role="alert">
                Projection board failed: {monitor.projection_board_error}
              </p>
            ) : (
              <p className="controls-hint" role="status">
                Updating the board for pick {currentPickNo ?? '—'}…
              </p>
            )}
          </section>
          </div>
          <details className="metric-glossary">
            <summary>What the metrics mean</summary>
            <dl>
              <div>
                <dt>Cost of waiting (positional falloff)</dt>
                <dd>
                  Projection board only: the first-seat marginal roster value of the
                  best player at a position now, minus the projected best remaining at
                  your next turn under deterministic ADP-order availability. Positive
                  means waiting costs value at that position. Not a survival
                  probability.
                </dd>
              </div>
              <div>
                <dt>Your boosts</dt>
                <dd>
                  Personal point offsets from My ranks: boost (+) or fade (−) a
                  player&apos;s projected season points. Included in both projection
                  board views and in the simulation advice ranking (shown as
                  &ldquo;yours&rdquo; next to the raw number). Ignored on purpose by
                  the market views: positional falloff and QB / TE market timing.
                </dd>
              </div>
              <div>
                <dt>Projected roster value</dt>
                <dd>
                  Deterministic best-legal-lineup points over replacement plus positive
                  bench value discounted by the bench factor, averaged across simulated
                  complete rest-of-drafts. The authoritative ranking.
                </dd>
              </div>
              <div>
                <dt>Title / playoff odds</dt>
                <dd>
                  Championship and playoff probabilities from the same simulations.
                  Secondary telemetry on an uncalibrated baseline.
                </dd>
              </div>
              <div>
                <dt>VORP</dt>
                <dd>
                  Value over replacement player: projected season points above the
                  league-wide starter replacement cutline.
                </dd>
              </div>
              <div>
                <dt>Roster value (board column)</dt>
                <dd>
                  What this player adds to your current starting lineup:
                  availability-adjusted weekly points above the streamer cutline
                  at his position, plus your boost or fade. 0.0 means no value
                  above streaming after availability and your adjustment — a
                  fade can floor a modest positive to zero, and a boost can
                  lift a streamer-level player above it. In a 1-QB league most
                  QBs sit at 0.0 on purpose. Projection ranks the points;
                  roster value ranks what your lineup keeps over the wire.
                </dd>
              </div>
              <div>
                <dt>WORP</dt>
                <dd>
                  Wins over replacement player: VORP converted to expected wins with the
                  approved calibration curve for this exact league format; shown only
                  when that context is validated.
                </dd>
              </div>
              <div>
                <dt>Opportunity / urgency</dt>
                <dd>
                  Candidate-root evidence (VONA-style): current marginal value versus the
                  expected best marginal value at your next pick. Explains timing and
                  breaks practical ties; it never ranks picks.
                </dd>
              </div>
              <div>
                <dt>Route value</dt>
                <dd>
                  Projection board only: current roster value plus approximate later
                  value through your next pick using ADP opponent-choice lookahead. Not
                  a full expected-value distribution.
                </dd>
              </div>
              <div>
                <dt>ADP</dt>
                <dd>
                  Market average draft position — a draft-position proxy, not trade
                  value.
                </dd>
              </div>
              <div>
                <dt>Available x/y at pick N</dt>
                <dd>
                  How many simulated continuations, rooted at the named alternative
                  pick, still have this player available at your next turn.
                </dd>
              </div>
            </dl>
          </details>
            </div>
            {railHasContent && (
            <aside className="draft-rail">
              <div hidden={liveView !== 'sim'}>
              {(simEngine || simulation) && (
              <section
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
              </section>
              )}
              {simEngine && recStatus === 'ready' && candidates.length > 0 && (
                <AlphaShadowPanel
                  monitor={monitor}
                  currentPickNo={currentPickNo}
                  audit={alphaAudit}
                />
              )}
              </div>
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
            </aside>
            )}
          </div>
        </section>
      )}
      <details
        className="panel setup-panel"
        aria-label="Draft intelligence setup"
        open={setupOpen}
        onToggle={(event) => setSetupOpen(event.currentTarget.open)}
      >
        <summary className="setup-summary">
          <span className="setup-summary-title">
            <span className="eyebrow">Draft intelligence</span>
            <strong>
              Draft setup
              {preparation.league_name ? ` — ${preparation.league_name}` : ''}
            </strong>
          </span>
          <span className={`draft-chip draft-chip-${chip.tone}`}>
            <span className="draft-chip-dot" aria-hidden="true" />
            {chip.label}
          </span>
        </summary>
        <div className="setup-body">

        {!ready && !preparing && !monitoring && (
          <ol className="setup-steps" aria-label="How draft intelligence works">
            <li>
              {onOpenRanks ? (
                <button type="button" className="link-button" onClick={onOpenRanks}>
                  Set your boosts
                </button>
              ) : (
                'Set your boosts'
              )}
              <small>optional · loaded when you prepare</small>
            </li>
            <li>
              Prepare draft
              <small>~1–2 min · projections, worlds, your boosts</small>
            </li>
            <li>
              Start monitoring
              <small>advice updates every pick</small>
            </li>
          </ol>
        )}

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
          <div className="field field-wide">
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={forceRefresh}
                onChange={(event) => setForceRefresh(event.target.checked)}
              />
              Pull the latest FantasyPros data
            </label>
            <p className="field-help">
              Ignores the 12-hour cache and downloads fresh FantasyPros
              projections and ADP now. This is the base data; your boosts and
              all calculations apply on top of it.
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
              <div><dt>Your boosts</dt><dd>{preparation.personal_ranks?.players ?? 0}</dd></div>
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
        </div>
      </details>

    </div>
  )
}
