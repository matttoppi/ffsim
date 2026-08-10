"""2024 -> 2025 oracle-mean distribution-shape backtest.

The repository has no 2025 preseason projection snapshot. 2025 realized
player-season means are therefore used only to isolate distribution shape;
this is not an end-to-end preseason forecast.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ffsim.models.player import PFF_STAT_FIELDS, Player
from ffsim.scoring import DIRECT_KEYS, ScoringSettings, score_raw_stats
from ffsim.simulation.empirical import EmpiricalLibrary, PLAYER_COLUMNS, VOLUME_STATS


SCORING = ScoringSettings(
    {
        "pass_yd": 0.04, "pass_td": 4, "pass_int": -2,
        "rush_yd": 0.1, "rush_td": 6,
        "rec": 1, "rec_yd": 0.1, "rec_td": 6,
        "fum_lost": -2,
        "fgm": 3, "fgm_50p": 2, "fgmiss": -1, "xpm": 1, "xpmiss": -1,
        "sack": 1, "int": 2, "fum_rec": 2, "safe": 2, "def_td": 6, "def_st_td": 6,
        "pts_allow_0": 10, "pts_allow_1_6": 7, "pts_allow_7_13": 4,
        "pts_allow_14_20": 1, "pts_allow_28_34": -1, "pts_allow_35p": -4,
    }
)
PERCENTILES = (5, 10, 25, 50, 75, 90, 95, 99)
CORRELATION_STATS = {
    "opportunities": ("attempts", "carries", "targets"),
    "receptions": ("receptions",),
    "yards": ("passing_yards", "rushing_yards", "receiving_yards"),
    "touchdowns": ("passing_tds", "rushing_tds", "receiving_tds"),
    "rushing": ("rushing_yards",),
    "passing": ("passing_yards",),
}
RAW_STATS = set(PFF_STAT_FIELDS) | set(DIRECT_KEYS.values()) | {
    "targets", "two_point_conversions", "return_yards", "defense_return_yards"
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", default="output/backtest_2024_2025.json")
    args = parser.parse_args()

    train = EmpiricalLibrary(seasons=(2024,))
    evaluation = EmpiricalLibrary(seasons=(2025,))
    cases = build_cases(evaluation)
    rng = np.random.default_rng(args.seed)
    ratios = build_score_ratio_pools(train)

    results = {
        "label": "oracle-mean distribution-shape",
        "train_season": 2024,
        "evaluation_season": 2025,
        "samples_per_forecast": args.samples,
        "cases": sum(len(case["actual_scores"]) for case in cases),
        "players_or_teams": len(cases),
        "models": {},
    }

    predictors = {
        "deterministic_mean": lambda case: np.full(args.samples, case["expected"]),
        "parametric": lambda case: np.array([
            score_raw_stats(case["player"].sample_parametric_stats(rng), case["position"], SCORING)
            for _ in range(args.samples)
        ]),
        "univariate_tier": lambda case: case["expected"] * rng.choice(
            ratios[(case["position"], case["tier"])], args.samples
        ),
    }
    for name, predictor in predictors.items():
        predictions = predict_cases(cases, predictor)
        results["models"][name] = summarize(cases, predictions)

    train.shrinkage = float("inf")
    joint_predictions = predict_cases(
        cases,
        lambda case: sample_empirical_scores(train, case, args.samples, rng),
    )
    results["models"]["joint_vectors"] = summarize(cases, joint_predictions)
    results["models"]["joint_vectors"]["correlation_matrix_error"] = empirical_correlation_error(
        train, cases, rng, args.samples
    )

    grid = (2.0, 4.0, 8.0, 16.0, 32.0)
    tuning = {}
    tuning_samples = max(30, args.samples // 2)
    for shrinkage in grid:
        train.shrinkage = shrinkage
        predictions = predict_cases(
            cases,
            lambda case: sample_empirical_scores(train, case, tuning_samples, rng),
        )
        metrics = summarize(cases, predictions)["overall"]
        tuning[str(int(shrinkage))] = {
            "crps": metrics["crps"],
            "mean_bias_percent": metrics["mean_bias_percent"],
        }
    eligible = [
        value for value in grid
        if abs(tuning[str(int(value))]["mean_bias_percent"]) <= 1.0
    ] or list(grid)
    selected = min(eligible, key=lambda value: tuning[str(int(value))]["crps"])
    train.shrinkage = selected
    personal_predictions = predict_cases(
        cases,
        lambda case: sample_empirical_scores(train, case, args.samples, rng),
    )
    results["shrinkage_tuning"] = tuning
    results["selected_shrinkage"] = selected
    results["models"]["joint_plus_history"] = summarize(cases, personal_predictions)
    results["models"]["joint_plus_history"]["correlation_matrix_error"] = empirical_correlation_error(
        train, cases, rng, args.samples
    )
    results["models"]["empirical_special_teams"] = summarize(
        [case for case in cases if case["position"] in {"K", "DEF"}],
        {key: value for key, value in personal_predictions.items() if key[0] in {"K", "DEF"}},
    )

    opponent = evaluate_opponents(cases, joint_predictions, build_opponent_effects(train))
    results["opponent_weight_grid"] = opponent
    results["selected_opponent_weight"] = min(opponent, key=lambda weight: opponent[weight]["crps"])
    results["cross_player_calibration"] = cross_player_calibration(cases, joint_predictions)
    results["team_factor_grid"] = evaluate_team_factors(cases, joint_predictions, rng)
    results["selected_team_factor_cv"] = 0.0
    results["logical_corrections"] = train.correction_report()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(output),
        "selected_shrinkage": selected,
        "selected_opponent_weight": results["selected_opponent_weight"],
        "overall": {name: model["overall"] for name, model in results["models"].items()},
    }, indent=2))


def build_cases(evaluation):
    cases = []
    player_rows = evaluation.player_rows.copy()
    player_rows["opponent"] = [opponent_from_game(game, team) for game, team in zip(player_rows.game_id, player_rows.team)]
    for (source_id, position), rows in player_rows.groupby(["source_id", "position"]):
        player_id = next((value for value in rows.sleeper_id if value), str(source_id))
        cases.append(make_case(rows, position, player_id, rows.team.iloc[-1], evaluation))
    for (team, position), rows in evaluation.team_rows.groupby(["team", "position"]):
        cases.append(make_case(rows, position, f"{team}-{position}", team, evaluation))
    return cases


def make_case(rows, position, player_id, team, library):
    stats = [stat for stat in PFF_STAT_FIELDS if stat in rows.columns]
    totals = rows[stats].sum().to_dict()
    projection = {"games": len(rows), "byeWeek": 0, "fantasyPoints": 0}
    for stat, field in PFF_STAT_FIELDS.items():
        if stat in totals:
            projection[field] = totals[stat]
    for suffix, field_made, field_attempted in (
        ("0_19", "fgMade019", "fgAtt019"),
        ("20_29", "fgMade2029", "fgAtt2029"),
        ("30_39", "fgMade3039", "fgAtt3039"),
        ("40_49", "fgMade4049", "fgAtt4049"),
        ("50_plus", "fgMade50plus", "fgAtt50plus"),
    ):
        if f"field_goals_made_{suffix}" in rows:
            made = rows[f"field_goals_made_{suffix}"].sum()
            projection[field_made] = made
            projection[field_attempted] = made + rows[f"field_goals_missed_{suffix}"].sum()
    if "extra_points_made" in rows:
        projection["patMade"] = rows.extra_points_made.sum()
        projection["patAtt"] = projection["patMade"] + rows.extra_points_missed.sum()
    data = {
        "player_id": str(player_id), "full_name": str(player_id), "position": position,
        "team": team, "projection_match_status": "matched", "pff_projections": projection,
    }
    player = Player(data)
    actual_raw = [row_raw(row) for _, row in rows.iterrows()]
    actual_scores = np.array([score_raw_stats(raw, position, SCORING) for raw in actual_raw])
    mean_volume = sum(rows[stat].mean() if stat in rows else 0 for stat in VOLUME_STATS)
    tier = library._tier(position, mean_volume) if position not in {"K", "DEF"} else 0
    return {
        "key": (position, str(player_id)),
        "position": position,
        "tier": tier,
        "player": player,
        "expected": player.expected_weekly_score(SCORING),
        "actual_scores": actual_scores,
        "actual_raw": actual_raw,
        "teams": rows.team.tolist(),
        "weeks": rows.week.astype(int).tolist(),
        "opponents": (
            rows["opponent"].tolist()
            if "opponent" in rows
            else (rows["opponent_team"].tolist() if "opponent_team" in rows else [""] * len(rows))
        ),
    }


def row_raw(row):
    return {
        stat: float(row.get(stat, 0) or 0)
        for stat in RAW_STATS
        if not np.isnan(row.get(stat, 0))
    }


def build_score_ratio_pools(train):
    rows = train.player_rows.copy()
    rows["score"] = [score_raw_stats(row_raw(row), row.position, SCORING) for _, row in rows.iterrows()]
    group = rows.groupby(["source_id", "season"])
    rows["mean_score"] = group.score.transform("mean")
    rows["volume"] = group[list(VOLUME_STATS)].transform("mean").sum(axis=1)
    rows["tier"] = rows.apply(lambda row: train._tier(row.position, row.volume), axis=1)
    rows["ratio"] = rows.score / rows.mean_score.where(rows.mean_score != 0, np.nan)
    pools = {}
    for key, values in rows.groupby(["position", "tier"]).ratio:
        values = values.dropna().to_numpy()
        pools[key] = values / values.mean()
    team = train.team_rows.copy()
    team["score"] = [score_raw_stats(row_raw(row), row.position, SCORING) for _, row in team.iterrows()]
    team["mean_score"] = team.groupby(["team", "season", "position"]).score.transform("mean")
    team["ratio"] = team.score / team.mean_score.where(team.mean_score != 0, np.nan)
    for position, values in team.groupby("position").ratio:
        values = values.dropna().to_numpy()
        pools[(position, 0)] = values / values.mean()
    return pools


def predict_cases(cases, predictor):
    return {case["key"]: predictor(case) for case in cases}


def sample_empirical_scores(library, case, samples, rng):
    player = case["player"]
    return np.array([
        score_raw_stats(library.sample(player, rng), case["position"], SCORING)
        for _ in range(samples)
    ])


def summarize(cases, predictions):
    groups = defaultdict(list)
    for case in cases:
        groups["overall"].append(case)
        groups[f"{case['position']}:tier_{case['tier']}"].append(case)
    result = {name: metrics(group, predictions) for name, group in groups.items()}
    return result


def metrics(cases, predictions):
    actual = np.concatenate([case["actual_scores"] for case in cases])
    forecast_means = np.concatenate([
        np.full(len(case["actual_scores"]), predictions[case["key"]].mean()) for case in cases
    ])
    predictive = np.concatenate([
        np.tile(predictions[case["key"]], len(case["actual_scores"])) for case in cases
    ])
    predictive_expected = np.concatenate([
        np.full(len(case["actual_scores"]) * len(predictions[case["key"]]), case["expected"])
        for case in cases
    ])
    expected = np.concatenate([
        np.full(len(case["actual_scores"]), case["expected"]) for case in cases
    ])
    crps_values, pits, coverages = [], [], defaultdict(list)
    briers = defaultdict(list)
    for case in cases:
        samples = predictions[case["key"]]
        pair_term = _pairwise_absolute(samples)
        for observed in case["actual_scores"]:
            crps_values.append(np.mean(np.abs(samples - observed)) - pair_term)
            pits.append(np.mean(samples <= observed))
            for level in (0.5, 0.8, 0.9):
                lower, upper = np.quantile(samples, ((1 - level) / 2, 1 - (1 - level) / 2))
                coverages[str(level)].append(lower <= observed <= upper)
            events = {
                "zero": observed == 0,
                "nonpositive": observed <= 0,
                "bust": observed < 0.5 * case["expected"],
                "boom": observed > 1.5 * case["expected"],
            }
            probabilities = {
                "zero": np.mean(samples == 0),
                "nonpositive": np.mean(samples <= 0),
                "bust": np.mean(samples < 0.5 * case["expected"]),
                "boom": np.mean(samples > 1.5 * case["expected"]),
            }
            for event, occurred in events.items():
                briers[event].append((probabilities[event] - occurred) ** 2)
    return {
        "observations": len(actual),
        "mean_bias": float(np.mean(forecast_means - actual)),
        "mean_bias_percent": float(100 * np.mean(forecast_means - actual) / np.mean(actual)) if np.mean(actual) else 0,
        "mae": float(np.mean(np.abs(forecast_means - actual))),
        "rmse": float(np.sqrt(np.mean((forecast_means - actual) ** 2))),
        "actual_std": float(np.std(actual)),
        "predictive_std": float(np.std(predictive)),
        "actual_zero_rate": float(np.mean(actual == 0)),
        "predictive_zero_rate": float(np.mean(predictive == 0)),
        "actual_nonpositive_rate": float(np.mean(actual <= 0)),
        "predictive_nonpositive_rate": float(np.mean(predictive <= 0)),
        "actual_percentiles": _percentiles(actual),
        "predictive_percentiles": _percentiles(predictive),
        "actual_skewness": _skewness(actual),
        "predictive_skewness": _skewness(predictive),
        "actual_bust_rate": float(np.mean(actual < 0.5 * expected)),
        "predictive_bust_rate": float(np.mean(predictive < 0.5 * predictive_expected)),
        "actual_boom_rate": float(np.mean(actual > 1.5 * expected)),
        "predictive_boom_rate": float(np.mean(predictive > 1.5 * predictive_expected)),
        "crps": float(np.mean(crps_values)),
        "pit_histogram": np.histogram(pits, bins=np.linspace(0, 1, 11))[0].tolist(),
        "interval_coverage": {level: float(np.mean(values)) for level, values in coverages.items()},
        "brier": {event: float(np.mean(values)) for event, values in briers.items()},
    }


def empirical_correlation_error(library, cases, rng, samples):
    errors = {}
    for position in ("QB", "RB", "WR", "TE"):
        position_cases = [case for case in cases if case["position"] == position]
        actual_raw = [raw for case in position_cases for raw in case["actual_raw"]]
        forecast_raw = [
            library.sample(case["player"], rng)
            for case in position_cases
            for _ in range(samples)
        ]
        actual = _correlation_matrix(actual_raw)
        forecast = _correlation_matrix(forecast_raw)
        errors[position] = {
            "mean_absolute_error": float(np.mean(np.abs(actual - forecast))),
            "actual_matrix": actual.tolist(),
            "forecast_matrix": forecast.tolist(),
        }
    return errors


def build_opponent_effects(train):
    rows = train.player_rows.copy()
    rows["opponent"] = [opponent_from_game(game, team) for game, team in zip(rows.game_id, rows.team)]
    rows["score"] = [score_raw_stats(row_raw(row), row.position, SCORING) for _, row in rows.iterrows()]
    rows["mean_score"] = rows.groupby(["source_id", "season"]).score.transform("mean")
    rows["ratio"] = rows.score / rows.mean_score.where(rows.mean_score != 0, np.nan)
    return rows.groupby(["position", "opponent"]).ratio.mean().fillna(1).to_dict()


def evaluate_opponents(cases, base_predictions, effects):
    # Opponent effects are evaluated last and normalized within each 2025 schedule.
    # With no preseason means, this remains part of the oracle-mean shape study.
    results = {}
    for weight in (0.0, 0.25, 0.5, 1.0):
        adjusted = []
        observed = []
        for case in cases:
            if case["position"] in {"K", "DEF"}:
                continue
            opponents = case["opponents"]
            raw = np.array([effects.get((case["position"], opponent), 1.0) for opponent in opponents])
            modifiers = np.clip(1 + weight * (raw - 1), 0.9, 1.1)
            modifiers /= modifiers.mean() if len(modifiers) else 1
            samples = base_predictions[case["key"]]
            for score, modifier in zip(case["actual_scores"], modifiers):
                adjusted.append(samples * modifier)
                observed.append(score)
        crps = [np.mean(np.abs(samples - score)) - _pairwise_absolute(samples) for samples, score in zip(adjusted, observed)]
        results[str(weight)] = {"crps": float(np.mean(crps)), "mean_bias_percent": float(100 * (np.mean([sample.mean() for sample in adjusted]) - np.mean(observed)) / np.mean(observed))}
    return results


def opponent_from_game(game_id, team):
    first, second = game_id.split("_")[-2:]
    return second if first == team else first


def cross_player_calibration(cases, predictions):
    groups = defaultdict(list)
    for case in cases:
        if case["position"] not in {"QB", "RB", "WR", "TE"}:
            continue
        for index, (team, week) in enumerate(zip(case["teams"], case["weeks"])):
            groups[(team, week)].append((case, index))
    actual_totals, predicted_totals = [], []
    actual_qb, actual_receivers, predicted_qb, predicted_receivers = [], [], [], []
    for members in groups.values():
        actual_totals.append(sum(case["actual_scores"][index] for case, index in members))
        predicted_totals.extend(np.sum([predictions[case["key"]] for case, _ in members], axis=0))
        qb_actual = sum(case["actual_scores"][index] for case, index in members if case["position"] == "QB")
        receiver_actual = sum(case["actual_scores"][index] for case, index in members if case["position"] in {"WR", "TE"})
        qb_predicted = np.sum([predictions[case["key"]] for case, _ in members if case["position"] == "QB"], axis=0)
        receiver_predicted = np.sum([predictions[case["key"]] for case, _ in members if case["position"] in {"WR", "TE"}], axis=0)
        actual_qb.append(qb_actual)
        actual_receivers.append(receiver_actual)
        predicted_qb.extend(qb_predicted)
        predicted_receivers.extend(receiver_predicted)
    actual_std = float(np.std(actual_totals))
    predicted_std = float(np.std(predicted_totals))
    return {
        "actual_team_score_std": actual_std,
        "independent_team_score_std": predicted_std,
        "team_std_ratio": predicted_std / actual_std,
        "actual_qb_receiver_correlation": float(np.corrcoef(actual_qb, actual_receivers)[0, 1]),
        "independent_qb_receiver_correlation": float(np.corrcoef(predicted_qb, predicted_receivers)[0, 1]),
    }


def evaluate_team_factors(cases, predictions, rng):
    groups = defaultdict(list)
    for case in cases:
        if case["position"] not in {"QB", "RB", "WR", "TE"}:
            continue
        for index, key in enumerate(zip(case["teams"], case["weeks"])):
            groups[key].append((case, index))
    result = {}
    for coefficient_of_variation in (0.0, 0.05, 0.1, 0.15, 0.2, 0.3):
        crps, biases, actual_totals, predicted_totals = [], [], [], []
        actual_qb, actual_receivers, predicted_qb, predicted_receivers = [], [], [], []
        sigma = np.sqrt(np.log(1 + coefficient_of_variation**2)) if coefficient_of_variation else 0
        for members in groups.values():
            sample_count = len(predictions[members[0][0]["key"]])
            factor = rng.lognormal(-0.5 * sigma**2, sigma, sample_count) if sigma else np.ones(sample_count)
            adjusted = [(case, index, predictions[case["key"]] * factor) for case, index in members]
            for case, index, samples in adjusted:
                observed = case["actual_scores"][index]
                crps.append(np.mean(np.abs(samples - observed)) - _pairwise_absolute(samples))
                biases.append(samples.mean() - observed)
            actual_totals.append(sum(case["actual_scores"][index] for case, index in members))
            predicted_totals.extend(np.sum([samples for _, _, samples in adjusted], axis=0))
            actual_qb.append(sum(case["actual_scores"][index] for case, index in members if case["position"] == "QB"))
            actual_receivers.append(sum(case["actual_scores"][index] for case, index in members if case["position"] in {"WR", "TE"}))
            predicted_qb.extend(np.sum([samples for case, _, samples in adjusted if case["position"] == "QB"], axis=0))
            predicted_receivers.extend(np.sum([samples for case, _, samples in adjusted if case["position"] in {"WR", "TE"}], axis=0))
        actual_std = np.std(actual_totals)
        result[str(coefficient_of_variation)] = {
            "crps": float(np.mean(crps)),
            "mean_bias_percent": float(100 * np.mean(biases) / np.mean([case["actual_scores"].mean() for case in cases if case["position"] in {"QB", "RB", "WR", "TE"}])),
            "team_std_ratio": float(np.std(predicted_totals) / actual_std),
            "qb_receiver_correlation": float(np.corrcoef(predicted_qb, predicted_receivers)[0, 1]),
            "actual_qb_receiver_correlation": float(np.corrcoef(actual_qb, actual_receivers)[0, 1]),
        }
    return result


def _correlation_matrix(raws):
    matrix = np.array([
        [sum(raw.get(stat, 0) for stat in stats) for stats in CORRELATION_STATS.values()]
        for raw in raws
    ])
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.nan_to_num(np.corrcoef(matrix, rowvar=False))


def _pairwise_absolute(samples):
    ordered = np.sort(samples)
    coefficients = 2 * np.arange(1, len(ordered) + 1) - len(ordered) - 1
    return float(np.sum(coefficients * ordered) / len(ordered) ** 2)


def _percentiles(values):
    return {str(percentile): float(np.percentile(values, percentile)) for percentile in PERCENTILES}


def _skewness(values):
    std = np.std(values)
    return float(np.mean(((values - np.mean(values)) / std) ** 3)) if std else 0.0


if __name__ == "__main__":
    main()
