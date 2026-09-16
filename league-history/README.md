# League History

A standalone web app for exploring Sleeper NFL dynasty rosters over time.
It lives beside FFsim and deploys independently as a static Vite site.

## Run locally

Use Node.js 22.12 or newer.

```sh
cd league-history
npm ci
npm run dev
```

Open the local URL printed by Vite. Paste a Sleeper league URL or league ID.
The example button imports Dynasty - Triton, including its 2022–2026 seasons.

```sh
npm test
npm run build
npm run preview
```

Tests use Node's built-in test runner. No Python process, FFsim configuration,
API key, database, or server function is required.

## Deploy to Vercel

1. Push the app directory to your FFsim Git repository.
2. In Vercel, create a project from that repository. Select the branch that
   contains this app.
3. Set **Root Directory** to `league-history`.
4. Select **Vite** as the framework and Node.js **22.x**.
5. Use **Install Command** `npm ci`, **Build Command** `npm run build`, and
   **Output Directory** `dist`.
6. Deploy. No environment variables are needed.
7. Open the production URL, import your league, and use **Copy this view** to
   share the league and selected date. Recipients import the data in their own
   browsers. They do not need access to the FFsim repository or a Vercel account.

`vercel.json` includes the build settings. URLs use query parameters, so the
app does not need a server route or a single-page routing rewrite.

This static, personal league viewer is designed for Vercel Hobby. Hobby usage
limits still apply. See [Vercel Hobby](https://vercel.com/docs/plans/hobby) and
[Vite on Vercel](https://vercel.com/docs/frameworks/frontend/vite).

## What the viewer shows

- All available linked seasons, followed through `previous_league_id`.
- A continuous date slider, date picker, season shortcuts, and event stepping.
- Every team's owned players, with player and team search.
- Completed trades, waivers, free-agent moves, commissioner moves, and drafts.
- Player, draft-pick, and waiver-budget transfers in the activity details.
- Share links that preserve the league ID and selected timestamp.

The app makes read-only requests directly to `https://api.sleeper.app/v1`.
Requests start at least 150 milliseconds apart, with at most three concurrent
league requests. The NFL transaction scan includes buckets 0 through 22 and
does not stop at an empty bucket. Repeated transaction IDs are deduplicated.
Failed requests stop the import; the app does not substitute an empty season.
The player catalog is cached for 24 hours in the browser when storage is
available. League history remains in memory until the page closes or reloads.

## Reconstruction and source limits

Each season starts from its retrieved roster snapshot. To show an earlier
time, the app reverses later completed changes. All sides of a trade change
together. Only completion timestamps determine transaction order. Draft
results supply newly drafted players; keeper entries are not new acquisitions.
Roster membership includes reserve and taxi players, but does not assign their
historical lineup slots.

The app checks incoming owners, outgoing owners, duplicate ownership, and
unknown roster references during replay. It also compares a closing roster
with the next season's reconstructed opening roster. An unexplained boundary
change hides rosters in that gap. These consistency checks cannot prove that
Sleeper retained every transaction. The API responses are not an atomic
snapshot; import again if an active league changes during collection.

Sleeper's sampled draft results have no individual pick timestamps. The app
therefore hides rosters between draft start and completion. It groups drafted
players at draft start only for reconstruction outside that interval. This
allows trades during a slow draft to reverse correctly. Conflicting changes
with the same timestamp also remain unresolved.

Team names and managers come from each retrieved season, not a dated rename
or ownership log. Player names and positions use the latest catalog, including
inactive players. Individual pick inventories, complete waiver-budget balances,
historical starting lineups, standings, and precise reserve/taxi placement are
outside this version. Pick and budget transfers remain visible in activity.

Source checks on 2026-09-16:

- Browser requests to the league and player endpoints accept cross-origin
  access. No authentication is required for these public endpoints.
- Dynasty - Triton links five seasons, from 2022 through 2026.
- All 1,776 completed transaction/draft event boundaries passed player replay
  consistency checks. Reversing the 2022 startup draft produces empty rosters.
- Two renewal boundaries differ by one player membership each. The app exposes
  these gaps instead of inventing a change date.

See the [Sleeper API documentation](https://docs.sleeper.com/). Sleeper permits
non-commercial use without an API token. Commercial API use requires a
separate arrangement with Sleeper.

## Relationship to FFsim

The app uses FFsim's existing source conventions: season-qualified rosters,
stable Sleeper player IDs, prior-season links, complete transaction status,
atomic trade sides, and explicit source gaps. The small TypeScript importer
runs in the browser so deployment does not require FFsim's Python client or
research database. It does not import simulation, projection, or licensed
FantasyPros data.
