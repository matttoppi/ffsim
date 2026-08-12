import { useState } from 'react'
import type { FinalResults } from './api'
import { monogram, teamHue } from './events'

const pct = (value: number) => `${(value * 100).toFixed(1)}%`

function TeamDetails({ team, results, onClose }: {
  team: string
  results: FinalResults
  onClose: () => void
}) {
  const stats = results.teams[team]
  const players = Object.values(results.players ?? {})
    .filter((player) => player.team === team)
    .sort((a, b) => b.average_score - a.average_score)
  const seeds = Object.entries(stats.seed_probabilities).sort(
    ([a], [b]) => Number(a) - Number(b),
  )

  return (
    <section className="team-details" aria-label={`${team} simulation details`}>
      <header className="team-details-header">
        <div>
          <p className="eyebrow">Team outlook</p>
          <h3>{team}</h3>
        </div>
        <button type="button" className="button-ghost" onClick={onClose}>Close</button>
      </header>

      <dl className="team-summary">
        <div><dt>Playoffs</dt><dd>{pct(stats.playoff_probability)}</dd></div>
        <div><dt>Championship</dt><dd>{pct(stats.championship_probability)}</dd></div>
        <div><dt>Top two</dt><dd>{pct(stats.top_two_probability)}</dd></div>
        <div><dt>Bottom two</dt><dd>{pct(stats.bottom_two_probability)}</dd></div>
      </dl>

      <div className="team-detail-grid">
        <section>
          <h4>Projected range</h4>
          <dl className="range-grid">
            <div><dt>Wins · P10</dt><dd>{stats.win_percentiles['10'].toFixed(1)}</dd></div>
            <div><dt>Median</dt><dd>{stats.win_percentiles['50'].toFixed(1)}</dd></div>
            <div><dt>Wins · P90</dt><dd>{stats.win_percentiles['90'].toFixed(1)}</dd></div>
            <div><dt>Points · P10</dt><dd>{Math.round(stats.points_percentiles['10']).toLocaleString()}</dd></div>
            <div><dt>Median</dt><dd>{Math.round(stats.points_percentiles['50']).toLocaleString()}</dd></div>
            <div><dt>Points · P90</dt><dd>{Math.round(stats.points_percentiles['90']).toLocaleString()}</dd></div>
          </dl>
        </section>
        <section>
          <h4>Seed odds</h4>
          <ol className="seed-list">
            {seeds.map(([seed, probability]) => (
              <li key={seed}>
                <span>#{seed}</span>
                <span className="seed-track" aria-hidden="true">
                  <span style={{ width: `${probability * 100}%` }} />
                </span>
                <strong>{pct(probability)}</strong>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <section className="roster-outlook">
        <h4>Roster outlook</h4>
        {players.length ? (
          <div className="standings-scroll">
            <table className="player-table">
              <thead><tr><th>Player</th><th>Pos</th><th>Avg pts</th><th>Games/sim</th><th>Avg missed</th></tr></thead>
              <tbody>
                {players.map((player) => (
                  <tr key={`${player.name}-${player.position}`}>
                    <td>{player.name}</td>
                    <td>{player.position}</td>
                    <td>{player.average_score.toFixed(1)}</td>
                    <td>{player.games_per_simulation.toFixed(1)}</td>
                    <td>{player.average_games_missed.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="detail-empty">Player outlook is unavailable for teams-only runs.</p>
        )}
      </section>
    </section>
  )
}

export function Standings({ results }: { results: FinalResults }) {
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null)
  const rows = Object.entries(results.teams).sort(
    ([, a], [, b]) =>
      b.championship_probability - a.championship_probability ||
      b.playoff_probability - a.playoff_probability ||
      b.average_wins - a.average_wins,
  )
  const titleFavorite = rows[0]
  const bestOffense = [...rows].sort(
    ([, a], [, b]) => b.average_points_per_week - a.average_points_per_week,
  )[0]
  const widestRange = [...rows].sort(
    ([, a], [, b]) =>
      b.win_percentiles['90'] - b.win_percentiles['10'] -
      (a.win_percentiles['90'] - a.win_percentiles['10']),
  )[0]
  const hasDivisions = rows.some(([, stats]) => stats.division_win_probability > 0)
  const selected = selectedTeam && results.teams[selectedTeam] ? selectedTeam : null

  return (
    <section className="panel standings" aria-label="Final projected standings">
      <header className="race-header">
        <h2 className="panel-title">Projected standings</h2>
        <p className="standings-meta">
          {results.league.name} · {results.simulations.toLocaleString()} seasons ·
          seed {results.seed}
        </p>
      </header>
      <div className="run-insights" aria-label="Run insights">
        <button type="button" onClick={() => setSelectedTeam(titleFavorite[0])}>
          <span>Title favorite</span>
          <strong>{titleFavorite[0]}</strong>
          <small>{pct(titleFavorite[1].championship_probability)} championship chance</small>
        </button>
        <button type="button" onClick={() => setSelectedTeam(bestOffense[0])}>
          <span>Best offense</span>
          <strong>{bestOffense[0]}</strong>
          <small>{bestOffense[1].average_points_per_week.toFixed(1)} projected pts/wk</small>
        </button>
        <button type="button" onClick={() => setSelectedTeam(widestRange[0])}>
          <span>Widest outcome range</span>
          <strong>{widestRange[0]}</strong>
          <small>{widestRange[1].win_percentiles['10'].toFixed(0)}–{widestRange[1].win_percentiles['90'].toFixed(0)} wins</small>
        </button>
      </div>
      <div className="standings-scroll">
        <table className="standings-table">
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col" className="col-team">Team</th>
              <th scope="col">Avg wins</th>
              <th scope="col">Pts/wk</th>
              <th scope="col">Playoffs</th>
              {hasDivisions && <th scope="col">Division</th>}
              <th scope="col">Title</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([team, stats], index) => (
              <tr key={team} className={selected === team ? 'is-selected' : undefined}>
                <td>{index + 1}</td>
                <td className="col-team">
                  <span
                    className="mono mono-sm"
                    style={{ ['--hue' as string]: teamHue(team) }}
                    aria-hidden="true"
                  >
                    {monogram(team)}
                  </span>
                  <button
                    type="button"
                    className="team-link"
                    aria-expanded={selected === team}
                    onClick={() => setSelectedTeam(team)}
                  >
                    {team}
                  </button>
                </td>
                <td>{stats.average_wins.toFixed(1)}</td>
                <td>{stats.average_points_per_week.toFixed(1)}</td>
                <td>{pct(stats.playoff_probability)}</td>
                {hasDivisions && <td>{pct(stats.division_win_probability)}</td>}
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
      {selected && (
        <TeamDetails team={selected} results={results} onClose={() => setSelectedTeam(null)} />
      )}
    </section>
  )
}
