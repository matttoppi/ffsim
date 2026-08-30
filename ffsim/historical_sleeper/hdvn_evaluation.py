import hashlib
import json
import math
import random
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import Protocol

from .hdvn_snapshot import canonical_json


EVALUATION_VERSION = "hdvn-evaluation-v1"
ARTIFACT_SCHEMA_VERSION = "hdvn-artifact-v1"
ALLOWED_STATUSES = {"research", "candidate", "validated_shadow", "rejected"}
REQUIRED_ARTIFACT_FIELDS = {
    "artifact_schema_version",
    "model_family",
    "model_version",
    "code_revision",
    "source_snapshot_hash",
    "feature_version",
    "label_version",
    "split_manifest_hash",
    "market_projection_provenance",
    "counts_by_year_context",
    "prefix_sampling_method",
    "total_team_weight",
    "architecture",
    "parameter_count",
    "seed",
    "optimizer",
    "loss_weights",
    "stopping_rule",
    "baseline_metrics",
    "holdout_metrics",
    "calibration",
    "limitations",
    "status",
}


class ModelFamily(str, Enum):
    CONTEXT_BASELINE = "context_baseline"
    REGULARIZED = "regularized_linear_logistic"
    BOOSTED_TREE = "boosted_tree"
    COMPLETED_DRAFT_NEURAL = "completed_draft_neural"
    PARTIAL_PREFIX_NEURAL = "partial_prefix_neural"


class OfflineModel(Protocol):
    family: ModelFamily
    model_version: str

    def predict(self, rows):
        """Return point, playoff, and within-league championship predictions."""


BASELINE_INTERFACES = (
    {"name": "uniform_championship", "requirement": "1 / team_count"},
    {"name": "draft_slot_and_context", "requirement": "point-in-time league and geometry features only"},
    {"name": "historical_market_value", "requirement": "rolling prior-draft board only"},
    {"name": "regularized_linear_logistic", "requirement": "common OfflineModel protocol"},
    {"name": "gradient_boosted_tree", "requirement": "common OfflineModel protocol"},
    {"name": "projection_value", "requirement": "exact projection snapshot predates target draft"},
    {"name": "deterministic_projection_lookahead", "requirement": "offline comparison adapter; no HDVN input"},
    {"name": "coupled_ffsim_terminal_rollouts", "requirement": "many coupled continuations with uncertainty and counts"},
)


def evaluate_predictions(rows):
    rows = list(rows)
    points = _pairs(rows, "points_for_percentile", "predicted_points_for_percentile")
    playoffs = _pairs(rows, "made_playoffs", "predicted_playoff")
    _validate_championship_probabilities(rows)
    championship = [
        row for row in rows
        if row.get("champion") is not None and row.get("predicted_champion") is not None
    ]
    point_errors = [prediction - actual for actual, prediction in points]
    playoff_errors = [prediction - actual for actual, prediction in playoffs]
    return {
        "evaluation_version": EVALUATION_VERSION,
        "points_percentile": {
            "mae": _mean(abs(error) for error in point_errors),
            "rmse": math.sqrt(_mean(error * error for error in point_errors)) if point_errors else None,
            "count": len(point_errors),
        },
        "playoff": {
            "log_loss": _mean(_binary_log_loss(actual, prediction) for actual, prediction in playoffs),
            "brier": _mean(error * error for error in playoff_errors),
            "count": len(playoffs),
        },
        "championship": {
            "within_league_log_loss": _mean(
                -math.log(_probability(row["predicted_champion"]))
                for row in championship if row["champion"] == 1
            ),
            "count": sum(row["champion"] == 1 for row in championship),
        },
        "calibration": {
            "playoff": calibration_buckets(rows, "made_playoffs", "predicted_playoff"),
            "championship": calibration_buckets(rows, "champion", "predicted_champion"),
        },
        "within_league_roster_ranking": within_league_ranking(rows),
        "coverage": coverage_report(rows),
    }


def context_slices(rows):
    grouped = defaultdict(list)
    for row in rows:
        for field in ("season", "team_count", "scoring_format", "draft_slot"):
            grouped[(field, row.get(field))].append(row)
    return [
        {"field": field, "value": value, "metrics": evaluate_predictions(group)}
        for (field, value), group in sorted(grouped.items(), key=lambda item: (item[0][0], str(item[0][1])))
    ]


def clustered_bootstrap(rows, metric, *, seed=0, samples=200, confidence=0.95):
    if samples < 2:
        raise ValueError("bootstrap needs at least two samples")
    rows = list(rows)
    clusters = defaultdict(list)
    for row in rows:
        key = row.get("league_season_id") or f"{row['season']}:{row['league_id']}"
        clusters[key].append(row)
    keys = sorted(clusters)
    if not keys:
        raise ValueError("bootstrap has no league-season clusters")
    rng = random.Random(seed)
    values = []
    for _ in range(samples):
        sampled = []
        for draw in range(len(keys)):
            source_key = rng.choice(keys)
            sampled.extend(
                {**row, "league_season_id": f"bootstrap:{draw}:{source_key}"}
                for row in clusters[source_key]
            )
        values.append(float(metric(sampled)))
    values.sort()
    tail = (1 - confidence) / 2
    low = values[max(0, int(tail * samples))]
    high = values[min(samples - 1, math.ceil((1 - tail) * samples) - 1)]
    return {
        "estimate": float(metric(rows)),
        "low": low,
        "high": high,
        "samples": samples,
        "seed": seed,
    }


def calibration_buckets(rows, actual_field, prediction_field, *, buckets=10):
    grouped = defaultdict(list)
    for row in rows:
        actual, prediction = row.get(actual_field), row.get(prediction_field)
        if actual is None or prediction is None:
            continue
        prediction = min(max(float(prediction), 0.0), 1.0)
        index = min(int(prediction * buckets), buckets - 1)
        grouped[index].append((float(actual), prediction))
    return [
        {
            "lower": index / buckets,
            "upper": (index + 1) / buckets,
            "count": len(values),
            "mean_prediction": _mean(value[1] for value in values),
            "observed_rate": _mean(value[0] for value in values),
        }
        for index, values in sorted(grouped.items())
    ]


def within_league_ranking(rows):
    leagues = defaultdict(list)
    for row in rows:
        if row.get("points_for_percentile") is None or row.get("predicted_points_for_percentile") is None:
            continue
        key = row.get("league_season_id") or f"{row['season']}:{row['league_id']}"
        leagues[key].append(row)
    concordant = comparable = 0.0
    for league in leagues.values():
        for left_index, left in enumerate(league):
            for right in league[left_index + 1:]:
                actual_delta = left["points_for_percentile"] - right["points_for_percentile"]
                predicted_delta = left["predicted_points_for_percentile"] - right["predicted_points_for_percentile"]
                if actual_delta == 0 or predicted_delta == 0:
                    concordant += 0.5
                elif actual_delta * predicted_delta > 0:
                    concordant += 1
                comparable += 1
    return {"pairwise_concordance": concordant / comparable if comparable else None, "pairs": int(comparable)}


def coverage_report(rows):
    rows = list(rows)
    prediction_fields = (
        "predicted_points_for_percentile",
        "predicted_playoff",
        "predicted_champion",
    )
    return {
        "rows": len(rows),
        "supporting_league_seasons": len({
            row.get("league_season_id") or f"{row.get('season')}:{row.get('league_id')}"
            for row in rows
        }),
        "missing_predictions": {
            field: sum(row.get(field) is None for row in rows) for field in prediction_fields
        },
        "missing_feature_rows": sum(bool(row.get("missing_features")) for row in rows),
    }


def uniform_championship_predictions(rows):
    return [
        {**row, "predicted_champion": 1.0 / int(row["team_count"])}
        for row in rows
    ]


def artifact_manifest(metadata):
    validate_artifact_manifest(metadata)
    body = dict(metadata)
    return {**body, "manifest_sha256": hashlib.sha256(canonical_json(body).encode()).hexdigest()}


def validate_artifact_manifest(metadata, *, expected=None):
    if not isinstance(metadata, dict):
        raise ValueError("artifact manifest must be an object")
    missing = REQUIRED_ARTIFACT_FIELDS - metadata.keys()
    if missing:
        raise ValueError(f"artifact manifest missing {sorted(missing)}")
    if metadata["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION:
        raise ValueError("incompatible artifact schema")
    try:
        ModelFamily(metadata["model_family"])
    except ValueError as error:
        raise ValueError("unsupported model family") from error
    if metadata["status"] not in ALLOWED_STATUSES:
        raise ValueError("unsupported artifact status")
    if not isinstance(metadata["parameter_count"], int) or metadata["parameter_count"] < 0:
        raise ValueError("invalid artifact parameter count")
    if not isinstance(metadata["total_team_weight"], (int, float)) or metadata["total_team_weight"] < 0:
        raise ValueError("invalid total team weight")
    if expected:
        for field, value in expected.items():
            if metadata.get(field) != value:
                raise ValueError(f"artifact context mismatch: {field}")
    return True


def load_artifact_manifest(path, *, expected=None):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        metadata = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("malformed artifact manifest") from error
    validate_artifact_manifest(metadata, expected=expected)
    claimed = metadata.get("manifest_sha256")
    if not claimed:
        raise ValueError("artifact manifest hash missing")
    body = {key: value for key, value in metadata.items() if key != "manifest_sha256"}
    actual = hashlib.sha256(canonical_json(body).encode()).hexdigest()
    if claimed != actual:
        raise ValueError("artifact manifest hash mismatch")
    return metadata


def write_artifact_manifest(metadata, path):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    manifest = artifact_manifest(metadata)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(manifest) + "\n")
    return manifest


def _validate_championship_probabilities(rows):
    leagues = defaultdict(list)
    for row in rows:
        if row.get("predicted_champion") is None:
            continue
        key = row.get("league_season_id") or f"{row['season']}:{row['league_id']}"
        leagues[key].append(float(row["predicted_champion"]))
    for key, probabilities in leagues.items():
        if any(value < 0 or value > 1 for value in probabilities):
            raise ValueError(f"invalid championship probability in {key}")
        if not math.isclose(sum(probabilities), 1.0, rel_tol=0, abs_tol=1e-9):
            raise ValueError(f"championship probabilities do not sum to one in {key}")


def _pairs(rows, actual_field, prediction_field):
    return [
        (float(row[actual_field]), float(row[prediction_field]))
        for row in rows
        if row.get(actual_field) is not None and row.get(prediction_field) is not None
    ]


def _probability(value):
    return min(max(float(value), 1e-15), 1 - 1e-15)


def _binary_log_loss(actual, prediction):
    probability = _probability(prediction)
    return -(actual * math.log(probability) + (1 - actual) * math.log(1 - probability))


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None
