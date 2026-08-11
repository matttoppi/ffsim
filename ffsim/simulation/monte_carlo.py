import numpy as np
from tqdm import tqdm
from ffsim.models.team import FLEX_ELIGIBILITY
from ffsim.simulation.season import SimulationSeason
from ffsim.simulation.tracker import SimulationTracker


_WORKER_SIMULATION = None
_WORKER_PROGRESS = None


def _initialize_worker(simulation, progress):
    global _WORKER_SIMULATION, _WORKER_PROGRESS
    _WORKER_SIMULATION = simulation
    _WORKER_PROGRESS = progress


def _run_worker(streams):
    simulation = _WORKER_SIMULATION
    simulation.tracker = simulation._new_tracker()
    simulation._run_streams(streams, progress_counter=_WORKER_PROGRESS)
    return simulation.tracker.worker_state()


class MonteCarloSimulation:
    def __init__(
        self,
        league,
        num_simulations=300,
        seed=2026,
        regular_season_weeks=14,
        scenario=None,
        track_players=True,
        keep_samples=False,
        workers=1,
    ):
        self.league = league
        self.num_simulations = num_simulations
        self.seed = seed
        self.regular_season_weeks = regular_season_weeks
        self.scenario = scenario or {}
        self.track_players = track_players
        self.keep_samples = keep_samples
        if workers < 1:
            raise ValueError("workers must be positive")
        self.workers = workers
        self.tracker = self._new_tracker()

    def _new_tracker(self):
        return SimulationTracker(
            self.league,
            self.num_simulations,
            self.regular_season_weeks,
            track_players=self.track_players,
            keep_samples=self.keep_samples,
        )

    def report_lineup_gaps(self):
        slots = self.league.roster_slots
        for team in self.league.rosters:
            unprojected = [player for player in team.players if not player.pff_projections]
            remaining = [player for player in team.players if player.pff_projections]
            gaps = []
            for flex_pass in (False, True):
                for position, count in slots.items():
                    if (position in FLEX_ELIGIBILITY) != flex_pass:
                        continue
                    eligible = FLEX_ELIGIBILITY.get(position, {position})
                    matches = [player for player in remaining if player.position in eligible]
                    if len(matches) < count:
                        gaps.append(f"{position} ({len(matches)}/{count})")
                    for player in matches[:count]:
                        remaining.remove(player)
            if gaps:
                print(
                    f"WARNING: {team.name} cannot fill required slots even fully healthy: "
                    f"{', '.join(gaps)} — replacement-level streamers will be used."
                )
            if unprojected:
                names = ", ".join(sorted(player.name for player in unprojected))
                print(f"NOTE: {team.name} has {len(unprojected)} rostered players without projections (always 0): {names}")

    def run(self):
        self.report_lineup_gaps()
        self.tracker = self._new_tracker()
        streams = np.random.SeedSequence(self.seed).spawn(self.num_simulations)
        if self.workers == 1:
            self._run_streams(streams, progress=True)
        else:
            self._run_parallel(streams)

        self.tracker.calculate_averages()
        results = self.tracker.to_dict(self.seed)
        if self.scenario:
            results["scenario"] = self.scenario
        if not self.track_players:
            results["team_only"] = True
        return results

    def _run_streams(self, streams, progress=False, progress_counter=None):
        kwargs = {"scenario": self.scenario} if self.scenario else {}
        season = SimulationSeason(
            self.league,
            self.tracker,
            self.regular_season_weeks,
            np.random.default_rng(streams[0]),
            **kwargs,
        )
        iterator = tqdm(streams, desc="Running Simulations", unit="sim") if progress else streams
        for stream in iterator:
            for team in self.league.rosters:
                team.reset_stats()

            season.rng = np.random.default_rng(stream)
            season.simulate()
            self.record_season_results(season)
            if progress_counter is not None:
                with progress_counter.get_lock():
                    progress_counter.value += 1

    def _run_parallel(self, streams):
        import multiprocessing as mp
        import time

        workers = min(self.workers, len(streams))
        chunk_size = (len(streams) + workers - 1) // workers
        chunks = [streams[start:start + chunk_size] for start in range(0, len(streams), chunk_size)]
        method = "forkserver" if "forkserver" in mp.get_all_start_methods() else "spawn"
        context = mp.get_context(method)
        completed = context.Value("i", 0)
        with context.Pool(
            workers, initializer=_initialize_worker, initargs=(self, completed)
        ) as pool:
            results = [pool.apply_async(_run_worker, (chunk,)) for chunk in chunks]
            with tqdm(total=len(streams), desc="Running Simulations", unit="sim") as progress:
                while not all(result.ready() for result in results):
                    progress.update(completed.value - progress.n)
                    time.sleep(0.05)
                progress.update(completed.value - progress.n)
            states = [result.get() for result in results]
        for state in states:
            self.tracker.merge_worker_state(state)

    def record_season_results(self, season):
        standings = sorted(
            self.league.rosters, key=lambda team: (team.wins, team.points_for), reverse=True
        )
        for seed, team in enumerate(standings, 1):
            self.tracker.record_team_season(team.name, team.wins, team.points_for, seed)

        playoff_sim = season.playoff_sim
        self.tracker.record_playoff_results(
            playoff_sim.bracket.teams,
            [playoff_sim.bracket.division1_winner, playoff_sim.bracket.division2_winner],
            playoff_sim.champion,
        )
