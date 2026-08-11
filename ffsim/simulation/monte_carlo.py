import numpy as np
from tqdm import tqdm
from ffsim.models.team import FLEX_ELIGIBILITY
from ffsim.simulation.season import SimulationSeason
from ffsim.simulation.tracker import SimulationTracker


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
    ):
        self.league = league
        self.num_simulations = num_simulations
        self.seed = seed
        self.regular_season_weeks = regular_season_weeks
        self.scenario = scenario or {}
        self.track_players = track_players
        self.keep_samples = keep_samples
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
        kwargs = {"scenario": self.scenario} if self.scenario else {}
        season = SimulationSeason(
            self.league,
            self.tracker,
            self.regular_season_weeks,
            np.random.default_rng(streams[0]),
            **kwargs,
        )
        for stream in tqdm(streams, desc="Running Simulations", unit="sim"):
            for team in self.league.rosters:
                team.reset_stats()

            season.rng = np.random.default_rng(stream)
            season.simulate()
            self.record_season_results(season)

        self.tracker.calculate_averages()
        results = self.tracker.to_dict(self.seed)
        if self.scenario:
            results["scenario"] = self.scenario
        if not self.track_players:
            results["team_only"] = True
        return results

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
