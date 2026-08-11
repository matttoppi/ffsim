import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiError,
  eventsUrl,
  getResults,
  getSimulation,
  startSimulation,
  type FinalResults,
  type JobSnapshot,
  type SimulationParams,
} from './api'
import {
  applyEvent,
  applySnapshot,
  initialLiveState,
  type LiveState,
  type SseEvent,
} from './events'

export type Connection = 'idle' | 'live' | 'reconnecting'

const SSE_EVENTS: SseEvent[] = ['queued', 'status', 'progress', 'complete', 'failed']

export function useSimulation() {
  const [live, setLive] = useState<LiveState>(initialLiveState)
  const [results, setResults] = useState<FinalResults | null>(null)
  const [startError, setStartError] = useState<string | null>(null)
  const [connection, setConnection] = useState<Connection>('idle')
  const sourceRef = useRef<EventSource | null>(null)

  const closeSource = useCallback(() => {
    sourceRef.current?.close()
    sourceRef.current = null
  }, [])

  useEffect(() => closeSource, [closeSource])

  const finalize = useCallback(async (id: string) => {
    try {
      setResults(await getResults(id))
    } catch (error) {
      setLive((prev) => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Could not load results',
      }))
    }
  }, [])

  const listen = useCallback(
    (id: string) => {
      closeSource()
      const source = new EventSource(eventsUrl(id))
      sourceRef.current = source
      setConnection('live')

      for (const type of SSE_EVENTS) {
        source.addEventListener(type, (event) => {
          if (sourceRef.current !== source) return
          const data = JSON.parse((event as MessageEvent).data) as JobSnapshot
          setLive((prev) => applyEvent(prev, type, data))
          if (type === 'complete' || type === 'failed') {
            closeSource()
            setConnection('idle')
            if (type === 'complete') void finalize(id)
          }
        })
      }
      source.onopen = () => {
        if (sourceRef.current === source) setConnection('live')
      }
      source.onerror = async () => {
        if (sourceRef.current !== source) return
        setConnection('reconnecting')
        try {
          const snapshot = await getSimulation(id)
          if (sourceRef.current !== source) return
          setLive((prev) => applySnapshot(prev, snapshot))
          if (snapshot.status === 'completed' || snapshot.status === 'failed') {
            closeSource()
            setConnection('idle')
            if (snapshot.status === 'completed') void finalize(id)
          }
          // Otherwise the browser EventSource retries with Last-Event-ID and
          // the server replays anything missed.
        } catch {
          /* server unreachable; EventSource keeps retrying */
        }
      }
    },
    [closeSource, finalize],
  )

  const start = useCallback(
    async (params: SimulationParams) => {
      closeSource()
      setConnection('idle')
      setStartError(null)
      setResults(null)
      setLive({ ...initialLiveState, phase: 'starting' })
      try {
        const snapshot = await startSimulation(params)
        setLive({ phase: snapshot.status, snapshot, lastResult: null, error: null })
        listen(snapshot.id)
      } catch (error) {
        setLive(initialLiveState)
        if (error instanceof ApiError && error.status === 409) {
          setStartError(
            'A simulation is already running on the server. Wait for it to finish, then run again.',
          )
        } else {
          setStartError(error instanceof Error ? error.message : 'Could not start simulation')
        }
      }
    },
    [closeSource, listen],
  )

  const busy = ['starting', 'queued', 'loading', 'running'].includes(live.phase)

  return { live, results, startError, connection, start, busy }
}
