import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useCountUp } from './useCountUp'

describe('useCountUp', () => {
  it('never lags more than one update behind rapid targets', () => {
    const { result, rerender } = renderHook(({ value }) => useCountUp(value), {
      initialProps: { value: 0 },
    })
    // Simulate a fast stream of progress events with no animation frames between.
    for (const value of [10, 20, 30, 40]) {
      act(() => rerender({ value }))
    }
    expect(result.current).toBeGreaterThanOrEqual(30)
  })
})
