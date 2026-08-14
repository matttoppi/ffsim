import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return {
    ...actual,
    getLeagueInfo: vi.fn(() => new Promise(() => {})),
    getDraftPreparation: vi.fn(() => new Promise(() => {})),
    getDraftMonitor: vi.fn(() => new Promise(() => {})),
  }
})

import App from './App'

describe('App', () => {
  it('keeps draft intelligence separate from the season simulator', () => {
    render(<App />)

    expect(screen.getByRole('tabpanel', { name: 'Draft intelligence' })).toBeTruthy()
    expect(document.getElementById('season-simulator-panel')?.hidden).toBe(true)

    fireEvent.click(screen.getByRole('tab', { name: 'Season simulator' }))

    expect(document.getElementById('draft-intelligence-panel')?.hidden).toBe(true)
    expect(screen.getByRole('form', { name: 'Simulation settings' })).toBeTruthy()
  })
})
