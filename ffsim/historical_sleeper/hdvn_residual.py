import hashlib
import json
import math
import random
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import numpy as np

from .hdvn_baselines import FULL_FEATURES, MARKET_FEATURES, _extract_features, _matrix
from .hdvn_labels import load_team_partition
from .hdvn_neural import (
    ARCHITECTURE,
    CONTEXT_FEATURE_ORDER,
    LOSS_WEIGHTS,
    OPTIMIZER,
    PICK_FEATURE_ORDER,
    SEED,
    STOPPING_RULE,
    CompletedDraftNetwork,
    _adam_step,
    _build_dataset,
    _league_groups,
    fit_normalizer,
    normalize_inputs,
)
from .hdvn_snapshot import canonical_json, sha256_file


RESIDUAL_ARTIFACT_VERSION = "hdvn-residual-alpha-v1"
GATE_MINIMUM_IMPROVEMENT = 0.05
BOOTSTRAP_SAMPLES = 200
FOLDS = (
    {"name": "train-2021_validate-2022", "train_years": (2021,), "validation_year": 2022},
    {"name": "train-2021-2022_validate-2023", "train_years": (2021, 2022), "validation_year": 2023},
)
ROSTER_FEATURE_ORDER = tuple(feature for feature in FULL_FEATURES if feature not in MARKET_FEATURES)
METHODS = ("roster_ridge", "sequence_ridge", "combined_ridge", "sequence_neural")
LIMITATIONS = (
    "training-year discovery only",
    "2024 validation file was not opened",
    "2025 locked-test file was not opened",
    "point-in-time historical projections are unavailable",
    "market-and-construction inputs only",
    "no ensemble or broad model search",
    "offline research only; no live eligibility",
)


def load_train_only(split_manifest_path, *, expected):
    split_manifest_path = Path(split_manifest_path).resolve()
    manifest = _load_hashed_json(split_manifest_path, "split manifest")
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"split context mismatch for {key}")
    if manifest.get("years", {}).get("train") != [2021, 2022, 2023]:
        raise ValueError("residual discovery requires the frozen 2021-2023 train partition")
    record = manifest["partition_files"]["train"]
    train_path = (split_manifest_path.parent / record["path"]).resolve()
    if sha256_file(train_path) != record["sha256"]:
        raise ValueError("train partition file hash mismatch")
    rows = list(load_team_partition(split_manifest_path, "train"))
    if not rows or {int(row["season"]) for row in rows} - {2021, 2022, 2023}:
        raise ValueError("train partition contains an invalid residual-discovery season")
    if any(row["feature_manifest_hash"] != expected["feature_manifest_hash"] for row in rows):
        raise ValueError("train row feature hash mismatch")
    max_picks = max(len(json.loads(row["position_sequence_json"])) for row in rows)
    dataset = _build_dataset("train", rows, max_picks)
    return rows, dataset, manifest, str(train_path)


def run_residual_alpha(
    split_manifest,
    output_directory,
    *,
    source_snapshot_hash,
    feature_manifest_hash,
    market_manifest_hash,
    tables_manifest_hash,
    label_manifest_hash,
    command,
    code_revision,
    seed=SEED,
    bootstrap_samples=BOOTSTRAP_SAMPLES,
):
    if seed != SEED:
        raise ValueError(f"HDVN-R01 uses the frozen seed {SEED}")
    if bootstrap_samples < 2:
        raise ValueError("bootstrap needs at least two samples")
    output_directory = Path(output_directory).resolve()
    predictions_path = output_directory / "predictions-2022-2023.parquet"
    report_path = output_directory / "residual-alpha-report.json"
    manifest_path = output_directory / "residual-alpha.manifest.json"
    paths = (predictions_path, report_path, manifest_path)
    if any(path.exists() for path in paths):
        raise FileExistsError(f"immutable residual-alpha output already exists: {output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)

    rows, dataset, split, opened_path = load_train_only(
        split_manifest,
        expected={
            "source_snapshot_sha256": source_snapshot_hash,
            "feature_manifest_hash": feature_manifest_hash,
            "tables_manifest_hash": tables_manifest_hash,
            "label_manifest_hash": label_manifest_hash,
        },
    )
    extracted = [_extract_features(row) for row in rows]
    roster = _matrix(extracted, ROSTER_FEATURE_ORDER, np)
    sequence = np.concatenate(
        (dataset.picks.reshape(len(rows), -1), dataset.mask.astype(np.float32)),
        axis=1,
    )
    combined = np.concatenate((roster, sequence), axis=1)
    feature_sets = {
        "roster_ridge": roster,
        "sequence_ridge": sequence,
        "combined_ridge": combined,
    }
    prediction_rows = []
    fold_reports = {}
    neural_reproducible = True

    for fold_index, fold in enumerate(FOLDS):
        train_indices = np.asarray(
            [index for index, row in enumerate(rows) if int(row["season"]) in fold["train_years"]],
            dtype=np.int64,
        )
        validation_indices = np.asarray(
            [index for index, row in enumerate(rows) if int(row["season"]) == fold["validation_year"]],
            dtype=np.int64,
        )
        if not len(train_indices) or not len(validation_indices):
            raise ValueError(f"residual fold is empty: {fold['name']}")
        train_rows = [rows[index] for index in train_indices]
        validation_rows = [rows[index] for index in validation_indices]
        market_oof, market_validation = _market_predictions(
            train_rows,
            validation_rows,
            seed=seed + fold_index,
        )
        train_actual = np.asarray([row["points_for_percentile"] for row in train_rows], dtype=np.float64)
        validation_actual = np.asarray(
            [row["points_for_percentile"] for row in validation_rows], dtype=np.float64
        )
        residual = train_actual - market_oof
        method_predictions = {"market": market_validation}
        training_details = {}
        for method, matrix in feature_sets.items():
            correction, details = _ridge_correction(
                matrix[train_indices],
                residual,
                matrix[validation_indices],
            )
            method_predictions[method] = np.clip(market_validation + correction, 0.0, 100.0)
            training_details[method] = details

        train_dataset = _subset(dataset, train_indices)
        validation_dataset = _subset(dataset, validation_indices)
        neural_prediction, neural_training = _train_residual_network(
            train_dataset,
            validation_dataset,
            residual,
            market_validation,
            seed=seed,
        )
        repeated_prediction, repeated_training = _train_residual_network(
            train_dataset,
            validation_dataset,
            residual,
            market_validation,
            seed=seed,
        )
        if not np.array_equal(neural_prediction, repeated_prediction) or neural_training != repeated_training:
            neural_reproducible = False
            raise ValueError("residual neural training is not reproducible")
        method_predictions["sequence_neural"] = neural_prediction
        training_details["sequence_neural"] = neural_training

        fold_report = {
            "train_years": list(fold["train_years"]),
            "validation_year": fold["validation_year"],
            "train_rows": len(train_indices),
            "validation_rows": len(validation_indices),
            "train_league_seasons": len({dataset.league_ids[index] for index in train_indices}),
            "validation_league_seasons": len({dataset.league_ids[index] for index in validation_indices}),
            "methods": {},
            "training": training_details,
        }
        baseline_mae = _mae(validation_actual, market_validation)
        for method, predictions in method_predictions.items():
            metrics = _point_metrics(validation_actual, predictions)
            fold_report["methods"][method] = {
                **metrics,
                "improvement_over_market": baseline_mae - metrics["mae"],
            }
            for local_index, prediction in enumerate(predictions):
                source = validation_rows[local_index]
                prediction_rows.append({
                    "fold": fold["name"],
                    "method": method,
                    "league_season_id": f"{source['season']}:{source['league_id']}",
                    "league_id": source["league_id"],
                    "season": int(source["season"]),
                    "roster_id": int(source["roster_id"]),
                    "scoring_format": source["scoring_format"],
                    "team_count": int(source["team_count"]),
                    "draft_slot": int(source["draft_slot"]),
                    "market_support_drafts": int(source["market_support_drafts"] or 0),
                    "market_support_bucket": _support_bucket(
                        int(source["market_support_drafts"] or 0)
                    ),
                    "missing_features": not any(
                        value is not None for value in json.loads(source["market_rank_by_pick_json"])
                    ),
                    "points_for_percentile": float(validation_actual[local_index]),
                    "predicted_points_for_percentile": float(prediction),
                })
        fold_reports[fold["name"]] = fold_report

    method_reports = {}
    for method in ("market", *METHODS):
        method_rows = [row for row in prediction_rows if row["method"] == method]
        method_reports[method] = {
            "metrics": _point_metrics_from_rows(method_rows),
            "slices": _slices(method_rows),
            "support": _support(method_rows),
        }
    market_by_key = {_row_key(row): row for row in prediction_rows if row["method"] == "market"}
    gates = {}
    for offset, method in enumerate(METHODS):
        rows_for_method = [row for row in prediction_rows if row["method"] == method]
        paired = [
            (
                row["league_season_id"],
                abs(row["predicted_points_for_percentile"] - row["points_for_percentile"])
                - abs(market_by_key[_row_key(row)]["predicted_points_for_percentile"] - row["points_for_percentile"]),
            )
            for row in rows_for_method
        ]
        interval = _clustered_mean_interval(
            paired,
            seed=seed + 100 + offset,
            samples=bootstrap_samples,
        )
        fold_improvements = {
            fold["name"]: fold_reports[fold["name"]]["methods"][method]["improvement_over_market"]
            for fold in FOLDS
        }
        gates[method] = {
            "fold_improvements": fold_improvements,
            "paired_absolute_error_difference": interval,
            "passes": (
                all(value >= GATE_MINIMUM_IMPROVEMENT for value in fold_improvements.values())
                and interval["estimate"] <= -GATE_MINIMUM_IMPROVEMENT
                and interval["high"] < 0
            ),
        }
    passing_methods = [method for method, gate in gates.items() if gate["passes"]]
    status = "research" if passing_methods else "rejected"

    _write_predictions(prediction_rows, predictions_path)
    repeated_path = output_directory / "predictions-2022-2023.repeat.parquet"
    _write_predictions(prediction_rows, repeated_path)
    prediction_hash = sha256_file(predictions_path)
    repeated_hash = sha256_file(repeated_path)
    repeated_path.unlink()
    if prediction_hash != repeated_hash:
        raise ValueError("residual prediction generation is not byte-identical")

    report = {
        "artifact_version": RESIDUAL_ARTIFACT_VERSION,
        "status": status,
        "frozen_gate": {
            "minimum_improvement_each_fold": GATE_MINIMUM_IMPROVEMENT,
            "minimum_pooled_improvement": GATE_MINIMUM_IMPROVEMENT,
            "pooled_interval_upper_below_zero": True,
        },
        "passing_methods": passing_methods,
        "folds": fold_reports,
        "methods": method_reports,
        "gates": gates,
        "loaded_partitions": ["train"],
        "opened_partition_files": [opened_path],
        "validation_2024_loaded": False,
        "locked_test_loaded": False,
        "neural_reproducible": neural_reproducible,
        "prediction_reproducibility": {
            "sha256": prediction_hash,
            "repeated_sha256": repeated_hash,
            "identical": True,
        },
        "limitations": list(LIMITATIONS),
    }
    report_path.write_text(canonical_json(report) + "\n")
    manifest = {
        "artifact_version": RESIDUAL_ARTIFACT_VERSION,
        "status": status,
        "source_snapshot_sha256": source_snapshot_hash,
        "feature_manifest_hash": feature_manifest_hash,
        "market_manifest_hash": market_manifest_hash,
        "tables_manifest_hash": tables_manifest_hash,
        "label_manifest_hash": label_manifest_hash,
        "split_manifest_hash": split["sha256"],
        "code_revision": code_revision,
        "code_sha256": sha256_file(Path(__file__)),
        "seed": seed,
        "methods": list(METHODS),
        "market_feature_order": list(MARKET_FEATURES),
        "roster_feature_order": list(ROSTER_FEATURE_ORDER),
        "sequence_feature_order": _sequence_feature_order(dataset),
        "neural_architecture": ARCHITECTURE,
        "neural_parameter_count": CompletedDraftNetwork(seed).parameter_count,
        "optimizer": OPTIMIZER,
        "loss_weights": LOSS_WEIGHTS,
        "stopping_rule": STOPPING_RULE,
        "frozen_gate": report["frozen_gate"],
        "passing_methods": passing_methods,
        "loaded_partitions": ["train"],
        "opened_partition_files": [opened_path],
        "validation_2024_loaded": False,
        "locked_test_loaded": False,
        "limitations": list(LIMITATIONS),
        "command": command,
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in (predictions_path, report_path)
        },
    }
    manifest["sha256"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    manifest_path.write_text(canonical_json(manifest) + "\n")
    load_residual_artifact(
        manifest_path,
        expected={
            "source_snapshot_sha256": source_snapshot_hash,
            "feature_manifest_hash": feature_manifest_hash,
            "market_manifest_hash": market_manifest_hash,
            "tables_manifest_hash": tables_manifest_hash,
            "label_manifest_hash": label_manifest_hash,
            "split_manifest_hash": split["sha256"],
            "status": status,
        },
    )
    for path in paths:
        path.chmod(0o444)
    return manifest


def load_residual_artifact(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = _load_hashed_json(manifest_path, "residual artifact manifest")
    if manifest.get("status") not in {"research", "rejected"}:
        raise ValueError("residual artifact status is invalid")
    if manifest.get("loaded_partitions") != ["train"]:
        raise ValueError("residual artifact loaded a non-train partition")
    if manifest.get("validation_2024_loaded") is not False:
        raise ValueError("residual artifact touched 2024 validation")
    if manifest.get("locked_test_loaded") is not False:
        raise ValueError("residual artifact touched locked test")
    if manifest.get("methods") != list(METHODS):
        raise ValueError("residual artifact method contract mismatch")
    if manifest.get("neural_parameter_count") >= 100_000:
        raise ValueError("residual neural model exceeds parameter limit")
    for filename, record in manifest.get("files", {}).items():
        if sha256_file(manifest_path.parent / filename) != record["sha256"]:
            raise ValueError(f"residual artifact file hash mismatch: {filename}")
    for key, value in (expected or {}).items():
        if manifest.get(key) != value:
            raise ValueError(f"residual artifact context mismatch for {key}")
    return manifest


def _market_predictions(train_rows, validation_rows, *, seed):
    try:
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import Ridge
        from sklearn.model_selection import GroupKFold
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as error:
        raise RuntimeError("residual discovery requires pinned research dependencies") from error
    x_train = _matrix([_extract_features(row) for row in train_rows], MARKET_FEATURES, np)
    x_validation = _matrix([_extract_features(row) for row in validation_rows], MARKET_FEATURES, np)
    actual = np.asarray([row["points_for_percentile"] for row in train_rows], dtype=np.float64)
    groups = np.asarray([f"{row['season']}:{row['league_id']}" for row in train_rows])
    oof = np.empty(len(train_rows), dtype=np.float64)
    splitter = GroupKFold(n_splits=5)
    for fit_indices, held_indices in splitter.split(x_train, actual, groups):
        model = _ridge_pipeline(SimpleImputer, StandardScaler, Ridge)
        model.fit(x_train[fit_indices], actual[fit_indices])
        oof[held_indices] = model.predict(x_train[held_indices])
    final = _ridge_pipeline(SimpleImputer, StandardScaler, Ridge)
    final.fit(x_train, actual)
    return np.clip(oof, 0.0, 100.0), np.clip(final.predict(x_validation), 0.0, 100.0)


def _ridge_pipeline(SimpleImputer, StandardScaler, Ridge):
    from sklearn.pipeline import make_pipeline

    return make_pipeline(
        SimpleImputer(strategy="median", keep_empty_features=True),
        StandardScaler(),
        Ridge(alpha=10.0),
    )


def _ridge_correction(x_train, residual, x_validation):
    try:
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler
    except ImportError as error:
        raise RuntimeError("residual discovery requires pinned research dependencies") from error
    model = _ridge_pipeline(SimpleImputer, StandardScaler, Ridge)
    model.fit(x_train, residual)
    return model.predict(x_validation), {"model": "Ridge", "alpha": 10.0}


def _train_residual_network(train, validation, residual, market_validation, *, seed):
    normalizer = fit_normalizer(train)
    train_picks, train_context = normalize_inputs(train, normalizer)
    validation_picks, validation_context = normalize_inputs(validation, normalizer)
    model = CompletedDraftNetwork(seed)
    model.params["points_bias"].fill(0.0)
    moments = {name: np.zeros_like(value) for name, value in model.params.items()}
    velocities = {name: np.zeros_like(value) for name, value in model.params.items()}
    groups = list(_league_groups(train.league_ids).values())
    residual_target = np.asarray(residual / 100.0, dtype=np.float32)
    actual_validation = validation.points * 100.0
    best = None
    history = []
    stale = step = 0
    for epoch in range(1, STOPPING_RULE["max_epochs"] + 1):
        order = np.random.default_rng(seed + epoch).permutation(len(groups))
        losses = []
        for start in range(0, len(order), 128):
            indices = np.concatenate([groups[index] for index in order[start:start + 128]])
            loss, gradients = model.loss_and_gradients(
                train_picks[indices],
                train.mask[indices],
                train_context[indices],
                residual_target[indices],
                train.playoff[indices],
                train.champion[indices],
                tuple(train.league_ids[index] for index in indices),
            )
            losses.append(loss)
            step += 1
            _adam_step(model.params, gradients, moments, velocities, step)
        correction, _, _ = model.forward(validation_picks, validation.mask, validation_context)
        predictions = np.clip(market_validation + correction * 100.0, 0.0, 100.0)
        mae = _mae(actual_validation, predictions)
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)), "validation_mae": mae})
        if best is None or mae < best[0] - STOPPING_RULE["minimum_improvement"]:
            best = (mae, epoch, {name: value.copy() for name, value in model.params.items()})
            stale = 0
        else:
            stale += 1
            if stale >= STOPPING_RULE["patience"]:
                break
    model.params = best[2]
    correction, _, _ = model.forward(validation_picks, validation.mask, validation_context)
    return np.clip(market_validation + correction * 100.0, 0.0, 100.0), {
        "best_epoch": best[1],
        "epochs_run": len(history),
        "history": history,
        "parameter_count": model.parameter_count,
    }


def _subset(dataset, indices):
    return replace(
        dataset,
        picks=dataset.picks[indices],
        mask=dataset.mask[indices],
        context=dataset.context[indices],
        points=dataset.points[indices],
        playoff=dataset.playoff[indices],
        champion=dataset.champion[indices],
        league_ids=tuple(dataset.league_ids[index] for index in indices),
        metadata=tuple(dataset.metadata[index] for index in indices),
    )


def _sequence_feature_order(dataset):
    order = [
        f"pick_{pick + 1}_{feature}"
        for pick in range(dataset.picks.shape[1])
        for feature in PICK_FEATURE_ORDER
    ]
    order.extend(f"pick_{pick + 1}_mask" for pick in range(dataset.picks.shape[1]))
    return order


def _point_metrics(actual, prediction):
    errors = np.asarray(prediction) - np.asarray(actual)
    return {
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors * errors))),
        "rows": len(errors),
    }


def _point_metrics_from_rows(rows):
    return _point_metrics(
        [row["points_for_percentile"] for row in rows],
        [row["predicted_points_for_percentile"] for row in rows],
    )


def _mae(actual, prediction):
    return float(np.mean(np.abs(np.asarray(prediction) - np.asarray(actual))))


def _slices(rows):
    grouped = defaultdict(list)
    for row in rows:
        for field in ("season", "scoring_format", "team_count", "draft_slot", "market_support_bucket"):
            grouped[(field, row[field])].append(row)
    return [
        {
            "field": field,
            "value": value,
            "metrics": _point_metrics_from_rows(group),
            "league_seasons": len({row["league_season_id"] for row in group}),
            "missing_feature_rows": sum(row["missing_features"] for row in group),
        }
        for (field, value), group in sorted(grouped.items(), key=lambda item: (item[0][0], str(item[0][1])))
    ]


def _support(rows):
    support = [row["market_support_drafts"] for row in rows]
    missing = sum(row["missing_features"] for row in rows)
    return {
        "rows": len(rows),
        "missing_feature_rows": missing,
        "missing_feature_rate": missing / len(rows),
        "minimum_market_support_drafts": min(support),
        "median_market_support_drafts": float(np.median(support)),
        "maximum_market_support_drafts": max(support),
    }


def _support_bucket(support):
    if support == 0:
        return "none"
    if support < 25:
        return "sparse"
    if support < 100:
        return "25-99"
    if support < 500:
        return "100-499"
    return "500+"


def _clustered_mean_interval(values, *, seed, samples, confidence=0.95):
    clusters = defaultdict(list)
    for key, value in values:
        clusters[key].append(float(value))
    keys = sorted(clusters)
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        sampled = [value for _ in keys for value in clusters[rng.choice(keys)]]
        estimates.append(sum(sampled) / len(sampled))
    estimates.sort()
    tail = (1 - confidence) / 2
    all_values = [value for group in clusters.values() for value in group]
    return {
        "estimate": sum(all_values) / len(all_values),
        "low": estimates[max(0, int(tail * samples))],
        "high": estimates[min(samples - 1, math.ceil((1 - tail) * samples) - 1)],
        "samples": samples,
        "seed": seed,
    }


def _write_predictions(rows, path):
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("residual discovery requires pinned research dependencies") from error
    pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd")


def _row_key(row):
    return row["season"], row["league_id"], row["roster_id"]


def _load_hashed_json(path, label):
    try:
        manifest = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is malformed") from error
    stored = manifest.get("sha256")
    body = {key: value for key, value in manifest.items() if key != "sha256"}
    if stored != hashlib.sha256(canonical_json(body).encode()).hexdigest():
        raise ValueError(f"{label} hash mismatch")
    return manifest
