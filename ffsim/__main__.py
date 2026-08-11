import argparse
import json
from dataclasses import replace
from pathlib import Path

from ffsim.config import AppConfig


def parse_args():
    parser = argparse.ArgumentParser(description="Run fantasy football season simulations.")
    parser.add_argument(
        "command", choices=("setup", "simulate", "refresh"), nargs="?", default="simulate"
    )
    parser.add_argument("--config", default="config.json")
    league = parser.add_mutually_exclusive_group()
    league.add_argument("--league-id")
    league.add_argument("--username", help="Sleeper username used to find a single NFL league")
    parser.add_argument("--season", type=int, default=2026, help="NFL season used with --username")
    parser.add_argument("--simulations", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output")
    parser.add_argument("--scenario")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--plots", action="store_true")
    output.add_argument(
        "--teams-only",
        action="store_true",
        help="skip bench-player score summaries for faster team outcome simulation",
    )
    return parser.parse_args()


def setup_league(config_path, username=None, season=2026, input_fn=input, print_fn=print):
    from ffsim.loaders.league import leagues_for_username

    username = username or input_fn("Sleeper username: ").strip()
    leagues = leagues_for_username(username, season)
    if not leagues:
        raise ValueError(f"No {season} NFL leagues found for Sleeper user {username}")

    print_fn(f"\n{season} leagues for {username}:")
    for number, league in enumerate(leagues, start=1):
        print_fn(
            f"  {number}. {league.get('name', 'Unnamed')} "
            f"[{league.get('status', 'unknown')}] ({league['league_id']})"
        )

    while True:
        choice = input_fn("Choose a league number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(leagues):
            selected = leagues[int(choice) - 1]
            break
        print_fn(f"Enter a number from 1 to {len(leagues)}.")

    path = Path(config_path)
    data = json.loads(path.read_text())
    data["league_id"] = str(selected["league_id"])
    path.write_text(json.dumps(data, indent=2) + "\n")
    print_fn(f"Saved {selected.get('name', 'Unnamed')} to {path}.")


def main():
    args = parse_args()
    if args.command == "setup":
        try:
            setup_league(args.config, args.username, args.season)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        return

    config = AppConfig.from_file(args.config)
    league_id = args.league_id or config.league_id
    if args.username:
        from ffsim.loaders.league import league_id_for_username

        try:
            league_id = league_id_for_username(args.username, args.season)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        print(f"Using Sleeper league {league_id} for {args.username} ({args.season}).")
    config = replace(
        config,
        league_id=league_id,
        simulations=config.simulations if args.simulations is None else args.simulations,
        seed=config.seed if args.seed is None else args.seed,
        results_file=args.output or config.results_file,
        scenario_file=args.scenario or config.scenario_file,
    )

    from ffsim.loaders.players import PlayerLoader

    player_loader = PlayerLoader()
    if args.command == "refresh":
        from ffsim.loaders.league import refresh_league
        from ffsim.simulation.season import refresh_matchups

        player_loader.refresh()
        refresh_league(config.league_id)
        refresh_matchups(config.league_id, config.regular_season_weeks + 3)
        return

    from ffsim.loaders.league import LeagueLoader
    from ffsim.simulation.monte_carlo import MonteCarloSimulation
    from ffsim.simulation.scenarios import apply_scenario, load_scenario

    league = LeagueLoader(config.league_id, player_loader).load_league()
    scenario = load_scenario(config.scenario_file)
    apply_scenario(league, scenario)
    league.set_replacement_levels(player_loader.enriched_players)
    simulation = MonteCarloSimulation(
        league,
        num_simulations=config.simulations,
        seed=config.seed,
        regular_season_weeks=config.regular_season_weeks,
        scenario=scenario,
        track_players=not args.teams_only,
        keep_samples=args.plots,
    )
    results = simulation.run()

    output = Path(config.results_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2) + "\n")
    simulation.tracker.print_results()
    if not args.teams_only:
        simulation.tracker.print_player_average_scores()
    if args.plots:
        from ffsim.simulation.visualizer import SimulationVisualizer

        SimulationVisualizer(league, simulation.tracker).plot_scoring_distributions()
    print(f"Results saved to {output}")


if __name__ == "__main__":
    main()
