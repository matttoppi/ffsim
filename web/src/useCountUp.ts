import { useEffect, useRef, useState } from 'react'

export const prefersReducedMotion = () =>
  typeof matchMedia === 'function' &&
  matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * Animate toward the latest target over ~300ms. Each new target restarts from
 * the currently displayed value, so fast updates converge instead of queueing.
 */
export function useCountUp(target: number): number {
  const [display, setDisplay] = useState(target)
  const displayRef = useRef(target)
  const targetRef = useRef(target)

  useEffect(() => {
    const previousTarget = targetRef.current
    targetRef.current = target
    if (
      prefersReducedMotion() ||
      document.visibilityState === 'hidden' ||
      target === displayRef.current
    ) {
      displayRef.current = target
      setDisplay(target)
      return
    }
    // Rapid retargets must never queue up: snap to the value we were already
    // heading for, then animate only the newest delta.
    if (displayRef.current !== previousTarget) {
      displayRef.current = previousTarget
      setDisplay(previousTarget)
    }
    const from = displayRef.current
    const startTime = performance.now()
    const duration = 300
    let frame: number
    const tick = (now: number) => {
      const t = Math.min(1, (now - startTime) / duration)
      const eased = 1 - (1 - t) * (1 - t)
      displayRef.current = t === 1 ? target : from + (target - from) * eased
      setDisplay(displayRef.current)
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    // rAF stalls in hidden tabs; guarantee we land on the server value.
    const settle = setTimeout(() => {
      cancelAnimationFrame(frame)
      displayRef.current = target
      setDisplay(target)
    }, duration + 100)
    return () => {
      cancelAnimationFrame(frame)
      clearTimeout(settle)
    }
  }, [target])

  return display
}
