import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  parseLeagueId,
  rosterAt,
  rosterDifference,
  seasonAt,
  type HistoryEvent,
  type LeagueHistory,
  type Season,
} from './history.ts'
import { normalizeSeason } from './sleeper.ts'

const start = Date.UTC(2024, 4, 1)
const day = 86_400_000
function event(
  id: string,
  at: number,
  adds: HistoryEvent['adds'],
  drops: HistoryEvent['drops'] = [],
): HistoryEvent {
  return { id, at, adds, drops, type: 'trade', picks: [], budget: [] }
}
function season(): Season {
  return {
    id: '123456789012345678',
    year: '2024',
    name: 'Test league',
    previous: null,
    teams: [
      { id: 1, name: 'Team one', manager: 'One', players: ['b', 'c'] },
      { id: 2, name: 'Team two', manager: 'Two', players: ['a'] },
    ],
    drafts: [
      {
        id: 'draft',
        start,
        end: start + day,
        active: false,
        adds: [
          { player: 'a', roster: 1 },
          { player: 'b', roster: 2 },
        ],
      },
    ],
    events: [
      event(
        'swap',
        start + 2 * day,
        [
          { player: 'a', roster: 2 },
          { player: 'b', roster: 1 },
        ],
        [
          { player: 'a', roster: 1 },
          { player: 'b', roster: 2 },
        ],
      ),
      { ...event('waiver', start + 3 * day, [{ player: 'c', roster: 1 }]), type: 'waiver' },
    ],
    fetchedAt: start + 4 * day,
    issues: [],
  }
}
function players(source: Season, at: number) {
  const state = rosterAt(source, at)
  assert.deepEqual(state.issues, [])
  return state.teams.map((team) => team.players.sort())
}

describe('roster reconstruction', () => {
  it('reverses a multi-team swap atomically and includes the transaction at its exact completion time', () => {
    const source = season()
    assert.deepEqual(players(source, start + 2 * day), [['b'], ['a']])
    assert.deepEqual(players(source, start + 2 * day - 1), [['a'], ['b']])
    assert.deepEqual(players(source, start - 1), [[], []])
    assert.deepEqual(players(source, source.fetchedAt), [['b', 'c'], ['a']])
    assert.deepEqual(source.teams[0].players, ['b', 'c'])
  })

  it('reverses drops, additions, and commissioner removals without losing free agents', () => {
    const source = season()
    source.events.push({
      ...event('remove', start + 3 * day + 1, [], [{ player: 'b', roster: 1 }]),
      type: 'commissioner',
    })
    source.teams[0].players = ['c']
    assert.deepEqual(players(source, start + 2 * day), [['b'], ['a']])
  })

  it('handles trades during a slow draft, while marking the draft interval unavailable', () => {
    const source = season()
    source.events[0].at = start + day / 2
    assert.equal(rosterAt(source, start + day / 2).draft?.id, 'draft')
    assert.deepEqual(players(source, start - 1), [[], []])
    assert.deepEqual(players(source, start + day), [['b'], ['a']])
    assert.equal(rosterAt(source, start + day).draft, null)
  })

  it('reports a missing change instead of silently assigning a player to a guessed team', () => {
    const source = season()
    source.teams[0].players = ['c']
    source.teams[1].players.push('b')
    assert.ok(
      rosterAt(source, start + day)
        .issues.join(' ')
        .includes('does not match'),
    )
  })

  it('reports duplicate owners and unknown rosters', () => {
    const source = season()
    source.teams[1].players.push('b')
    assert.ok(rosterAt(source, source.fetchedAt).issues.join(' ').includes('multiple'))
    source.teams[1].players = ['a']
    source.events[1].drops = [{ player: 'z', roster: 99 }]
    assert.ok(
      rosterAt(source, start + 2 * day)
        .issues.join(' ')
        .includes('cannot be restored'),
    )
  })

  it('refuses to guess the order of simultaneous changes to the same player', () => {
    const source = season()
    source.events.push(event('same-time', start + 3 * day, [], [{ player: 'c', roster: 2 }]))
    assert.ok(rosterAt(source, start + 2 * day).issues.length > 0)
  })

  it('permits independent changes at the same timestamp', () => {
    const source = season()
    source.teams[1].players.push('d')
    source.events.push(event('independent', start + 3 * day, [{ player: 'd', roster: 2 }]))
    assert.deepEqual(players(source, start + 2 * day), [['b'], ['a']])
  })

  it('compares season boundaries and hides intervals with unexplained changes', () => {
    const older = season()
    const newer = {
      ...season(),
      id: '123456789012345679',
      year: '2025',
      previous: older.id,
      drafts: [],
      events: [event('new-year', start + 100 * day, [{ player: 'd', roster: 1 }])],
      fetchedAt: start + 101 * day,
    }
    newer.teams = older.teams.map((team) => ({
      ...team,
      players: [...team.players, ...(team.id === 1 ? ['d'] : [])],
    }))
    const history: LeagueHistory = { leagueId: newer.id, seasons: [older, newer], players: {} }
    assert.equal(seasonAt(history, start + 50 * day).gap, false)
    newer.teams[1].players.push('unexplained')
    assert.equal(seasonAt(history, start + 50 * day).gap, true)
    assert.equal(seasonAt(history, start + 100 * day).season.id, newer.id)
    assert.equal(rosterDifference(older.teams, older.teams), 0)
  })
})

describe('Sleeper data boundary', () => {
  const league = {
    league_id: '123456789012345678',
    name: 'Example',
    sport: 'nfl',
    season: '2024',
    total_rosters: 2,
  }
  const rosters = [
    { roster_id: 1, players: ['a'], reserve: ['reserve'], taxi: ['taxi'] },
    { roster_id: 2, players: [] },
  ]
  const transaction = {
    transaction_id: 'trade',
    type: 'trade',
    status: 'complete',
    status_updated: start,
    adds: { a: 1 },
    drops: { a: 2 },
  }

  it('accepts only numeric league IDs and supported Sleeper URLs', () => {
    assert.equal(parseLeagueId('123456789012345678'), '123456789012345678')
    assert.equal(parseLeagueId('https://sleeper.com/leagues/123456789012345678/team'), '123456789012345678')
    assert.throws(() => parseLeagueId('https://example.com/leagues/123456789012345678'))
    assert.throws(() => parseLeagueId('https://sleeper.com/i/invitation'))
    assert.throws(() => parseLeagueId('123abc'))
  })

  it('deduplicates transaction buckets, ignores pending and failed transactions, and retains reserves', () => {
    const result = normalizeSeason(
      league,
      rosters,
      [],
      [
        transaction,
        transaction,
        { ...transaction, transaction_id: 'failed', status: 'failed' },
        { ...transaction, transaction_id: 'pending', status: 'pending' },
      ],
      [],
      start + day,
    )
    assert.equal(result.events.length, 1)
    assert.deepEqual(result.teams[0].players, ['a', 'reserve', 'taxi'])
  })

  it('keeps draft pick ownership and waiver budget transfers in trade history', () => {
    const trade = {
      ...transaction,
      draft_picks: [{ season: '2025', round: 1, roster_id: 1, previous_owner_id: 1, owner_id: 2 }],
      waiver_budget: [{ sender: 2, receiver: 1, amount: 25 }],
    }
    const result = normalizeSeason(league, rosters, [], [trade], [], start + day)
    assert.deepEqual(result.events[0].picks[0], { season: '2025', round: 1, original: 1, from: 1, to: 2 })
    assert.deepEqual(result.events[0].budget[0], { from: 2, to: 1, amount: 25 })
  })

  it('does not invent dates for undated completed events or treat keepers as new acquisitions', () => {
    const result = normalizeSeason(
      league,
      rosters,
      [],
      [{ ...transaction, status_updated: null }],
      [
        {
          draft: { draft_id: 'draft', status: 'complete', start_time: start, last_picked: start + day },
          picks: [{ player_id: 'a', roster_id: 1, is_keeper: true }],
        },
      ],
      start + 2 * day,
    )
    assert.equal(result.issues.length, 1)
    assert.deepEqual(result.drafts[0].adds, [])
    assert.deepEqual(rosterAt(result, result.fetchedAt).issues, [])
    assert.equal(rosterAt(result, start).issues.length, 1)
  })

  it('rejects malformed source data rather than displaying an empty successful import', () => {
    assert.throws(() => normalizeSeason(league, [], [], [], [], start))
    assert.throws(() =>
      normalizeSeason(league, rosters, [], [{ ...transaction, adds: { a: 'not-a-roster' } }], [], start),
    )
    assert.throws(() => normalizeSeason({ ...league, sport: 'nba' }, rosters, [], [], [], start))
  })
})
