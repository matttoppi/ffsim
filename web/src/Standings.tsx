import type { FinalResults } from './api'
import { monogram, teamHue } from './events'

const pct = (value: number) => `${(value * 100).toFixed(1)}%`

export function Standings({ results }: { results: FinalResults }) {
  const rows = Object.entries(results.teams).sort(
    ([, a], [, b]) =>
      b.championship_probability - a.championship_probability ||
      b.playoff_probability - a.playoff_probability ||
      b.average_wins - a.average_wins,
  )
  return (
    <section className="panel standings" aria-label="Final projected standings">
      <header className="race-header">
        <h2 className="panel-title">Projected standings</h2>
        <p className="standings-meta">
          {results.league.name} · {results.simulations.toLocaleString()} seasons ·
          seed {results.seed}
        </p>
      </header>
      <div className="standings-scroll">
        <table className="standings-table">
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col" className="col-team">Team</th>
              <th scope="col">Avg wins</th>
              <th scope="col">Pts/wk</th>
              <th scope="col">Playoffs</th>
              <th scope="col">Division</th>
              <th scope="col">Title</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([team, stats], index) => (
              <tr key={team}>
                <td>{index + 1}</td>
                <td className="col-team">
                  <span
                    className="mono mono-sm"
                    style={{ ['--hue' as string]: teamHue(team) }}
                    aria-hidden="true"
                  >
                    {monogram(team)}
                  </span>
                  {team}
                </td>
                <td>{stats.average_wins.toFixed(1)}</td>
                <td>{stats.average_points_per_week.toFixed(1)}</td>
                <td>{pct(stats.playoff_probability)}</td>
                <td>{pct(stats.division_win_probability)}</td>
                <td className="col-title">
                  <span className="mini-track" aria-hidden="true">
                    <span
                      className="mini-fill"
                      style={{ width: `${Math.min(100, stats.championship_probability * 100)}%` }}
                    />
                  </span>
                  {pct(stats.championship_probability)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
