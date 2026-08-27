import type { DraftProjectionBoard } from './api'

const POSITION_ORDER = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']

function signed(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}`
}

export function ProjectionBoard({
  board,
  positionFilter,
  onPositionFilterChange,
}: {
  board: DraftProjectionBoard
  positionFilter: string | null
  onPositionFilterChange: (position: string | null) => void
}) {
  const positions = POSITION_ORDER.filter((position) =>
    board.players.some((player) => player.position === position),
  )
  const visiblePositions = positionFilter ? [positionFilter] : positions
  const recommendation = board.plans.find(
    (plan) => plan.player_id === board.recommended_player_id,
  )

  return (
    <div className="projection-board">
      <section className="projection-callout" aria-label="Projection recommendation">
        <div>
          <p className="eyebrow">Fast projection route</p>
          <h4>
            {recommendation
              ? `${recommendation.name} leads the current-turn plan`
              : 'No eligible projected player'}
          </h4>
          {recommendation && (
            <p>
              {recommendation.current_roster_value.toFixed(1)} roster value now
              {board.next_user_pick_no != null && (
                <>
                  {' '}+ {recommendation.later_value.toFixed(1)} expected through pick{' '}
                  {board.next_user_pick_no}
                </>
              )}
              {' '}= {recommendation.route_value.toFixed(1)} route value.
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
                {plan.later_value.toFixed(1)} later
              </small>
              <span>{plan.route_value.toFixed(1)}</span>
            </button>
          ))}
        </section>
      )}

      <div className="pos-filter" role="group" aria-label="Filter projection rankings by position">
        <button
          type="button"
          className={`pos-chip${positionFilter === null ? ' is-active' : ''}`}
          onClick={() => onPositionFilterChange(null)}
        >
          All
        </button>
        {positions.map((position) => (
          <button
            key={position}
            type="button"
            className={`pos-chip${positionFilter === position ? ' is-active' : ''}`}
            onClick={() => onPositionFilterChange(position)}
          >
            {position}
          </button>
        ))}
      </div>

      <div className="projection-position-lists">
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
                        </th>
                        <td>{player.projected_points.toFixed(1)}</td>
                        <td>{signed(player.value_over_replacement)}</td>
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
        Prepared projections scored with this league&apos;s Sleeper settings. VORP is projected
        points above the league-wide starter replacement cutline. Route value uses
        the current roster and deterministic ADP lookahead; it does not run rest-of-draft or
        season simulations.
      </p>
    </div>
  )
}
