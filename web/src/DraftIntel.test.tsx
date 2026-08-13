import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DraftIntel } from './DraftIntel'

function response(body: unknown) {
  return { ok: true, status: 200, json: () => Promise.resolve(body) } as Response
}

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  fetchMock.mockResolvedValue(response({ status: 'idle' }))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('DraftIntel', () => {
  it('explains the league-created mobile mock requirement and accepts its URL', async () => {
    render(<DraftIntel currentDraftId="real" />)
    expect(screen.getByText(/Sleeper mobile app/)).toBeTruthy()
    expect(screen.getByText(/generic Draftboard created on desktop/)).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Sleeper mock draft URL'), {
      target: { value: 'https://sleeper.app/draft/nfl/1393634461312106496' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    expect(screen.getByLabelText<HTMLInputElement>('Sleeper mock draft URL').value).toBe('')
    fireEvent.change(screen.getByLabelText('Sleeper mock draft URL'), {
      target: { value: 'https://sleeper.app/draft/nfl/1393634461312106496' },
    })
    fireEvent.change(screen.getByLabelText('Sleeper username'), {
      target: { value: 'mtoppi' },
    })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Prepare draft' }))
    })

    const call = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      draft_id: 'real',
      username: 'mtoppi',
      mock_draft_id: 'https://sleeper.app/draft/nfl/1393634461312106496',
    })
  })
})
