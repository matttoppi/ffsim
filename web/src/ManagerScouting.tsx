import { useCallback, useEffect, useState } from 'react'
import { getManagerScouting, type ManagerScoutingReport } from './api'

const RB_SHAPE_LABEL: Record<string, string> = {
  zero_rb: 'Zero-RB',
  hero_rb: 'Hero-RB',
  heavy_rb: 'RB-heavy',
}

function topWeightedKey(weights: Record<string, number>): string | null {
  let best: string | null = null
  for (const [key, weight] of Object.entries(weights)) {
    if (best === null || weight > weights[best]) best = key
  }
  return best
}

export function ManagerScouting() {
  const [report, setReport] = useState<ManagerScoutingReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(
    () =>
      getManagerScouting().then(
        (value) => {
          setReport(value)
          setError(null)
        },
        (cause) => {
          setError(cause instanceof Error ? cause.message : 'Manager scouting failed')
        },
      ),
    [],
  )

  useEffect(() => {
    void load()
  }, [load])

  if (error) {
    return (
      <section className="panel" aria-label="League scouting">
        <p className="eyebrow">League scouting</p>
        <p className="form-error" role="alert">{error}</p>
        <button type="button" className="button-ghost" onClick={() => void load()}>
          Retry
        </button>
      </section>
    )
  }
  if (!report) {
    return (
      <section className="panel" aria-label="League scouting">
        <p className="eyebrow">League scouting</p>
        <p className="controls-hint" role="status">Loading manager history…</p>
      </section>
    )
  }

  const context = report.target_context
  return (
    <section className="panel" aria-label="League scouting">
      <header className="scout-header">
        <div>
          <p className="eyebrow">League scouting</p>
          <h2>Manager draft history</h2>
        </div>
        <p className="scout-context">
          Target: {context.season} · {context.team_count}-team ·{' '}
          {context.scoring_type ?? 'unknown scoring'} ·{' '}
          {report.observation_count.toLocaleString()} historical picks
        </p>
      </header>
      <p className="scout-note">
        Descriptive history only — the live opponent model stays population-based;
        manager personalization is not decision-eligible.
      </p>
      <div className="scout-grid">
        {report.managers.map((manager) => {
          const history = manager.history
          const qb = history?.qb_te_timing?.QB
          const te = history?.qb_te_timing?.TE
          const starts = history?.four_round_starts
          const shape = starts && starts.sample_size > 0
            ? topWeightedKey(starts.weighted_rb_shape)
            : null
          const topPositions = history
            ? Object.entries(history.position_picks)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 3)
            : []
          return (
            <article className="scout-card" key={manager.roster_id ?? manager.display_name}>
              <header>
                <span className="scout-slot">
                  {manager.draft_slot != null ? `#${manager.draft_slot}` : '—'}
                </span>
                <div className="scout-name">
                  <strong>{manager.display_name}</strong>
                  {manager.team_name && <small>{manager.team_name}</small>}
                </div>
              </header>
              {history ? (
                <dl>
                  <div>
                    <dt>History depth</dt>
                    <dd>
                      {history.draft_count} drafts · {history.pick_count} picks ·
                      weight {history.weighted_draft_count.toFixed(1)}
                    </dd>
                  </div>
                  {qb && qb.selected_drafts > 0 && (
                    <div>
                      <dt>First QB</dt>
                      <dd>
                        usually R{topWeightedKey(qb.weighted_first_rounds) ?? '—'} ·
                        drafted one in {qb.selected_drafts}/
                        {qb.selected_drafts + qb.not_selected_drafts} drafts
                      </dd>
                    </div>
                  )}
                  {te && te.selected_drafts > 0 && (
                    <div>
                      <dt>First TE</dt>
                      <dd>
                        usually R{topWeightedKey(te.weighted_first_rounds) ?? '—'} ·
                        drafted one in {te.selected_drafts}/
                        {te.selected_drafts + te.not_selected_drafts} drafts
                      </dd>
                    </div>
                  )}
                  {starts && starts.sample_size > 0 && (
                    <div>
                      <dt>First four rounds</dt>
                      <dd>
                        {shape ? RB_SHAPE_LABEL[shape] ?? shape : '—'} starts ·
                        WR-heavy in {starts.wr_heavy}/{starts.sample_size}
                      </dd>
                    </div>
                  )}
                  {topPositions.length > 0 && (
                    <div>
                      <dt>Most drafted</dt>
                      <dd>
                        {topPositions
                          .map(([position, count]) => `${position} ${count}`)
                          .join(' · ')}
                      </dd>
                    </div>
                  )}
                </dl>
              ) : (
                <p className="scout-empty">
                  No eligible draft history — the population model covers this manager.
                </p>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}
