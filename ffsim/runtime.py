"""Shared construction of a simulation from cached inputs."""

from ffsim.loaders.league import LeagueLoader
from ffsim.loaders.players import PlayerLoader
from ffsim.simulation.monte_carlo import MonteCarloSimulation
from ffsim.simulation.scenarios import apply_scenario, load_scenario


def create_simulation(config, *, workers=1, track_players=True, keep_samples=False):
    player_loader = PlayerLoader()
    league = LeagueLoader(config.league_id, player_loader).load_league()
    scenario = load_scenario(config.scenario_file)
    apply_scenario(league, scenario)
    league.set_replacement_levels(player_loader.enriched_players)
    return MonteCarloSimulation(
        league,
        num_simulations=config.simulations,
        seed=config.seed,
        regular_season_weeks=config.regular_season_weeks,
        scenario=scenario,
        track_players=track_players,
        keep_samples=keep_samples,
        workers=workers,
    )
