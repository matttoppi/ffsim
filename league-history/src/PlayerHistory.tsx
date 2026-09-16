import { useEffect, useRef } from 'react'
import { EventDetails, date, label, teamName, timeFormat } from './EventDetails.tsx'
import {
  playerContext,
  playerHistory,
  playerInfo,
  seasonAt,
  seasonStart,
  type LeagueHistory,
  type PlayerMove,
} from './history.ts'

export type PlayerSelection = { player: string; roster: number; at: number }

function moveDescription(move: PlayerMove, player: string) {
  const from = move.event.drops.find((item) => item.player === player)?.roster
  const to = move.event.adds.find((item) => item.player === player)?.roster
  if (from !== undefined && to !== undefined)
    return `${teamName(move.season, from)} → ${teamName(move.season, to)}`
  if (to !== undefined) return `Joined ${teamName(move.season, to)}`
  return `Left ${teamName(move.season, from!)}`
}

function moveDate(move: PlayerMove) {
  return date(move.start) === date(move.event.at)
    ? date(move.event.at)
    : `${date(move.start)} – ${date(move.event.at)}`
}

export function PlayerHistory({
  history,
  selection,
  onClose,
  onView,
  onCompare,
}: {
  history: LeagueHistory
  selection: PlayerSelection
  onClose: () => void
  onView: (at: number) => void
  onCompare: (from: number, to: number) => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const { player: id, roster, at } = selection
  const player = playerInfo(history, id)
  const moves = playerHistory(history, id)
  const { arrival, departure } = playerContext(moves, id, roster, at)
  const contextSeason = seasonAt(history, at).season
  const first = seasonStart(history.seasons[0])

  useEffect(() => {
    const element = dialog.current!
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const overflow = document.body.style.overflow
    element.showModal()
    document.body.style.overflow = 'hidden'
    return () => {
      element.close()
      document.body.style.overflow = overflow
      if (trigger?.isConnected) trigger.focus({ preventScroll: true })
    }
  }, [])

  return (
    <dialog
      ref={dialog}
      className="player-dialog"
      aria-labelledby="player-history-title"
      aria-describedby="player-history-context"
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
    >
      <header className="player-dialog-heading">
        <div>
          <p className="eyebrow">{player.position} · Player history</p>
          <h2 id="player-history-title">{player.name}</h2>
          <p id="player-history-context">
            {teamName(contextSeason, roster)} · {date(at)}
          </p>
        </div>
        <button
          type="button"
          className="dialog-close"
          aria-label="Close player history"
          onClick={onClose}
          autoFocus
        >
          ×
        </button>
      </header>
      <div className="player-dialog-body">
        <div className="player-context">
          {[
            { title: 'Last recorded arrival', move: arrival },
            { title: 'Next recorded departure', move: departure },
          ].map(({ title, move }) => (
            <div key={title}>
              <p className="eyebrow">{title}</p>
              <strong>{move ? moveDate(move) : 'No record found'}</strong>
              <p>
                {move
                  ? `${label(move.event)} · ${moveDescription(move, id)}`
                  : 'Within the imported league history.'}
              </p>
              {move && (
                <button
                  type="button"
                  className="history-jump"
                  onClick={() => {
                    const details = document.getElementById(`player-move-${move.season.id}-${move.event.id}`)
                    if (details instanceof HTMLDetailsElement) {
                      details.open = true
                      details.scrollIntoView({ block: 'start' })
                    }
                  }}
                >
                  View {move.event.type === 'trade' ? 'trade' : 'move'} details →
                </button>
              )}
            </div>
          ))}
        </div>
        <p className="player-history-note">
          Recorded moves across all seasons. Draft dates show the draft window; individual pick times are
          unavailable. Missing records can leave gaps in a player’s history.
        </p>
        <h3>
          Every recorded move <span>{moves.length}</span>
        </h3>
        <ol className="player-history-list">
          {moves.map((move) => {
            const { event, season } = move
            const highlighted = move === arrival || move === departure
            const activeDraft = season.drafts.some(
              (draft) => `draft:${draft.id}` === event.id && draft.active,
            )
            return (
              <li key={`${season.id}:${event.id}`} className={event.at > at ? 'future-move' : ''}>
                <details id={`player-move-${season.id}-${event.id}`} open={highlighted}>
                  <summary>
                    <span className="player-move-meta">
                      <span>
                        {label(event)} · {moveDate(move)}
                        {activeDraft ? ' · in progress' : ''}
                      </span>
                      {move.start > at && <span>After selected date</span>}
                    </span>
                    <strong>{moveDescription(move, id)}</strong>
                    <span className="move-detail-hint">
                      {event.type === 'trade' ? 'Full trade details' : 'Move details'}
                    </span>
                  </summary>
                  {event.type === 'draft' ? (
                    <p className="draft-player-detail">
                      {player.name}: {moveDescription(move, id)} during this draft.
                    </p>
                  ) : (
                    <EventDetails event={event} season={season} history={history} />
                  )}
                  {!activeDraft && (
                    <div className="player-move-actions">
                      <button
                        type="button"
                        className="button secondary"
                        onClick={() => {
                          onView(event.at)
                          onClose()
                        }}
                      >
                        View roster after
                      </button>
                      {event.type !== 'draft' && event.at > first && (
                        <button
                          type="button"
                          className="button primary"
                          onClick={() => {
                            onCompare(event.at - 1, event.at)
                            onClose()
                          }}
                        >
                          Compare this move
                        </button>
                      )}
                    </div>
                  )}
                  {event.type !== 'draft' && (
                    <p className="move-exact-date">
                      {date(event.at)} at {timeFormat.format(event.at)} UTC
                    </p>
                  )}
                </details>
              </li>
            )
          })}
        </ol>
        {!moves.length && (
          <p className="no-results">No acquisition or departure record is available for this player.</p>
        )}
      </div>
    </dialog>
  )
}
