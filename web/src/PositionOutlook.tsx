import { memo } from 'react'
import { BoostChip } from './ProjectionBoard'
import type { DraftProjectionBoard } from './api'

function signedValue(value: number) {
  return `${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(1)}`
}

type Turn = NonNullable<
  DraftProjectionBoard['position_outlook']
>['positions'][number]['turns'][number]

function TurnHead() {
  return (
    <li className="turns-head" aria-hidden="true">
      <span />
      <span>best if waiting</span>
      <span>value</span>
      <span>vs now</span>
    </li>
  )
}

function TurnRow({ turn }: { turn: Turn }) {
  const cost = turn.drop_from_now
  return (
    <li>
      <span>Pick {turn.pick_no}</span>
      <span>
        {turn.name ?? 'No projected player'}
        <BoostChip offset={turn.personal_offset ?? 0} />
      </span>
      <span
        className="turn-value"
        title="Expected roster value of the best player still there at that pick"
      >
        {turn.marginal_value.toFixed(1)}
      </span>
      <span
        className={`turn-cost${cost < -0.05 ? ' is-gain' : ''}`}
        title="How the expected roster value compares with drafting the position now"
      >
        {Math.abs(cost) < 0.05 ? '±0' : signedValue(-cost)}
      </span>
    </li>
  )
}

/** Memoized: the monitor poll reuses board references between real changes. */
export const PositionOutlook = memo(function PositionOutlook({
  outlook,
  positionFilter,
}: {
  outlook: NonNullable<DraftProjectionBoard['position_outlook']>
  positionFilter: string | null
}) {
  const filterPositions =
    positionFilter === 'SKILL'
      ? new Set(['RB', 'WR', 'TE'])
      : positionFilter
        ? new Set([positionFilter])
        : null
  const rows = filterPositions
    ? outlook.positions.filter((row) => filterPositions.has(row.position))
    : outlook.positions
  // Zero-cost positions add no decision: collapse them into one line so
  // the cards only show positions where waiting actually loses value.
  const costly = rows.filter((row) => row.take_now_edge >= 0.05)
  const safe = rows.filter((row) => row.take_now_edge < 0.05)
  if (rows.length === 0) return null
  return (
    <section className="falloff" aria-label="Positional falloff">
      <header className="falloff-head">
        <h5>
          Cost of waiting — by position
          {outlook.value_basis === 'raw_projection' && (
            <span className="market-chip">market view · your boosts excluded</span>
          )}
        </h5>
        <span>
          If you skip a position now, the model expects a weaker best option at
          your next pick. The red numbers are roster value lost by waiting:
          −10 under “vs now” means that pick is 10 weaker than drafting now.
        </span>
      </header>
      {costly.length > 0 && (
      <div className="falloff-grid">
        {costly.map((row) => (
          <article className="falloff-card" key={row.position}>
            <header>
              <span className={`pos-badge pos-${row.position}`}>{row.position}</span>
            <strong
              className="falloff-edge"
              title={`Roster value you give up if you pass on ${row.position} now and take the best ${row.position} still there at your next turn`}
            >
              {row.take_now_edge.toFixed(1)}
            </strong>
              <small>
                roster value lost if you wait
                {row.turns[0] != null && <> until pick {row.turns[0].pick_no}</>} ·{' '}
                {row.remaining_starting_opportunities > 0
                  ? `${row.open_dedicated_slots} seat${
                      row.open_dedicated_slots === 1 ? '' : 's'
                    } open${
                      row.eligible_open_flex_slots > 0
                        ? ` +${row.eligible_open_flex_slots} flex (shared)`
                        : ''
                    }`
                  : 'starters filled'}
              </small>
            </header>
            <p className="falloff-now">
              Best now: <strong>{row.best_now_name}</strong>
              <BoostChip offset={row.best_now_personal_offset ?? 0} />{' '}
              · {row.best_now_marginal_value.toFixed(1)} roster value ·{' '}
              {row.best_now_points.toFixed(0)} pts
              {row.best_now_adp != null && <> · ADP {row.best_now_adp.toFixed(0)}</>}
            </p>
            <ul className="falloff-turns">
              <TurnHead />
              {row.turns.slice(0, 3).map((turn) => (
                <TurnRow key={turn.pick_no} turn={turn} />
              ))}
            </ul>
            {(row.turns.length > 3 || row.top_players.length > 0) && (
              <details className="falloff-details">
                <summary>Targets and later turns</summary>
                {row.top_players.length > 0 && (
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">Target now</th>
                        <th scope="col">Value</th>
                        <th scope="col" title="Roster value kept by taking this player now instead of waiting for your next turn">vs next turn</th>
                        <th scope="col">ADP</th>
                      </tr>
                    </thead>
                    <tbody>
                      {row.top_players.map((player) => (
                        <tr key={player.player_id}>
                          <th scope="row">
                            {player.name}
                            <BoostChip offset={player.personal_offset ?? 0} />
                          </th>
                          <td>{player.marginal_value.toFixed(1)}</td>
                          <td>{signedValue(player.edge_vs_next_turn)}</td>
                          <td>{player.adp == null ? '—' : player.adp.toFixed(0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {row.turns.length > 3 && (
                  <ul className="falloff-turns">
                    <TurnHead />
                    {row.turns.slice(3).map((turn) => (
                      <TurnRow key={turn.pick_no} turn={turn} />
                    ))}
                  </ul>
                )}
              </details>
            )}
          </article>
        ))}
      </div>
      )}
      {safe.length > 0 && (
        <p className="falloff-safe">
          <strong>No cost to wait:</strong>
          {safe.map((row) => (
            <span key={row.position} className="falloff-safe-item">
              <span className={`pos-badge pos-${row.position}`}>{row.position}</span>
              {row.best_now_name} · {row.best_now_points.toFixed(0)} pts
            </span>
          ))}
        </p>
      )}
      <p className="board-footnote">
        Roster value = projected points a player adds to your best starting
        lineup over what your roster already covers. Market view: availability
        follows ADP order with the live reach cushion. The simulation advice
        stays the final ranking.
      </p>
    </section>
  )
})
