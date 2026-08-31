import { memo, useState } from 'react'
import type { DraftProjectionBoard } from './api'

const POSITION_ORDER = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']

type OverallPlayer = DraftProjectionBoard['players'][number]

/**
 * Clickable overall-table sorts. ADP ascends (market order); the rest
 * descend. `help` hover text follows ASD-STE100: short active sentences.
 */
const OVERALL_SORTS: Record<
  'projected' | 'vorp' | 'value' | 'adp',
  {
    label: string
    help: string
    direction: 'ascending' | 'descending'
    compare: (a: OverallPlayer, b: OverallPlayer) => number
  }
> = {
  projected: {
    label: 'Projected',
    help:
      'This column shows the projected season points. The value uses the league scoring rules and includes your boost or fade.',
    direction: 'descending',
    compare: (a, b) => b.projected_points - a.projected_points,
  },
  vorp: {
    label: 'VORP',
    help:
      'Value over replacement player. This value is the projected points above the replacement player at the same position.',
    direction: 'descending',
    compare: (a, b) => b.value_over_replacement - a.value_over_replacement,
  },
  value: {
    label: 'Roster value',
    help:
      'This value shows the points this player adds to your starting lineup. The comparison is with a streamed player at the same position. It includes your boost or fade.',
    direction: 'descending',
    compare: (a, b) => b.current_roster_value - a.current_roster_value,
  },
  adp: {
    label: 'ADP',
    help:
      'Average draft position. This value shows where drafts usually select this player. It is not a trade value.',
    direction: 'ascending',
    compare: (a, b) => (a.adp ?? Infinity) - (b.adp ?? Infinity),
  },
}

const WORP_HELP =
  'Wins over replacement player. This value changes VORP into expected wins with the approved curve for this league.'

function signed(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}`
}

/** Compact marker: this number already includes the user's boost or fade. */
export function BoostChip({ offset }: { offset: number }) {
  if (!offset) return null
  return (
    <span
      className={`boost-chip ${offset > 0 ? 'is-boost' : 'is-fade'}`}
      title={`Includes your ${offset > 0 ? 'boost' : 'fade'} of ${offset > 0 ? '+' : '−'}${Math.abs(offset)} points`}
    >
      {offset > 0 ? `+${offset}` : `−${Math.abs(offset)}`}
    </span>
  )
}

/** F8: a lone non-consensus projection among consensus rows is an artifact
 * risk (e.g. a PFF starter-level fallback), not extra signal. */
export function SourceChip({
  source,
  outlier,
}: {
  source?: string | null
  outlier?: boolean
}) {
  if (!outlier || !source) return null
  return (
    <span
      className="source-chip"
      title={`Single-source projection (${source}) — no consensus row backs this number; consider a fade offset before trusting it`}
    >
      {source.toUpperCase()}
    </span>
  )
}

/** Memoized: the monitor poll reuses board references between real changes. */
export const ProjectionBoard = memo(function ProjectionBoard({
  board,
  positionFilter,
  onPositionFilterChange,
}: {
  board: DraftProjectionBoard
  positionFilter: string | null
  onPositionFilterChange: (position: string | null) => void
}) {
  // Owner default (ADR-045 amended): open on value & roster fit.
  const [view, setView] = useState<'points' | 'value'>('value')
  const [overallSort, setOverallSort] = useState<keyof typeof OVERALL_SORTS>('value')
  // Hovered/focused heading explanation, shown above the overall table.
  const [overallHelp, setOverallHelp] = useState<string | null>(null)
  const positions = POSITION_ORDER.filter((position) =>
    board.players.some((player) => player.position === position),
  )
  const filterPositions =
    positionFilter === 'SKILL'
      ? new Set(['RB', 'WR', 'TE'])
      : positionFilter
        ? new Set([positionFilter])
        : null
  const visiblePositions = filterPositions
    ? positions.filter((position) => filterPositions.has(position))
    : positions
  const pointsPositions = POSITION_ORDER.filter((position) =>
    board.points_players.some((player) => player.position === position),
  )
  const visiblePointPositions = filterPositions
    ? pointsPositions.filter((position) => filterPositions.has(position))
    : pointsPositions
  const recommendation = board.plans.find(
    (plan) => plan.player_id === board.recommended_player_id,
  )
  const worpReady = board.worp_calibration.status === 'validated'
  const worpStatus = board.worp_calibration.status.replaceAll('_', ' ')
  const boostedPointsVisible = board.points_players.some(
    (player) =>
      !!player.personal_offset &&
      (!filterPositions || filterPositions.has(player.position)),
  )

  if (view === 'points') {
    return (
      <div className="projection-board projection-points-simple">
        <div className="projection-view-row">
          <span className="projection-view-label" id="points-view-label">Board view</span>
          <div className="projection-view-toggle" role="group" aria-labelledby="points-view-label">
            <button type="button" className="is-active" aria-pressed="true" onClick={() => setView('points')}>
              Points only
            </button>
            <button type="button" aria-pressed="false" onClick={() => setView('value')}>
              Value &amp; roster fit
            </button>
          </div>
        </div>
        <section className="projection-callout" aria-label="FantasyPros projected points">
          <div>
            <p className="eyebrow">
              {boostedPointsVisible ? 'Your projected points' : 'FantasyPros projections'}
            </p>
            <h4>Top remaining players by season points</h4>
            <p>
              {boostedPointsVisible
                ? 'FantasyPros baseline + your adjustments, scored with this league\u2019s settings.'
                : 'Offense uses FantasyPros projections scored with this league\u2019s settings. Kicker and defense use PFF projections.'}
            </p>
          </div>
          <span className="projection-model">2026 points</span>
        </section>
        <div className="projection-position-lists">
          {visiblePointPositions.map((position) => {
            const players = board.points_players.filter(
              (player) => player.position === position,
            )
            if (players.length === 0) return null
            return (
              <section className="projection-position" key={position}>
                <header>
                  <div>
                    <span className={`pos-badge pos-${position}`}>{position}</span>
                    <strong>Top {players.length} remaining</strong>
                  </div>
                  <small>Projected season points</small>
                </header>
                <div className="projection-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">Rank</th>
                        <th scope="col">Player</th>
                        <th scope="col">Projected points</th>
                      </tr>
                    </thead>
                    <tbody>
                      {players.map((player) => (
                        <tr key={player.player_id}>
                          <td>{player.position}{player.position_rank}</td>
                          <th scope="row">
                            {player.name}
                            {player.team && <small>{player.team}</small>}
                            <SourceChip
                              source={player.projection_source}
                              outlier={player.projection_source_outlier}
                            />
                          </th>
                          <td>
                            <strong>{player.projected_points.toFixed(1)}</strong>
                            <BoostChip offset={player.personal_offset} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )
          })}
        </div>
        <p className="board-footnote">
          Points only — no VORP, roster fit, or availability.
        </p>
      </div>
    )
  }

  // One flat cross-position ranking: "who is the next best pick" without
  // opening each position table. The clicked metric sorts first; the fixed
  // roster-value/VORP/projected/ADP/player-id chain keeps every ordering
  // fully deterministic through the 0.0-roster-value tail.
  const primarySort = OVERALL_SORTS[overallSort].compare
  const overallPlayers = board.players
    .filter((player) => !filterPositions || filterPositions.has(player.position))
    .sort(
      (a, b) =>
        primarySort(a, b) ||
        b.current_roster_value - a.current_roster_value ||
        b.value_over_replacement - a.value_over_replacement ||
        b.projected_points - a.projected_points ||
        (a.adp ?? Infinity) - (b.adp ?? Infinity) ||
        a.player_id.localeCompare(b.player_id),
    )
    .slice(0, 40)

  return (
    <div className="projection-board">
      <div className="projection-view-row">
        <span className="projection-view-label" id="value-view-label">Board view</span>
        <div className="projection-view-toggle" role="group" aria-labelledby="value-view-label">
          <button type="button" aria-pressed="false" onClick={() => setView('points')}>
            Points only
          </button>
          <button type="button" className="is-active" aria-pressed="true" onClick={() => setView('value')}>
            Value &amp; roster fit
          </button>
        </div>
      </div>
      <section className="projection-callout" aria-label="Projection recommendation">
        <div>
          <p className="eyebrow">Best pick by projections</p>
          <h4>
            {recommendation
              ? `${recommendation.name} leads the current-turn plan`
              : 'No eligible projected player'}
          </h4>
          {recommendation && (
            <p>
              Route value {recommendation.route_value.toFixed(1)} ≈{' '}
              {recommendation.current_roster_value.toFixed(1)} now
              {board.next_user_pick_no != null
                ? ` + ${recommendation.later_value.toFixed(1)} likely later through pick ${board.next_user_pick_no}`
                : ` + ${recommendation.later_value.toFixed(1)} likely later`}
              .
            </p>
          )}
        </div>
        <span className="projection-model">projection v{board.model_version}</span>
      </section>

      {board.plans.length > 0 && (
        <section className="projection-plans" aria-label="Current position plans">
          {board.plans.map((plan, index) => (
            <button
              key={plan.player_id}
              type="button"
              className={`projection-plan${index === 0 ? ' is-leading' : ''}`}
              onClick={() => onPositionFilterChange(plan.position)}
            >
              <span className={`pos-badge pos-${plan.position}`}>{plan.position}</span>
              <strong>{plan.name}</strong>
              <small>
                {plan.current_roster_value.toFixed(1)} now ·{' '}
                {plan.later_value.toFixed(1)} likely later
              </small>
              <span>{plan.route_value.toFixed(1)}</span>
            </button>
          ))}
        </section>
      )}

      <div className="projection-position-lists">
        {overallPlayers.length > 0 && visiblePositions.length > 1 && (
          <section
            className="projection-position projection-overall"
            aria-label="Overall ranking"
          >
            <header>
              <div>
                <strong>Overall · next best pick</strong>
              </div>
              <small
                className={overallHelp ? 'projection-overall-help' : undefined}
                aria-live="polite"
              >
                {overallHelp ?? (
                  <>
                    Top {overallPlayers.length} across positions · sorted by{' '}
                    {OVERALL_SORTS[overallSort].label} · hover a heading for its
                    meaning
                  </>
                )}
              </small>
            </header>
            <div className="projection-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Rank</th>
                    <th scope="col">Player</th>
                    {(['projected', 'vorp'] as const).map((key) => (
                      <th
                        key={key}
                        scope="col"
                        data-help={OVERALL_SORTS[key].help}
                        aria-sort={overallSort === key ? OVERALL_SORTS[key].direction : undefined}
                      >
                        <button
                          type="button"
                          className={overallSort === key ? 'is-active' : ''}
                          onClick={() => setOverallSort(key)}
                          onMouseEnter={() => setOverallHelp(OVERALL_SORTS[key].help)}
                          onMouseLeave={() => setOverallHelp(null)}
                          onFocus={() => setOverallHelp(OVERALL_SORTS[key].help)}
                          onBlur={() => setOverallHelp(null)}
                        >
                          {OVERALL_SORTS[key].label}
                        </button>
                      </th>
                    ))}
                    {worpReady && (
                      <th
                        scope="col"
                        data-help={WORP_HELP}
                        onMouseEnter={() => setOverallHelp(WORP_HELP)}
                        onMouseLeave={() => setOverallHelp(null)}
                      >
                        WORP
                      </th>
                    )}
                    {(['value', 'adp'] as const).map((key) => (
                      <th
                        key={key}
                        scope="col"
                        data-help={OVERALL_SORTS[key].help}
                        aria-sort={overallSort === key ? OVERALL_SORTS[key].direction : undefined}
                      >
                        <button
                          type="button"
                          className={overallSort === key ? 'is-active' : ''}
                          onClick={() => setOverallSort(key)}
                          onMouseEnter={() => setOverallHelp(OVERALL_SORTS[key].help)}
                          onMouseLeave={() => setOverallHelp(null)}
                          onFocus={() => setOverallHelp(OVERALL_SORTS[key].help)}
                          onBlur={() => setOverallHelp(null)}
                        >
                          {OVERALL_SORTS[key].label}
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {overallPlayers.map((player, index) => (
                    <tr key={player.player_id}>
                      <td>{index + 1}</td>
                      <th scope="row">
                        <span className={`pos-badge pos-${player.position}`}>
                          {player.position}
                        </span>
                        {player.name}
                        {player.team && <small>{player.team}</small>}
                        <SourceChip
                          source={player.projection_source}
                          outlier={player.projection_source_outlier}
                        />
                      </th>
                      <td>
                        {player.projected_points.toFixed(1)}
                        <BoostChip offset={player.personal_offset} />
                      </td>
                      <td>{signed(player.value_over_replacement)}</td>
                      {worpReady && (
                        <td>
                          {player.wins_over_replacement == null
                            ? '—'
                            : signed(player.wins_over_replacement)}
                        </td>
                      )}
                      <td>
                        <strong>{player.current_roster_value.toFixed(1)}</strong>
                      </td>
                      <td>{player.adp == null ? '—' : player.adp.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
        {visiblePositions.map((position) => {
          const players = board.players.filter((player) => player.position === position)
          if (players.length === 0) return null
          return (
            <section className="projection-position" key={position}>
              <header>
                <div>
                  <span className={`pos-badge pos-${position}`}>{position}</span>
                  <strong>{position} projections</strong>
                </div>
                <small>Replacement: {players[0].replacement_points.toFixed(1)} pts</small>
              </header>
              <div className="projection-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Rank</th>
                      <th scope="col">Player</th>
                      <th scope="col">Projected</th>
                      <th scope="col">VORP</th>
                      {worpReady && <th scope="col">WORP</th>}
                      <th scope="col">Roster value</th>
                      <th scope="col">ADP</th>
                    </tr>
                  </thead>
                  <tbody>
                    {players.map((player) => (
                      <tr key={player.player_id}>
                        <td>{player.position}{player.position_rank}</td>
                        <th scope="row">
                          {player.name}
                          {player.team && <small>{player.team}</small>}
                          <SourceChip
                            source={player.projection_source}
                            outlier={player.projection_source_outlier}
                          />
                        </th>
                        <td>
                          {player.projected_points.toFixed(1)}
                          <BoostChip offset={player.personal_offset} />
                        </td>
                        <td>{signed(player.value_over_replacement)}</td>
                        {worpReady && (
                          <td>
                            {player.wins_over_replacement == null
                              ? '—'
                              : signed(player.wins_over_replacement)}
                          </td>
                        )}
                        <td>{player.current_roster_value.toFixed(1)}</td>
                        <td>{player.adp == null ? '—' : player.adp.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )
        })}
      </div>

      <p className="board-footnote">
        Scored with this league&apos;s Sleeper settings · VORP and route value are defined
        under &ldquo;What the metrics mean&rdquo;.
      </p>
      <p className="board-footnote" role="status">
        {worpReady
          ? `WORP: approved ${board.worp_calibration.model_version} curve for ${board.worp_calibration.team_count}-team ${board.worp_calibration.scoring_format}.`
          : `WORP pending for ${board.worp_calibration.team_count}-team ${board.worp_calibration.scoring_format ?? 'unknown scoring'}: ${worpStatus}.`}
      </p>
    </div>
  )
})
