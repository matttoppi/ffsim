import hashlib
import json
import math
import os
import random
from collections import defaultdict
from pathlib import Path

from .hdvn_evaluation import (
    ALLOWED_STATUSES,
    EVALUATION_VERSION,
    evaluate_predictions,
)
from .hdvn_labels import load_team_partition
from .hdvn_snapshot import canonical_json, sha256_file


BASELINE_BUNDLE_VERSION = "hdvn-baselines-v1"
SEED = 20260828
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF", "UNKNOWN")
SCORING_FORMATS = ("STD", "HALF_PPR", "PPR")
CONTEXT_FEATURES = (
    "season",
    "team_count",
    "draft_slot",
    "round_count",
    *(f"scoring_{value}" for value in SCORING_FORMATS),
    *(f"roster_slot_{value}" for value in ("QB", "RB", "WR", "TE", "FLEX", "BN")),
)
MARKET_FEATURES = (
    *CONTEXT_FEATURES,
    "cumulative_market_value",
    "market_support_drafts",
    "market_pick_coverage",
    "market_rank_mean",
    "market_adp_mean",
    "market_value_mean",
    "market_value_std",
)
FULL_FEATURES = (
    *MARKET_FEATURES,
    "first_qb_round",
    "first_rb_round",
    "first_wr_round",
    "first_te_round",
    "starter_slots",
    "starter_covered",
    "flex_slots",
    "flex_covered",
    *(f"count_r{round_}_{position}" for round_ in (3, 5, 8) for position in POSITIONS),
    *(f"count_total_{position}" for position in POSITIONS),
    *(f"bench_{position}" for position in POSITIONS),
)
MODEL_FEATURES = {
    "draft_slot_and_context": CONTEXT_FEATURES,
    "historical_market_value": MARKET_FEATURES,
    "regularized_linear_logistic": FULL_FEATURES,
    "gradient_boosted_tree": FULL_FEATURES,
}
LIMITATIONS = [
    "market_and_construction_only",
    "point-in-time historical projections are unavailable",
    "current projection value is not substituted",
    "deterministic projection lookahead is unavailable without historical projection provenance",
    "coupled ffsim terminal rollouts are unavailable without historical projection provenance",
    "validation metrics are 2024 only; the locked 2025 partition was not loaded",
]


def fit_baselines(
    split_manifest,
    output_directory,
    *,
    source_snapshot_hash,
    feature_manifest_hash,
    label_manifest_hash,
    tables_manifest_hash,
    market_manifest_hash,
    command,
    code_revision,
    seed=SEED,
    bootstrap_samples=200,
):
    output_directory = Path(output_directory).resolve()
    model_path = output_directory / "models.joblib"
    prediction_path = output_directory / "predictions-2024.parquet"
    report_path = output_directory / "validation-report.json"
    manifest_path = output_directory / "baseline-bundle.manifest.json"
    paths = (model_path, prediction_path, report_path, manifest_path)
    if any(path.exists() for path in paths):
        raise FileExistsError(f"immutable baseline output already exists: {output_directory}")
    if bootstrap_samples < 2:
        raise ValueError("bootstrap needs at least two samples")
    output_directory.mkdir(parents=True, exist_ok=True)

    train_rows = list(load_team_partition(split_manifest, "train"))
    validation_rows = list(load_team_partition(split_manifest, "validation"))
    if not train_rows or not validation_rows:
        raise ValueError("baseline split is empty")
    if any(int(row["season"]) == 2025 for row in (*train_rows, *validation_rows)):
        raise ValueError("locked 2025 rows entered baseline fitting")

    try:
        import joblib
        import numpy as np
        import pyarrow as pa
        import pyarrow.parquet as pq
        from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
        from sklearn.dummy import DummyClassifier
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression, Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as error:
        raise RuntimeError("baseline fitting requires pinned research dependencies") from error

    extracted_train = [_extract_features(row) for row in train_rows]
    extracted_validation = [_extract_features(row) for row in validation_rows]
    y_points = np.asarray([row["points_for_percentile"] for row in train_rows], dtype=float)
    y_playoff = np.asarray([row["made_playoffs"] for row in train_rows], dtype=int)
    y_champion = np.asarray([row["champion"] for row in train_rows], dtype=int)
    artifacts = {}
    prediction_sets = {}

    train_mean_points = float(np.mean(y_points))
    train_mean_playoff = float(np.mean(y_playoff))
    uniform = []
    for row in validation_rows:
        uniform.append(_prediction_row(
            row,
            train_mean_points,
            train_mean_playoff,
            1.0 / int(row["team_count"]),
            missing_features=False,
        ))
    prediction_sets["uniform_championship"] = uniform
    artifacts["uniform_championship"] = {
        "status": "research",
        "model": "uniform 1 / team_count championship; train means for non-championship heads",
        "feature_order": [],
        "championship_temperature": None,
    }

    for name, feature_order in MODEL_FEATURES.items():
        x_train = _matrix(extracted_train, feature_order, np)
        x_validation = _matrix(extracted_validation, feature_order, np)
        if name == "gradient_boosted_tree":
            point_model = make_pipeline(
                SimpleImputer(strategy="median", keep_empty_features=True),
                HistGradientBoostingRegressor(
                    max_iter=100,
                    max_leaf_nodes=15,
                    l2_regularization=1.0,
                    random_state=seed,
                ),
            )
            playoff_model = make_pipeline(
                SimpleImputer(strategy="median", keep_empty_features=True),
                HistGradientBoostingClassifier(
                    max_iter=100,
                    max_leaf_nodes=15,
                    l2_regularization=1.0,
                    random_state=seed,
                ),
            )
            champion_model = make_pipeline(
                SimpleImputer(strategy="median", keep_empty_features=True),
                HistGradientBoostingClassifier(
                    max_iter=100,
                    max_leaf_nodes=15,
                    l2_regularization=1.0,
                    random_state=seed,
                ),
            )
        else:
            point_model = make_pipeline(
                SimpleImputer(strategy="median", keep_empty_features=True),
                StandardScaler(),
                Ridge(alpha=10.0),
            )
            playoff_model = make_pipeline(
                SimpleImputer(strategy="median", keep_empty_features=True),
                StandardScaler(),
                LogisticRegression(C=0.1, max_iter=1000, random_state=seed),
            )
            champion_model = make_pipeline(
                SimpleImputer(strategy="median", keep_empty_features=True),
                StandardScaler(),
                LogisticRegression(C=0.1, max_iter=1000, random_state=seed),
            )
        if np.unique(y_playoff).size < 2:
            playoff_model = DummyClassifier(
                strategy="constant",
                constant=int(y_playoff[0]),
            )
        if np.unique(y_champion).size < 2:
            champion_model = DummyClassifier(
                strategy="constant",
                constant=int(y_champion[0]),
            )
        point_model.fit(x_train, y_points)
        playoff_model.fit(x_train, y_playoff)
        champion_model.fit(x_train, y_champion)
        points = point_model.predict(x_validation)
        playoff = _positive_probability(playoff_model, x_validation, np)
        champion_probability = _positive_probability(champion_model, x_validation, np)
        logits = np.log(np.clip(champion_probability, 1e-15, 1 - 1e-15)) - np.log1p(
            -np.clip(champion_probability, 1e-15, 1 - 1e-15)
        )
        temperature = _select_temperature(validation_rows, logits)
        champion = _within_league_softmax(validation_rows, logits / temperature)
        predictions = [
            _prediction_row(
                row,
                min(max(float(point), 0.0), 100.0),
                min(max(float(playoff_probability), 1e-15), 1 - 1e-15),
                champion_probability,
                missing_features=(
                    name != "draft_slot_and_context"
                    and features["market_pick_coverage"] == 0.0
                ),
            )
            for row, features, point, playoff_probability, champion_probability in zip(
                validation_rows,
                extracted_validation,
                points,
                playoff,
                champion,
            )
        ]
        prediction_sets[name] = predictions
        artifacts[name] = {
            "status": "research",
            "model": (
                "histogram gradient boosted trees"
                if name == "gradient_boosted_tree"
                else "ridge points and regularized logistic playoff/champion"
            ),
            "feature_order": list(feature_order),
            "championship_temperature": temperature,
            "point_model": point_model,
            "playoff_model": playoff_model,
            "champion_model": champion_model,
        }

    report = {
        "evaluation_version": EVALUATION_VERSION,
        "validation_year": 2024,
        "locked_test_loaded": False,
        "baselines": {},
    }
    prediction_rows = []
    for index, (name, predictions) in enumerate(prediction_sets.items()):
        metrics = evaluate_predictions(predictions)
        report["baselines"][name] = {
            "status": "research",
            "metrics": metrics,
            "bootstrap": _clustered_bootstrap_metrics(
                predictions,
                seed=seed + index,
                samples=bootstrap_samples,
            ),
            "slices": _baseline_slices(predictions),
        }
        prediction_rows.extend({"baseline": name, **row} for row in predictions)

    serializable_artifacts = {
        name: {
            key: value
            for key, value in artifact.items()
            if key not in {"point_model", "playoff_model", "champion_model"}
        }
        for name, artifact in artifacts.items()
    }
    model_bundle = {
        "bundle_version": BASELINE_BUNDLE_VERSION,
        "seed": seed,
        "feature_orders": {name: list(order) for name, order in MODEL_FEATURES.items()},
        "artifacts": artifacts,
    }
    joblib.dump(model_bundle, model_path, compress=3)
    pq.write_table(pa.Table.from_pylist(prediction_rows), prediction_path, compression="zstd")
    report_path.write_text(canonical_json(report) + "\n")

    manifest = {
        "bundle_version": BASELINE_BUNDLE_VERSION,
        "evaluation_version": EVALUATION_VERSION,
        "code_revision": code_revision,
        "code_sha256": sha256_file(Path(__file__)),
        "source_snapshot_sha256": source_snapshot_hash,
        "feature_manifest_hash": feature_manifest_hash,
        "label_manifest_hash": label_manifest_hash,
        "tables_manifest_hash": tables_manifest_hash,
        "market_manifest_hash": market_manifest_hash,
        "split_manifest_hash": json.loads(Path(split_manifest).read_text())["sha256"],
        "seed": seed,
        "bootstrap_samples": bootstrap_samples,
        "deterministic_feature_order": {
            name: list(order) for name, order in MODEL_FEATURES.items()
        },
        "loaded_partitions": ["train", "validation"],
        "locked_test_loaded": False,
        "counts": {
            "train_rows": len(train_rows),
            "validation_rows": len(validation_rows),
            "train_league_seasons": len({_league_key(row) for row in train_rows}),
            "validation_league_seasons": len({_league_key(row) for row in validation_rows}),
        },
        "artifacts": serializable_artifacts,
        "limitations": LIMITATIONS,
        "command": command,
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in (model_path, prediction_path, report_path)
        },
    }
    if any(artifact["status"] not in ALLOWED_STATUSES for artifact in artifacts.values()):
        raise ValueError("baseline artifact has invalid status")
    manifest["sha256"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    manifest_path.write_text(canonical_json(manifest) + "\n")
    for path in paths:
        path.chmod(0o444)
    return manifest


def load_baseline_bundle(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("baseline manifest is malformed") from error
    stored_hash = manifest.get("sha256")
    body = {key: value for key, value in manifest.items() if key != "sha256"}
    if stored_hash != hashlib.sha256(canonical_json(body).encode()).hexdigest():
        raise ValueError("baseline manifest hash mismatch")
    if manifest.get("locked_test_loaded") is not False:
        raise ValueError("baseline artifact touched locked test")
    for artifact in manifest.get("artifacts", {}).values():
        if artifact.get("status") not in ALLOWED_STATUSES:
            raise ValueError("baseline artifact status is invalid")
    for filename, record in manifest.get("files", {}).items():
        if sha256_file(manifest_path.parent / filename) != record["sha256"]:
            raise ValueError(f"baseline artifact file hash mismatch: {filename}")
    for key, value in (expected or {}).items():
        if manifest.get(key) != value:
            raise ValueError(f"baseline context mismatch for {key}")
    return manifest


def _extract_features(row):
    roster_slots = _counts(json.loads(row["roster_positions_json"]))
    rank_values = _numbers(json.loads(row["market_rank_by_pick_json"]))
    adp_values = _numbers(json.loads(row["market_adp_by_pick_json"]))
    market_values = _numbers(json.loads(row["market_value_by_pick_json"]))
    pick_count = len(json.loads(row["pick_numbers_json"]))
    values = {
        "season": float(row["season"]),
        "team_count": float(row["team_count"]),
        "draft_slot": _float(row["draft_slot"]),
        "round_count": float(row["round_count"]),
        "cumulative_market_value": float(row["cumulative_market_value"]),
        "market_support_drafts": float(row["market_support_drafts"]),
        "market_pick_coverage": len(rank_values) / pick_count if pick_count else 0.0,
        "market_rank_mean": _mean(rank_values),
        "market_adp_mean": _mean(adp_values),
        "market_value_mean": _mean(market_values),
        "market_value_std": _std(market_values),
        "first_qb_round": _float(row["first_qb_round"]),
        "first_rb_round": _float(row["first_rb_round"]),
        "first_wr_round": _float(row["first_wr_round"]),
        "first_te_round": _float(row["first_te_round"]),
        "starter_slots": float(row["starter_slots"]),
        "starter_covered": float(row["starter_covered"]),
        "flex_slots": float(row["flex_slots"]),
        "flex_covered": float(row["flex_covered"]),
    }
    values.update({f"scoring_{name}": float(row["scoring_format"] == name) for name in SCORING_FORMATS})
    values.update({f"roster_slot_{name}": float(roster_slots.get(name, 0)) for name in ("QB", "RB", "WR", "TE", "FLEX", "BN")})
    for round_ in (3, 5, 8):
        counts = json.loads(row[f"position_counts_r{round_}_json"])
        values.update({f"count_r{round_}_{position}": float(counts.get(position, 0)) for position in POSITIONS})
    total = json.loads(row["position_counts_json"])
    bench = json.loads(row["bench_structure_json"])
    values.update({f"count_total_{position}": float(total.get(position, 0)) for position in POSITIONS})
    values.update({f"bench_{position}": float(bench.get(position, 0)) for position in POSITIONS})
    return values


def _matrix(rows, feature_order, np):
    return np.asarray(
        [[row.get(feature, float("nan")) for feature in feature_order] for row in rows],
        dtype=float,
    )


def _prediction_row(row, points, playoff, champion, *, missing_features):
    return {
        "league_season_id": _league_key(row),
        "league_id": row["league_id"],
        "season": int(row["season"]),
        "team_count": int(row["team_count"]),
        "scoring_format": row["scoring_format"],
        "draft_slot": row["draft_slot"],
        "roster_id": int(row["roster_id"]),
        "points_for_percentile": float(row["points_for_percentile"]),
        "made_playoffs": int(row["made_playoffs"]),
        "champion": int(row["champion"]),
        "predicted_points_for_percentile": float(points),
        "predicted_playoff": float(playoff),
        "predicted_champion": float(champion),
        "missing_features": bool(missing_features),
    }


def _within_league_softmax(rows, logits):
    output = [0.0] * len(rows)
    leagues = defaultdict(list)
    for index, row in enumerate(rows):
        leagues[_league_key(row)].append(index)
    for indices in leagues.values():
        maximum = max(float(logits[index]) for index in indices)
        weights = [math.exp(float(logits[index]) - maximum) for index in indices]
        total = sum(weights)
        for index, weight in zip(indices, weights):
            output[index] = weight / total
    return output


def _select_temperature(rows, logits):
    best = None
    for temperature in (0.5, 0.75, 1.0, 1.5, 2.0):
        probabilities = _within_league_softmax(rows, logits / temperature)
        loss = _champion_log_loss(rows, probabilities)
        candidate = (loss, temperature)
        if best is None or candidate < best:
            best = candidate
    return best[1]


def _champion_log_loss(rows, probabilities):
    losses = [
        -math.log(max(float(probability), 1e-15))
        for row, probability in zip(rows, probabilities)
        if row["champion"] == 1
    ]
    return sum(losses) / len(losses)


def _positive_probability(model, matrix, np):
    classes = list(model.classes_)
    probabilities = model.predict_proba(matrix)
    if 1 not in classes:
        return np.zeros(matrix.shape[0], dtype=float)
    return probabilities[:, classes.index(1)]


def _clustered_bootstrap_metrics(rows, *, seed, samples, confidence=0.95):
    clusters = defaultdict(list)
    for row in rows:
        clusters[_league_key(row)].append(row)
    keys = sorted(clusters)
    rng = random.Random(seed)
    values = defaultdict(list)
    for _ in range(samples):
        sampled = []
        for draw in range(len(keys)):
            source = rng.choice(keys)
            sampled.extend(clusters[source])
        metrics = _core_metrics(sampled)
        for name, value in metrics.items():
            values[name].append(value)
    estimates = _core_metrics(rows)
    tail = (1 - confidence) / 2
    result = {}
    for name, samples_for_metric in values.items():
        samples_for_metric.sort()
        result[name] = {
            "estimate": estimates[name],
            "low": samples_for_metric[max(0, int(tail * samples))],
            "high": samples_for_metric[min(samples - 1, math.ceil((1 - tail) * samples) - 1)],
            "samples": samples,
            "seed": seed,
        }
    return result


def _core_metrics(rows):
    point_errors = [row["predicted_points_for_percentile"] - row["points_for_percentile"] for row in rows]
    playoff_errors = [row["predicted_playoff"] - row["made_playoffs"] for row in rows]
    champion_losses = [
        -math.log(max(row["predicted_champion"], 1e-15))
        for row in rows
        if row["champion"] == 1
    ]
    return {
        "points_mae": sum(abs(value) for value in point_errors) / len(point_errors),
        "points_rmse": math.sqrt(sum(value * value for value in point_errors) / len(point_errors)),
        "playoff_log_loss": sum(
            -(row["made_playoffs"] * math.log(max(row["predicted_playoff"], 1e-15))
              + (1 - row["made_playoffs"]) * math.log(max(1 - row["predicted_playoff"], 1e-15)))
            for row in rows
        ) / len(rows),
        "playoff_brier": sum(value * value for value in playoff_errors) / len(playoff_errors),
        "championship_log_loss": (
            sum(champion_losses) / len(champion_losses)
            if champion_losses
            else None
        ),
    }


def _league_key(row):
    return row.get("league_season_id") or f"{row['season']}:{row['league_id']}"


def _counts(values):
    result = defaultdict(int)
    for value in values:
        result[value] += 1
    return result


def _numbers(values):
    return [float(value) for value in values if value is not None]


def _float(value):
    return float(value) if value is not None else float("nan")


def _mean(values):
    return sum(values) / len(values) if values else float("nan")


def _std(values):
    if len(values) < 2:
        return float("nan")
    mean = _mean(values)
    return math.sqrt(
        sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    )
def _baseline_slices(rows):
    grouped = defaultdict(list)
    for row in rows:
        for field in ("season", "scoring_format", "team_count", "draft_slot"):
            grouped[(field, row[field])].append(row)
    return [
        {
            "field": field,
            "value": value,
            "rows": len(group),
            "league_seasons": len({_league_key(row) for row in group}),
            "metrics": _core_metrics(group),
            "missing_feature_rows": sum(bool(row["missing_features"]) for row in group),
        }
        for (field, value), group in sorted(
            grouped.items(),
            key=lambda item: (item[0][0], str(item[0][1])),
        )
    ]


