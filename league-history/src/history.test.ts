import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  compareRosters,
  parseLeagueId,
  playerContext,
  playerHistory,
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

describe('player history and roster comparisons', () => {
  function history(source = season()): LeagueHistory {
    return { leagueId: source.id, seasons: [source], players: {} }
  }

  it('shows both sides of a trade and preserves the direction when viewing an earlier date', () => {
    const source = history()
    const at = start + 2 * day
    const forward = compareRosters(source, at - 1, at)
    assert.equal(forward.issue, null)
    assert.deepEqual(forward.changes.get(1), { added: ['b'], removed: ['a'] })
    assert.deepEqual(forward.changes.get(2), { added: ['a'], removed: ['b'] })
    assert.deepEqual(compareRosters(source, at, at - 1).changes.get(1), { added: ['a'], removed: ['b'] })
    assert.deepEqual(compareRosters(source, at, at).changes.get(1), { added: [], removed: [] })
  })

  it('reports net membership changes, without counting a player who leaves and returns', () => {
    const source = season()
    source.events.push(event('drop', start + 3 * day + 1, [], [{ player: 'b', roster: 1 }]))
    source.events.push(event('return', start + 3 * day + 2, [{ player: 'b', roster: 1 }]))
    assert.deepEqual(compareRosters(history(source), start + 2 * day, source.fetchedAt).changes.get(1), {
      added: ['c'],
      removed: [],
    })
  })

  it('blocks comparisons at draft intervals, replay failures, and unverified renewal gaps', () => {
    const source = history()
    assert.ok(compareRosters(source, start, start + 2 * day).issue)
    source.seasons[0].issues.push('Missing source record')
    assert.ok(compareRosters(source, start + day, start + 2 * day).issue)
    source.seasons[0].issues = []
    const newer = {
      ...season(),
      id: '123456789012345679',
      year: '2025',
      drafts: [],
      events: [],
      fetchedAt: start + 100 * day,
    }
    newer.teams[0].players.push('unexplained')
    source.seasons.push(newer)
    assert.ok(compareRosters(source, start + 50 * day, newer.fetchedAt).issue)
    newer.teams.pop()
    assert.ok(compareRosters(source, start + 3 * day, newer.fetchedAt).issue?.includes('roster slots'))
  })

  it('keeps complete trade assets and draft intervals in a player history across seasons', () => {
    const source = history()
    source.seasons[0].events[0].picks.push({ season: '2025', round: 1, original: 1, from: 1, to: 2 })
    const newer = {
      ...season(),
      id: '123456789012345679',
      year: '2025',
      drafts: [],
      events: [
        event('return', start + 100 * day, [{ player: 'a', roster: 1 }], [{ player: 'a', roster: 2 }]),
      ],
    }
    source.seasons.push(newer)
    const moves = playerHistory(source, 'a')
    assert.deepEqual(
      moves.map((move) => move.event.id),
      ['draft:draft', 'swap', 'return'],
    )
    assert.equal(moves[0].start, start)
    assert.equal(moves[0].event.at, start + day)
    assert.equal(moves[1].event.picks.length, 1)
    assert.equal(moves[2].season, newer)
    assert.deepEqual(playerHistory(source, 'unknown'), [])
  })

  it('selects the latest arrival for a returning player and the next departure after the viewed date', () => {
    const source = history()
    source.seasons[0].events.push(
      event('return', start + 3 * day, [{ player: 'a', roster: 1 }], [{ player: 'a', roster: 2 }]),
    )
    const moves = playerHistory(source, 'a')
    const firstStay = playerContext(moves, 'a', 1, start + day)
    assert.equal(firstStay.arrival?.event.id, 'draft:draft')
    assert.equal(firstStay.departure?.event.id, 'swap')
    const secondStay = playerContext(moves, 'a', 1, start + 3 * day)
    assert.equal(secondStay.arrival?.event.id, 'return')
    assert.equal(secondStay.departure, undefined)
    assert.equal(playerContext(moves, 'a', 1, start).arrival, undefined)
  })
})

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
