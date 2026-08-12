## 6. Data Acquisition and Snapshot Strategy

### 6.1 Sleeper live and league data

Use Sleeper as the authoritative source for the target Sleeper league. Required data includes:

- user object(s)
- target league
- target league users
- target league rosters
- target league drafts
- target draft details
- target draft picks
- league traded picks and/or draft traded picks as applicable
- full player map, cached no more frequently than necessary

The documented API is read-only and does not require a token. Live polling must include backoff and remain comfortably below Sleeper's stated general rate guidance.

### 6.2 League-mate draft-history crawl

For each current league mate:

1. Resolve Sleeper `user_id`.
2. Request that user's NFL drafts for the current season.
3. Request previous-season drafts as configured (initially current year, previous year, and two years prior).
4. Collect all returned `draft_id` values.
5. Deduplicate globally by `draft_id` before fetching picks.
6. Fetch each unique draft metadata and picks exactly once.
7. Associate picks back to all relevant current league mates who participated.
8. Store the raw source payload and normalized rows.

This explicitly solves the common case where several current league mates are also in another league with the user. That shared draft is one draft environment, not multiple independent datasets.

### 6.3 Historical draft inclusion filters

Every historical draft must be classified before it influences the model:

- redraft vs keeper vs dynasty
- snake vs linear vs auction
- normal managed league vs best ball if detectable
- 1QB vs superflex
- scoring format
- team count
- roster depth
- season
- platform
- draft date

Default behavior:

- Use same-season, same-format redraft data most strongly.
- Use prior seasons as weaker priors.
- Exclude auctions from snake choice modeling.
- Exclude rookie-only drafts.
- Exclude dynasty startup picks from redraft player-affinity estimates unless a specific feature is proven useful in backtesting.
- Exclude keeper picks from voluntary preference training.
- Keep dissimilar drafts in storage for future research rather than deleting them.

### 6.4 ADP and rankings sources

Implement an adapter interface rather than wiring the engine directly to any one vendor.

```python
class MarketDataSource(Protocol):
    name: str

    def fetch(self, context: MarketContext) -> list[MarketObservation]: ...
```

Initial source hierarchy:

1. **Target-platform board rank**, if a stable authorized source is established.
2. **Target-platform ADP.**
3. **FantasyPros consensus ADP/ECR and projection/ranking metadata via official API.**
4. **Other platform-specific ADP sources** (Yahoo, ESPN, Fleaflicker, etc.) only through supported APIs, licensed data, authorized exports, or explicit user imports.
5. **Manual CSV/import adapter** as a safe fallback for useful data that cannot be legally or reliably automated.

Do not make unofficial ESPN endpoints a hard production dependency. The implementation agent should research whether a stable, permitted source for current ESPN-specific ADP exists. If not, ESPN-specific ADP remains optional.

### 6.5 FantasyPros integration requirements

The official FantasyPros API currently advertises NFL consensus rankings, ADP, projections, player metadata/external IDs, news, and injuries. Personal/non-commercial production access is tied to their personal API options; commercial/redistribution use has separate licensing requirements.

Implementation requirements:

- Use the official API rather than scraping when the needed field is available.
- Verify with a real API key whether per-platform ADP splits are exposed in the official response. Do not assume that public web-page columns are present in the API.
- If the API only exposes consensus ADP, treat it as consensus and acquire source-specific platform ADP separately.
- Persist retrieval timestamps and raw payload hashes.

### 6.6 Yahoo and Fleaflicker

Yahoo's official Fantasy Sports API is OAuth-backed and can expose fantasy game/league/team/player data to an authorized user. It can be considered later for leagues the user is authorized to access. Do not assume it can discover unrelated private league-mate history.

Fleaflicker exposes an HTTP API including draft boards, league rules, and rosters. This makes it a viable future adapter for explicitly known/accessible Fleaflicker leagues.

Cross-platform manager identity must be explicitly linked by the user or by an unambiguous authenticated mapping. Do not infer that similar usernames belong to the same human.

### 6.7 Snapshot frequency

Suggested defaults, all configurable:

**Sleeper player map**
- Once per day or less unless filtered endpoints are sufficient.

**Historical draft data**
- Crawl at setup.
- Incrementally refresh same-season drafts daily leading into draft season.
- Refresh immediately before the target draft.

**ADP/rankings**
- Daily early in the offseason.
- Every 4-6 hours during the final week before major drafts.
- Explicit refresh before the target draft.
- Do not require network refresh on every pick.

**Live target draft**
- Poll completed picks every 1-2 seconds by default.
- Exponential backoff on errors.
- Degrade to manual pick entry if the source is unavailable.

### 6.8 Never overwrite historical market snapshots

Market observations are append-only. Historical draft analysis requires the market state that existed at the time of the historical draft.

For a historical pick at time `T`, choose the most recent compatible market snapshot at or before `T`, subject to a maximum staleness window. If no suitable snapshot exists, mark exact reach calculations as low confidence and rely more on coarse behavior features.

---

## 7. Canonical Player Identity

A canonical player layer is mandatory because Sleeper, FantasyPros, Yahoo, Fleaflicker, PFF, and other sources use different identifiers and naming conventions.

### 7.1 Canonical schema

```text
players
  canonical_player_id
  full_name
  normalized_name
  position
  nfl_team
  active_status

player_external_ids
  canonical_player_id
  source
  external_id
  first_seen_at
  last_seen_at
  confidence
```

Prefer stable external IDs whenever present. Fall back to normalized name + position + canonical NFL team only when necessary. Ambiguous joins should fail closed and require explicit resolution, following the same correctness philosophy already used by `ffsim` projection matching.

### 7.2 Identity requirements

- One canonical player cannot silently map to two active players from the same source.
- Position mismatches must be surfaced.
- Team changes must not break identity.
- Retired/inactive players can remain for historical drafts.
- D/ST must use team identity rather than a human-player identity model.
- All historical picks must preserve the source ID even if canonical resolution fails.

---

## 8. Historical Draft Normalization and Opportunity Sets

Raw pick frequency is not enough. The model must reconstruct what was available to the manager at each pick.

### 8.1 Pick observation

Normalize each historical pick into an observation:

```text
PickObservation
  draft_id
  pick_no
  round
  draft_slot
  manager_id
  selected_player_id
  selected_position
  roster_before_pick
  available_players_before_pick
  market_snapshot_id
  format_features
  timestamp
```

Storing the full available-player set for every historical pick may be redundant. It can be reconstructed from ordered draft picks and the initial draftable player pool. For reproducibility, store enough metadata to reconstruct it exactly.

### 8.2 Player opportunity definition

A manager-player affinity signal should only be calculated when the player was plausibly selectable.

Examples:

- Player already drafted before manager's pick -> no evidence.
- Player available and selected -> positive evidence.
- Player available and passed at a pick well before the player's market range -> weak or no negative evidence.
- Player available and passed within/after a plausible selection window -> negative evidence.
- Player selected repeatedly above market -> strong positive evidence, shrunk for sample size.

Define a configurable plausibility window using market distribution rather than a fixed `+/- 20 picks` rule when possible.

### 8.3 Repeated passes

For each manager/player pair, track:

```text
opportunities
selections
passes_in_plausible_window
average_selection_delta_vs_market
minimum_selection_delta
maximum_selection_delta
current_season_opportunities
current_season_selections
```

A player taken in 3 of 3 real opportunities is stronger evidence than a player taken in 3 of 5 drafts when the player was unavailable before the manager's pick in two of them.

### 8.4 Shared-draft correlation

Rows inside one draft are not independent because the same room, player pool, position runs, and scoring environment affect them. Backtesting/training must cluster or group by `draft_id` where appropriate. At minimum:

- Never duplicate the same draft because multiple target managers appear in it.
- Do not count one shared environment as multiple independent market observations.
- Split train/test by entire draft, not by individual pick, to avoid leakage.

---

## 9. Opponent Modeling

### 9.1 Modeling philosophy

With only a few drafts per manager, the model should be hierarchical/regularized:

```text
Global population prior
        +
League/format effects
        +
Manager-level effects
        +
Small player-specific affinity adjustments
```

A manager with almost no history behaves close to the market prior. A manager with repeated consistent evidence earns a larger personal adjustment.

### 9.2 Manager-level features

At minimum, calculate these features when data supports them:

**Board adherence**
- Mean signed delta from target-platform rank/ADP.
- Mean absolute delta.
- Distribution of reach/fall distance.
- Percent of picks within 5/10/20 spots of target board.

**Behavioral temperature / volatility**
- Managers who closely follow the board should have a low-temperature choice distribution.
- Managers who reach unpredictably should have a broader distribution.

**Position timing**
- Probability of QB/RB/WR/TE by round or normalized pick percentile.
- First QB pick distribution.
- First TE pick distribution.
- Early-round RB/WR allocation.
- Bench positional allocation.

**Roster construction**
- Zero-RB / hero-RB / heavy-RB tendencies.
- WR-heavy starts.
- Elite-QB vs late-QB tendency.
- Elite-TE vs late-TE tendency.
- Number of each position after N rounds.

**Player repetition**
- Tendency to draft the same players across multiple leagues.
- Opportunity-adjusted player affinities.
- Opportunity-adjusted player fades.

**Rookie preference**
- Rookie selection rate versus market expectation.

**NFL-team homerism**
- Selection rate for players from particular NFL teams relative to market opportunity.

**Stacking**
- QB + WR/TE same-team tendency.
- Correlated skill-position stacking if consistently observed.

**Position-run response**
- Does the manager become more likely to select a position after several consecutive room picks at that position?
- Does the manager tend to start runs by reaching ahead of market?

**Injury/risk preference**
- If data is sufficient, willingness to draft currently injured/suspended/high-variance players relative to market.

**Endgame behavior**
- K/DST timing.
- Backup QB/TE tendencies.
- Handcuff tendencies.

Not all features should be active by default. Features that do not improve backtests should be removed or strongly regularized.

### 9.3 Player-specific affinity

A conceptual affinity statistic is:

```text
Affinity(manager, player)
  ~ log( P(manager selects player | player available and plausible)
       / P(market selects player | player available and plausible) )
```

Apply Bayesian/empirical shrinkage toward zero. Two selections should nudge a probability, not create certainty.

### 9.4 Context weighting

Every historical draft receives a relevance weight. Initial heuristic dimensions:

- current season vs previous seasons
- same platform
- same scoring type
- same 1QB/superflex configuration
- similar team count
- similar roster depth
- same draft format
- similar draft date within season

Example starting season-decay values may be `1.0 / 0.35 / 0.15` for current / previous / two-years-prior, but these are initialization values only. Backtesting should tune or replace them.

### 9.5 Auto-draft / board-following likelihood

A manager who almost always takes the highest available target-platform player should be modeled as strongly board-anchored. Signals can include:

- very low absolute board deviation
- position-insensitive top-available selections
- repeated behavior across drafts

Do not assert that a human actually enabled auto-draft unless the platform exposes that fact. Model `board_following_probability`, not intent.

### 9.6 Manual intelligence

Sparse structured manual signals are valuable and should be first-class data rather than free-form notes that never affect the model.

```text
ManagerSignal
  manager_id
  signal_type       # likes_player, fades_player, early_qb, favorite_team, etc.
  target_id         # player/position/team
  strength          # weak/medium/strong or numeric prior adjustment
  confidence
  source            # direct_statement, observed, user_note
  created_at
  expires_at
  note
```

Examples:

- "Chris said this week he wants Player X."
- "Ryan always takes a QB by Round 5."
- "John is a Patriots homer."

Direct recent statements may be more predictive than old drafts, but manual signals must remain visible in explanations and easy to disable.

### 9.7 Recommended model family

Start with a regularized conditional-choice model or a transparent heuristic utility model that has the same interface.

For manager `m`, candidate player `p`, and current pick state `t`:

```text
U(m,p,t) =
    b1 * target_platform_exposure(p,t)
  + b2 * cross_platform_market(p,t)
  + b3 * manager_player_affinity(m,p)
  + b4 * manager_position_timing(m,pos(p),t)
  + b5 * roster_need(m,pos(p),t)
  + b6 * nfl_team_affinity(m,team(p))
  + b7 * rookie_affinity(m,p)
  + b8 * stacking_affinity(m,p,t)
  + b9 * live_room_shift(pos(p),t)
  + b10 * manual_signals(m,p,t)
```

Then:

```text
P(p selected | m,t) = softmax(U / temperature_m)
```

Candidate sets can be truncated to a plausible top-K market/affinity window for speed, but the selected historical player must always be included during training.

### 9.8 Future advanced option: conditional logit

A conditional multinomial logit model is a natural statistical framing because each pick is a choice from an available set. A hierarchical Bayesian version could partially pool manager parameters, but it is not required for V1. The transparent heuristic version should be implemented first and treated as a baseline that the learned model must beat.

---

## 10. Market and Multi-Platform ADP Model

### 10.1 Market data serves two jobs

**Behavioral prediction:** What will other managers likely do?

**Value comparison:** Is a player expensive/cheap relative to broader market and internal projection value?

Do not collapse all platform ADPs into one raw average.

### 10.2 Recommended normalized fields

For each player and market context:

```text
target_board_rank
target_platform_adp
consensus_adp
consensus_ecr
platform_adp_by_source
platform_median_adp
platform_trimmed_mean_adp
platform_adp_spread
platform_min_adp
platform_max_adp
source_count
source_freshness
internal_value_rank
internal_value_minus_target_rank
market_median_minus_target_rank
```

### 10.3 Distribution, not point estimate

An ADP of 50 does not mean pick 50. Model a draft-position distribution.

```text
AdpDistribution
  mean_pick
  std_dev or estimated dispersion
  scoring
  team_count
  source
  observed_at
```

If a source does not provide dispersion, estimate it from observed draft outcomes by ADP bucket, position, format, and season.

### 10.4 Target-platform exposure weighting

For a Sleeper draft, target-platform board rank or Sleeper ADP should usually have more predictive weight than another site's ADP because it is what the room sees. The exact weight must be calibrated rather than hard-coded.

Cross-platform consensus remains important because it identifies:

- players Sleeper is pushing unusually high
- players Sleeper is burying
- broad market disagreement
- cases where expert/value ranks disagree with draft-room exposure

### 10.5 Platform-specific manager priors

If a manager is explicitly known to draft primarily on another platform, their market prior may reasonably weight that platform more heavily. This is optional and must not rely on guessed identities.

### 10.6 Market movement

Track ADP velocity:

```text
adp_change_24h
adp_change_72h
adp_change_7d
```

A fast riser may have a stale season-long ADP but a much earlier current draft range. Historical manager evaluation should use time-local snapshots.

---
