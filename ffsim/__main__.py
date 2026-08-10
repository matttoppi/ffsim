import argparse
import json
from dataclasses import replace
from pathlib import Path

from ffsim.config import AppConfig


def parse_args():
    parser = argparse.ArgumentParser(description="Run fantasy football season simulations.")
    parser.add_argument("command", choices=("simulate", "refresh"), nargs="?", default="simulate")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--league-id")
    parser.add_argument("--simulations", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output")
    parser.add_argument("--plots", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    config = AppConfig.from_file(args.config)
    config = replace(
        config,
        league_id=args.league_id or config.league_id,
        simulations=config.simulations if args.simulations is None else args.simulations,
        seed=config.seed if args.seed is None else args.seed,
        results_file=args.output or config.results_file,
    )

    from ffsim.loaders.players import PlayerLoader

    player_loader = PlayerLoader()
    if args.command == "refresh":
        from ffsim.loaders.league import refresh_league
        from ffsim.simulation.season import refresh_matchups

        player_loader.refresh()
        refresh_league(config.league_id)
        refresh_matchups(config.league_id, config.regular_season_weeks)
        return

    from ffsim.loaders.league import LeagueLoader
    from ffsim.simulation.monte_carlo import MonteCarloSimulation

    league = LeagueLoader(config.league_id, player_loader).load_league()
    simulation = MonteCarloSimulation(
        league,
        num_simulations=config.simulations,
        seed=config.seed,
        regular_season_weeks=config.regular_season_weeks,
    )
    results = simulation.run()

    output = Path(config.results_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2) + "\n")
    simulation.tracker.print_results()
    simulation.tracker.print_player_average_scores()
    if args.plots:
        simulation.visualizer.plot_scoring_distributions()
    print(f"Results saved to {output}")


if __name__ == "__main__":
    main()
