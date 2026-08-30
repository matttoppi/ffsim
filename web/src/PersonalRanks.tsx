import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ApiError,
  fetchPersonalRanks,
  savePersonalRank,
  type PersonalRanksBoard,
} from './api'

const POSITION_ORDER = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']

function offsetBadge(offset: number) {
  if (offset === 0) return '—'
  return offset > 0 ? `+${offset}` : `${offset}`
}

/**
 * Personal draft board: every player sorted by market ADP, with a per-player
 * season-point offset (more or fewer projected points than the base
 * projection) saved to the server on click.
 */
export function PersonalRanks() {
  const [board, setBoard] = useState<PersonalRanksBoard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [errorStatus, setErrorStatus] = useState<number | null>(null)
  const [saveError, setSaveError] = useState<{ id: string; message: string } | null>(null)
  const [search, setSearch] = useState('')
  const [position, setPosition] = useState<string | null>(null)
  const [ratedOnly, setRatedOnly] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [pendingNotice, setPendingNotice] = useState(false)
  const noticeTimer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(noticeTimer.current), [])

  const load = useCallback(
    () =>
      fetchPersonalRanks().then(
        (value) => {
          setBoard(value)
          setError(null)
          setErrorStatus(null)
        },
        (cause) => {
          setError(cause instanceof Error ? cause.message : 'Personal ranks failed')
          setErrorStatus(cause instanceof ApiError ? cause.status : null)
        },
      ),
    [],
  )

  useEffect(() => {
    void load()
  }, [load])

  const ranked = useMemo(() => {
    if (!board) return []
    return board.players
      .map((player) => ({ player }))
      .sort((a, b) => {
        if (a.player.adp === null && b.player.adp === null)
          return a.player.name.localeCompare(b.player.name)
        if (a.player.adp === null) return 1
        if (b.player.adp === null) return -1
        return a.player.adp - b.player.adp
      })
      .map((entry, index) => ({ ...entry, rank: index + 1 }))
  }, [board])

  if (error && !board) {
    return (
      <section className="panel personal-ranks" aria-label="My ranks">
        <p className="eyebrow">My ranks</p>
        <p className="form-error" role="alert">{error}</p>
        {errorStatus === 409 && (
          <p className="controls-hint">
            Pick a league and run draft preparation first — personal ranks lean on the
            cached market board.
          </p>
        )}
        <button type="button" className="button-ghost" onClick={() => void load()}>
          Retry
        </button>
      </section>
    )
  }
  if (!board) {
    return (
      <section className="panel personal-ranks" aria-label="My ranks">
        <p className="eyebrow">My ranks</p>
        <p className="controls-hint" role="status">Loading personal ranks…</p>
      </section>
    )
  }

  const positions = POSITION_ORDER.filter((pos) =>
    board.players.some((player) => player.position === pos),
  )
  const boostCount = board.players.filter((player) => player.offset > 0).length
  const fadeCount = board.players.filter((player) => player.offset < 0).length
  const ratedCount = boostCount + fadeCount
  const query = search.trim().toLowerCase()
  const visible = ranked.filter(({ player }) => {
    if (position && player.position !== position) return false
    if (ratedOnly && player.offset === 0) return false
    if (query && !player.name.toLowerCase().includes(query)) return false
    return true
  })

  const save = (playerId: string, offset: number) => {
    const previous = board.players.find((p) => p.player_id === playerId)
    if (!previous || previous.offset === offset) return
    const revertTo = previous.offset
    setSaveError(null)
    setBoard({
      ...board,
      players: board.players.map((p) =>
        p.player_id === playerId ? { ...p, offset } : p,
      ),
    })
    savePersonalRank(playerId, offset).then(
      (result) => {
        window.clearTimeout(noticeTimer.current)
        if (result.applied === 'next_prepare') {
          setPendingNotice(true)
          noticeTimer.current = window.setTimeout(() => setPendingNotice(false), 5000)
        } else {
          setPendingNotice(false)
        }
      },
      (cause: unknown) => {
        setBoard((current) =>
          current
            ? {
                ...current,
                players: current.players.map((p) =>
                  p.player_id === playerId ? { ...p, offset: revertTo } : p,
                ),
              }
            : current,
        )
        setSaveError({
          id: playerId,
          message: cause instanceof Error ? cause.message : 'Save failed',
        })
      },
    )
  }

  const step = (playerId: string, offset: number, direction: -1 | 1) => {
    const index = board.allowed_offsets.indexOf(offset)
    const next = board.allowed_offsets[index + direction]
    if (next !== undefined) save(playerId, next)
  }

  return (
    <section className="panel personal-ranks" aria-label="My ranks">
      <header className="ranks-header">
        <div>
          <p className="eyebrow">My ranks</p>
          <h2>Personal draft board</h2>
        </div>
        <div>
          <p className="ranks-count" role="status">
            {ratedCount === 0
              ? 'No rated players yet'
              : `${ratedCount} rated · ${boostCount} boost${boostCount === 1 ? '' : 's'} · ${fadeCount} fade${fadeCount === 1 ? '' : 's'}`}
          </p>
          {pendingNotice && (
            <p className="ranks-applied" role="status">
              Saved — applies after next draft prep
            </p>
          )}
        </div>
      </header>
      <p className="controls-hint">
        Boost (+) or fade (−) a player&apos;s projected season points. Feeds the
        draft engine · saves on click.
      </p>
      <div className="ranks-controls">
        <input
          type="search"
          aria-label="Search players"
          placeholder="Search players…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setSearch('')
          }}
        />
        <div className="ranks-pills" role="group" aria-label="Position filter">
          <button
            type="button"
            className={position === null ? 'is-active' : ''}
            aria-pressed={position === null}
            onClick={() => setPosition(null)}
          >
            ALL
          </button>
          {positions.map((pos) => (
            <button
              key={pos}
              type="button"
              className={position === pos ? 'is-active' : ''}
              aria-pressed={position === pos}
              onClick={() => setPosition(position === pos ? null : pos)}
            >
              {pos}
            </button>
          ))}
        </div>
        <label className="check ranks-rated-toggle">
          <input
            type="checkbox"
            checked={ratedOnly}
            onChange={(e) => setRatedOnly(e.target.checked)}
          />
          Rated only
        </label>
      </div>
      <div className="ranks-list" role="list">
        {visible.length === 0 && (
          <p className="controls-hint">No players match the current filters.</p>
        )}
        {visible.map(({ player, rank }) => {
          const expanded = expandedId === player.player_id
          return (
            <div role="listitem" key={player.player_id}>
              <div className={`ranks-row${player.offset !== 0 ? ' is-rated' : ''}`}>
                <span className="ranks-rank">{rank}</span>
                <span className={`pos-badge pos-${player.position}`}>
                  {player.position}
                </span>
                <span className="ranks-player">
                  <strong>{player.name}</strong>
                  {player.team && <small>{player.team}</small>}
                </span>
                <span className="ranks-adp">
                  <small>ADP</small>
                  {player.adp === null ? '—' : player.adp.toFixed(1)}
                </span>
                <span
                  className={`ranks-offset${
                    player.offset > 0 ? ' is-boost' : player.offset < 0 ? ' is-fade' : ''
                  }`}
                  aria-label={`Offset for ${player.name}`}
                >
                  {offsetBadge(player.offset)}
                </span>
                <span className="ranks-actions">
                  <button
                    type="button"
                    className="ranks-step"
                    aria-label={`Fade ${player.name}`}
                    title="Fade — fewer points"
                    disabled={player.offset === board.allowed_offsets[0]}
                    onClick={() => step(player.player_id, player.offset, -1)}
                  >
                    −
                  </button>
                  <button
                    type="button"
                    className="ranks-step"
                    aria-label={`Boost ${player.name}`}
                    title="Boost — more points"
                    disabled={
                      player.offset ===
                      board.allowed_offsets[board.allowed_offsets.length - 1]
                    }
                    onClick={() => step(player.player_id, player.offset, 1)}
                  >
                    +
                  </button>
                  <button
                    type="button"
                    className={`ranks-step ranks-expand${expanded ? ' is-active' : ''}`}
                    aria-expanded={expanded}
                    aria-label={`All offsets for ${player.name}`}
                    onClick={() => setExpandedId(expanded ? null : player.player_id)}
                  >
                    …
                  </button>
                </span>
              </div>
              {saveError?.id === player.player_id && (
                <p className="form-error ranks-save-error" role="alert">
                  {saveError.message}
                </p>
              )}
              {expanded && (
                <div className="ranks-offset-picker" role="group" aria-label={`Offset picker for ${player.name}`}>
                  <span className="ranks-offset-hint">← fade</span>
                  {board.allowed_offsets.map((offset) => (
                    <button
                      key={offset}
                      type="button"
                      className={offset === player.offset ? 'is-active' : ''}
                      aria-pressed={offset === player.offset}
                      onClick={() => save(player.player_id, offset)}
                    >
                      {offset === 0 ? 'Clear' : offsetBadge(offset)}
                    </button>
                  ))}
                  <span className="ranks-offset-hint">boost →</span>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
