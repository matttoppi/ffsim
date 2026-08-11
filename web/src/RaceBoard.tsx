import { useState } from 'react'
import type { JobSnapshot, LastResult } from './api'
import { monogram, teamHue, teamRows, type Metric } from './events'
import { useCountUp } from './useCountUp'

const METRICS: { key: Metric; label: string }[] = [
  { key: 'championships', label: 'Championships' },
  { key: 'playoff_appearances', label: 'Playoff berths' },
  { key: 'division_wins', label: 'Division wins' },
]

const ROW_HEIGHT = 58

function Row({
  team,
  count,
  share,
  rank,
  leaderCount,
  isLatestChampion,
  isWinner,
  flashKey,
}: {
  team: string
  count: number
  share: number
  rank: number
  leaderCount: number
  isLatestChampion: boolean
  isWinner: boolean
  flashKey: number
}) {
  const displayCount = useCountUp(count)
  const displayShare = useCountUp(share * 100)
  const width = leaderCount > 0 ? (count / leaderCount) * 100 : 0
  return (
    <li
      className={`race-row${rank === 1 && count > 0 ? ' is-leader' : ''}${isWinner ? ' is-winner' : ''}`}
      style={{
        transform: `translateY(${(rank - 1) * ROW_HEIGHT}px)`,
        ['--hue' as string]: teamHue(team),
      }}
    >
      <span className="race-bar" style={{ width: `${width}%` }} aria-hidden="true" />
      <span className="race-rank" aria-hidden="true">
        {rank}
      </span>
      <span className="mono" aria-hidden="true">
        {monogram(team)}
      </span>
      <span className="race-team">{team}</span>
      {isLatestChampion && (
        <span key={flashKey} className="race-flash" aria-hidden="true">
          CROWNED
        </span>
      )}
      {isWinner && <span className="race-crown" aria-hidden="true">🏆</span>}
      <span className="race-share">{displayShare.toFixed(1)}%</span>
      <span className="race-count">{Math.round(displayCount)}</span>
    </li>
  )
}

export function RaceBoard({
  snapshot,
  lastResult,
  completed,
}: {
  snapshot: JobSnapshot | null
  lastResult: LastResult | null
  completed: boolean
}) {
  const [metric, setMetric] = useState<Metric>('championships')
  const rows = teamRows(snapshot, metric)
  const leaderCount = rows[0]?.count ?? 0
  const winner = completed && metric === 'championships' ? rows[0]?.team : undefined

  return (
    <section className="panel race" aria-label="Live leaderboard">
      <header className="race-header">
        <h2 className="panel-title">Championship race</h2>
        <div className="race-tabs" role="group" aria-label="Leaderboard metric">
          {METRICS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              className="race-tab"
              aria-pressed={metric === key}
              onClick={() => setMetric(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </header>
      {rows.length === 0 ? (
        <p className="race-empty">
          Teams appear here as soon as the league loads. Run a simulation to
          start the race.
        </p>
      ) : (
        <ol className="race-list" style={{ height: rows.length * ROW_HEIGHT }}>
          {rows.map((row, index) => (
            <Row
              key={row.team}
              team={row.team}
              count={row.count}
              share={row.share}
              rank={index + 1}
              leaderCount={leaderCount}
              isLatestChampion={
                metric === 'championships' &&
                !completed &&
                lastResult?.champion === row.team
              }
              isWinner={row.team === winner}
              flashKey={snapshot?.completed ?? 0}
            />
          ))}
        </ol>
      )}
    </section>
  )
}
