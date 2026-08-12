import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RaceBoard } from './RaceBoard'
import type { JobSnapshot } from './api'

const snapshot = {
  id: 'job',
  completed: 1,
  total: 1,
  progress: 1,
  seed: 1,
  workers: 1,
  teams_only: true,
  elapsed_seconds: 1,
  simulations_per_second: 1,
  status: 'completed',
  championships: { Alpha: 1 },
  playoff_appearances: { Alpha: 1 },
  division_wins: {},
  error: null,
} satisfies JobSnapshot

describe('RaceBoard', () => {
  it('hides division wins when the league has no divisions', () => {
    render(<RaceBoard snapshot={snapshot} lastResult={null} completed />)

    expect(screen.queryByRole('button', { name: 'Division wins' })).toBeNull()
    expect(screen.getByText('Alpha')).toBeTruthy()
  })
})
