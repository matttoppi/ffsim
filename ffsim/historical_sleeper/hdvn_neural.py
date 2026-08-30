import hashlib
import json
import math
import os
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .hdvn_baselines import load_baseline_bundle
from .hdvn_evaluation import ALLOWED_STATUSES, EVALUATION_VERSION, evaluate_predictions
from .hdvn_snapshot import canonical_json, sha256_file


NEURAL_ARTIFACT_VERSION = "hdvn-completed-draft-neural-v1"
SEED = 20260828
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF", "UNKNOWN")
SCORING_FORMATS = ("STD", "HALF_PPR", "PPR")
PICK_FEATURE_ORDER = (
    *(f"position_{position}" for position in POSITIONS),
    "round_fraction",
    "overall_pick_fraction",
    "market_rank_fraction",
    "market_adp_fraction",
    "market_value_fraction",
    "market_present",
    *(f"prior_count_{position}" for position in POSITIONS),
)
CONTEXT_FEATURE_ORDER = (
    "season_offset",
    "team_count",
    "draft_slot_fraction",
    "round_count",
    *(f"scoring_{value}" for value in SCORING_FORMATS),
    *(f"roster_slot_{value}" for value in ("QB", "RB", "WR", "TE", "FLEX", "BN")),
    "log_market_support",
    "cumulative_market_value_per_pick",
    "market_pick_coverage",
)
PARTITION_COLUMNS = (
    "league_id",
    "season",
    "draft_id",
    "roster_id",
    "draft_slot",
    "round_count",
    "team_count",
    "scoring_format",
    "roster_positions_json",
    "position_sequence_json",
    "pick_numbers_json",
    "pick_rounds_json",
    "market_rank_by_pick_json",
    "market_adp_by_pick_json",
    "market_value_by_pick_json",
    "cumulative_market_value",
    "market_support_drafts",
    "feature_manifest_hash",
    "points_for_percentile",
    "made_playoffs",
    "champion",
)
ARCHITECTURE = {
    "pick_input": len(PICK_FEATURE_ORDER),
    "pick_hidden": 32,
    "pooling": "explicit-mask mean and max",
    "context_input": len(CONTEXT_FEATURE_ORDER),
    "shared_hidden": 48,
    "heads": ["points_percentile", "playoff_logit", "within_league_championship_logit"],
    "player_ids": False,
}
LOSS_WEIGHTS = {"points": 1.0, "playoff": 0.1, "championship": 0.1}
OPTIMIZER = {"name": "Adam", "learning_rate": 0.001, "beta1": 0.9, "beta2": 0.999, "epsilon": 1e-8, "l2": 1e-5}
STOPPING_RULE = {"metric": "2024 points-percentile MAE", "max_epochs": 40, "patience": 6, "minimum_improvement": 0.001}
TEMPERATURES = (0.5, 0.75, 1.0, 1.5, 2.0)
PASS_MAE = 27.08046
PRIMARY_BASELINES = (
    "draft_slot_and_context",
    "historical_market_value",
    "regularized_linear_logistic",
    "gradient_boosted_tree",
)
LIMITATIONS = [
    "market_and_construction_only",
    "point-in-time historical projections are unavailable",
    "current projections and post-season player outcomes are not inputs",
    "validation, early stopping, and calibration use 2024 only",
    "the locked 2025 partition was not opened",
    "completed drafts only; no prefix or candidate-substitution training",
    "single neural fit; no ensemble or architecture search",
    "offline research only; no live loader or ranking path",
]


@dataclass(frozen=True)
class CompletedDraftDataset:
    partition: str
    picks: np.ndarray
    mask: np.ndarray
    context: np.ndarray
    points: np.ndarray
    playoff: np.ndarray
    champion: np.ndarray
    league_ids: tuple
    metadata: tuple


@dataclass(frozen=True)
class CompletedDraftDatasets:
    train: CompletedDraftDataset
    validation: CompletedDraftDataset
    split_manifest: dict
    opened_paths: tuple


def load_completed_draft_datasets(split_manifest_path, *, expected):
    """Load exactly the train and validation completed-draft partitions."""
    split_manifest_path = Path(split_manifest_path).resolve()
    manifest = _load_hashed_json(split_manifest_path, "split manifest")
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"split context mismatch for {key}")
    if manifest.get("years", {}).get("train") != [2021, 2022, 2023]:
        raise ValueError("training years are not the frozen 2021-2023 split")
    if manifest.get("years", {}).get("validation") != [2024]:
        raise ValueError("validation year is not the frozen 2024 split")

    opened_paths = []
    raw = {}
    for partition in ("train", "validation"):
        record = manifest["partition_files"][partition]
        path = (split_manifest_path.parent / record["path"]).resolve()
        if sha256_file(path) != record["sha256"]:
            raise ValueError(f"partition file hash mismatch: {partition}")
        opened_paths.append(str(path))
        raw[partition] = _read_partition(path, partition, expected["feature_manifest_hash"])
    max_picks = max(len(json.loads(row["position_sequence_json"])) for rows in raw.values() for row in rows)
    datasets = {
        partition: _build_dataset(partition, rows, max_picks)
        for partition, rows in raw.items()
    }
    return CompletedDraftDatasets(
        train=datasets["train"],
        validation=datasets["validation"],
        split_manifest=manifest,
        opened_paths=tuple(opened_paths),
    )


def _read_partition(path, partition, feature_manifest_hash):
    try:
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("HDVN neural fitting requires pinned research dependencies") from error
    expected_seasons = {"train": {2021, 2022, 2023}, "validation": {2024}}[partition]
    rows = []
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(batch_size=10_000, columns=PARTITION_COLUMNS):
        for row in batch.to_pylist():
            if int(row["season"]) not in expected_seasons:
                raise ValueError(f"{partition} row has season {row['season']}")
            if row["feature_manifest_hash"] != feature_manifest_hash:
                raise ValueError("partition row feature hash mismatch")
            rows.append(row)
    if not rows:
        raise ValueError(f"{partition} partition is empty")
    return rows


def _build_dataset(partition, rows, max_picks):
    picks = np.zeros((len(rows), max_picks, len(PICK_FEATURE_ORDER)), dtype=np.float32)
    mask = np.zeros((len(rows), max_picks), dtype=bool)
    context = np.zeros((len(rows), len(CONTEXT_FEATURE_ORDER)), dtype=np.float32)
    metadata = []
    for index, row in enumerate(rows):
        features, valid, market_coverage = _pick_features(row, max_picks)
        picks[index] = features
        mask[index] = valid
        context[index] = _context_features(row, market_coverage)
        metadata.append({
            "league_season_id": f"{row['season']}:{row['league_id']}",
            "league_id": row["league_id"],
            "season": int(row["season"]),
            "draft_id": row["draft_id"],
            "roster_id": int(row["roster_id"]),
            "team_count": int(row["team_count"]),
            "scoring_format": row["scoring_format"],
            "draft_slot": int(row["draft_slot"]),
            "market_support_drafts": int(row["market_support_drafts"] or 0),
            "market_pick_coverage": market_coverage,
            "missing_features": market_coverage == 0.0,
            "points_for_percentile": float(row["points_for_percentile"]),
            "made_playoffs": int(row["made_playoffs"]),
            "champion": int(row["champion"]),
        })
    league_ids = tuple(row["league_season_id"] for row in metadata)
    return CompletedDraftDataset(
        partition=partition,
        picks=picks,
        mask=mask,
        context=context,
        points=np.asarray([row["points_for_percentile"] / 100.0 for row in metadata], dtype=np.float32),
        playoff=np.asarray([row["made_playoffs"] for row in metadata], dtype=np.float32),
        champion=np.asarray([row["champion"] for row in metadata], dtype=np.float32),
        league_ids=league_ids,
        metadata=tuple(metadata),
    )


def _pick_features(row, max_picks):
    positions = json.loads(row["position_sequence_json"])
    pick_numbers = json.loads(row["pick_numbers_json"])
    rounds = json.loads(row["pick_rounds_json"])
    ranks = json.loads(row["market_rank_by_pick_json"])
    adps = json.loads(row["market_adp_by_pick_json"])
    values = json.loads(row["market_value_by_pick_json"])
    lengths = {len(values_) for values_ in (positions, pick_numbers, rounds, ranks, adps, values)}
    if len(lengths) != 1 or not positions or len(positions) > max_picks:
        raise ValueError("pick sequence columns are not aligned")
    result = np.zeros((max_picks, len(PICK_FEATURE_ORDER)), dtype=np.float32)
    valid = np.zeros(max_picks, dtype=bool)
    prior = Counter()
    total_picks = max(int(row["team_count"]) * int(row["round_count"]), 1)
    supported = 0
    for index, (position, pick_no, round_, rank, adp, value) in enumerate(
        zip(positions, pick_numbers, rounds, ranks, adps, values)
    ):
        position = position if position in POSITIONS else "UNKNOWN"
        vector = [float(position == candidate) for candidate in POSITIONS]
        present = rank is not None and adp is not None and value is not None
        supported += int(present)
        vector.extend([
            float(round_) / max(int(row["round_count"]), 1),
            float(pick_no) / total_picks,
            float(rank) / total_picks if rank is not None else 0.0,
            float(adp) / total_picks if adp is not None else 0.0,
            float(value) / total_picks if value is not None else 0.0,
            float(present),
            *(prior[candidate] / max(int(row["round_count"]), 1) for candidate in POSITIONS),
        ])
        result[index] = vector
        valid[index] = True
        prior[position] += 1
    return result, valid, supported / len(positions)


def _context_features(row, market_coverage):
    roster_slots = Counter(json.loads(row["roster_positions_json"]))
    pick_count = len(json.loads(row["position_sequence_json"]))
    return np.asarray([
        (int(row["season"]) - 2021) / 3.0,
        float(row["team_count"]),
        float(row["draft_slot"]) / max(int(row["team_count"]), 1),
        float(row["round_count"]),
        *(float(row["scoring_format"] == value) for value in SCORING_FORMATS),
        *(float(roster_slots[value]) for value in ("QB", "RB", "WR", "TE", "FLEX", "BN")),
        math.log1p(float(row["market_support_drafts"] or 0)),
        float(row["cumulative_market_value"] or 0.0) / max(pick_count, 1),
        market_coverage,
    ], dtype=np.float32)


def fit_normalizer(dataset):
    valid_picks = dataset.picks[dataset.mask]
    pick_mean = valid_picks.mean(axis=0)
    pick_std = valid_picks.std(axis=0)
    context_mean = dataset.context.mean(axis=0)
    context_std = dataset.context.std(axis=0)
    pick_std[pick_std < 1e-6] = 1.0
    context_std[context_std < 1e-6] = 1.0
    return {
        "pick_mean": pick_mean,
        "pick_std": pick_std,
        "context_mean": context_mean,
        "context_std": context_std,
    }


def normalize_inputs(dataset, normalizer):
    picks = (dataset.picks - normalizer["pick_mean"]) / normalizer["pick_std"]
    picks = np.where(dataset.mask[..., None], picks, 0.0).astype(np.float32)
    context = ((dataset.context - normalizer["context_mean"]) / normalizer["context_std"]).astype(np.float32)
    return picks, context


class CompletedDraftNetwork:
    def __init__(self, seed=SEED, params=None):
        if params is not None:
            self.params = {name: np.asarray(value, dtype=np.float32) for name, value in params.items()}
            self._validate_shapes()
            return
        rng = np.random.default_rng(seed)
        pick_input = len(PICK_FEATURE_ORDER)
        pick_hidden = ARCHITECTURE["pick_hidden"]
        combined = 2 * pick_hidden + len(CONTEXT_FEATURE_ORDER)
        shared_hidden = ARCHITECTURE["shared_hidden"]
        self.params = {
            "pick_weight": rng.normal(0, math.sqrt(2 / pick_input), (pick_input, pick_hidden)).astype(np.float32),
            "pick_bias": np.zeros(pick_hidden, dtype=np.float32),
            "shared_weight": rng.normal(0, math.sqrt(2 / combined), (combined, shared_hidden)).astype(np.float32),
            "shared_bias": np.zeros(shared_hidden, dtype=np.float32),
            "points_weight": rng.normal(0, 0.05, (shared_hidden, 1)).astype(np.float32),
            "points_bias": np.asarray([0.5], dtype=np.float32),
            "playoff_weight": rng.normal(0, 0.05, (shared_hidden, 1)).astype(np.float32),
            "playoff_bias": np.zeros(1, dtype=np.float32),
            "champion_weight": rng.normal(0, 0.05, (shared_hidden, 1)).astype(np.float32),
            "champion_bias": np.zeros(1, dtype=np.float32),
        }
        self._validate_shapes()

    @property
    def parameter_count(self):
        return sum(value.size for value in self.params.values())

    def _validate_shapes(self):
        expected = {
            "pick_weight": (len(PICK_FEATURE_ORDER), ARCHITECTURE["pick_hidden"]),
            "pick_bias": (ARCHITECTURE["pick_hidden"],),
            "shared_weight": (2 * ARCHITECTURE["pick_hidden"] + len(CONTEXT_FEATURE_ORDER), ARCHITECTURE["shared_hidden"]),
            "shared_bias": (ARCHITECTURE["shared_hidden"],),
            "points_weight": (ARCHITECTURE["shared_hidden"], 1),
            "points_bias": (1,),
            "playoff_weight": (ARCHITECTURE["shared_hidden"], 1),
            "playoff_bias": (1,),
            "champion_weight": (ARCHITECTURE["shared_hidden"], 1),
            "champion_bias": (1,),
        }
        if set(self.params) != set(expected):
            raise ValueError("neural parameter names mismatch")
        for name, shape in expected.items():
            if self.params[name].shape != shape:
                raise ValueError(f"neural parameter shape mismatch: {name}")

    def forward(self, picks, mask, context, *, cache=False):
        if picks.shape[:2] != mask.shape or picks.shape[2] != len(PICK_FEATURE_ORDER):
            raise ValueError("pick tensor and explicit mask are incompatible")
        p = self.params
        pick_linear = picks @ p["pick_weight"] + p["pick_bias"]
        encoded = np.maximum(pick_linear, 0.0)
        expanded_mask = mask[..., None]
        count = np.maximum(mask.sum(axis=1, keepdims=True), 1).astype(np.float32)
        mean_pool = (encoded * expanded_mask).sum(axis=1) / count
        masked = np.where(expanded_mask, encoded, -np.inf)
        max_pool = masked.max(axis=1)
        max_pool[~mask.any(axis=1)] = 0.0
        maximum_indices = masked.argmax(axis=1)
        combined = np.concatenate((mean_pool, max_pool, context), axis=1)
        shared_linear = combined @ p["shared_weight"] + p["shared_bias"]
        shared = np.maximum(shared_linear, 0.0)
        outputs = (
            (shared @ p["points_weight"] + p["points_bias"]).ravel(),
            (shared @ p["playoff_weight"] + p["playoff_bias"]).ravel(),
            (shared @ p["champion_weight"] + p["champion_bias"]).ravel(),
        )
        if not cache:
            return outputs
        return outputs, {
            "picks": picks,
            "mask": mask,
            "count": count,
            "pick_linear": pick_linear,
            "maximum_indices": maximum_indices,
            "combined": combined,
            "shared_linear": shared_linear,
            "shared": shared,
        }

    def loss_and_gradients(self, picks, mask, context, points, playoff, champion, league_ids):
        (point_output, playoff_logits, champion_logits), cache = self.forward(picks, mask, context, cache=True)
        count = len(points)
        point_error = point_output - points
        points_loss = float(np.mean(point_error * point_error))
        d_points = LOSS_WEIGHTS["points"] * 2.0 * point_error / count
        playoff_loss = float(np.mean(np.logaddexp(0.0, playoff_logits) - playoff * playoff_logits))
        d_playoff = LOSS_WEIGHTS["playoff"] * (_sigmoid(playoff_logits) - playoff) / count
        championship_loss, d_champion = _championship_loss_and_gradient(champion_logits, champion, league_ids)
        d_champion *= LOSS_WEIGHTS["championship"]

        p = self.params
        shared = cache["shared"]
        gradients = {
            "points_weight": shared.T @ d_points[:, None],
            "points_bias": np.asarray([d_points.sum()], dtype=np.float32),
            "playoff_weight": shared.T @ d_playoff[:, None],
            "playoff_bias": np.asarray([d_playoff.sum()], dtype=np.float32),
            "champion_weight": shared.T @ d_champion[:, None],
            "champion_bias": np.asarray([d_champion.sum()], dtype=np.float32),
        }
        d_shared = (
            d_points[:, None] @ p["points_weight"].T
            + d_playoff[:, None] @ p["playoff_weight"].T
            + d_champion[:, None] @ p["champion_weight"].T
        )
        d_shared[cache["shared_linear"] <= 0] = 0
        gradients["shared_weight"] = cache["combined"].T @ d_shared
        gradients["shared_bias"] = d_shared.sum(axis=0)
        d_combined = d_shared @ p["shared_weight"].T
        hidden = ARCHITECTURE["pick_hidden"]
        d_mean = d_combined[:, :hidden]
        d_max = d_combined[:, hidden:2 * hidden]
        d_encoded = d_mean[:, None, :] * cache["mask"][..., None] / cache["count"][:, :, None]
        row_indices = np.arange(count)[:, None]
        feature_indices = np.arange(hidden)[None, :]
        np.add.at(d_encoded, (row_indices, cache["maximum_indices"], feature_indices), d_max)
        d_encoded *= cache["mask"][..., None]
        d_encoded[cache["pick_linear"] <= 0] = 0
        gradients["pick_weight"] = np.einsum("npi,npj->ij", cache["picks"], d_encoded)
        gradients["pick_bias"] = d_encoded.sum(axis=(0, 1))

        l2_loss = 0.0
        for name, value in p.items():
            if name.endswith("weight"):
                l2_loss += 0.5 * OPTIMIZER["l2"] * float(np.sum(value * value))
                gradients[name] += OPTIMIZER["l2"] * value
        total = (
            LOSS_WEIGHTS["points"] * points_loss
            + LOSS_WEIGHTS["playoff"] * playoff_loss
            + LOSS_WEIGHTS["championship"] * championship_loss
            + l2_loss
        )
        return total, gradients


def train_network(train, validation, *, seed=SEED, batch_size=128):
    if batch_size < 1:
        raise ValueError("batch size must be positive")
    normalizer = fit_normalizer(train)
    train_picks, train_context = normalize_inputs(train, normalizer)
    validation_picks, validation_context = normalize_inputs(validation, normalizer)
    model = CompletedDraftNetwork(seed)
    if model.parameter_count >= 100_000:
        raise ValueError("HDVN V1 exceeds the 100,000 parameter limit")
    moments = {name: np.zeros_like(value) for name, value in model.params.items()}
    velocities = {name: np.zeros_like(value) for name, value in model.params.items()}
    groups = list(_league_groups(train.league_ids).values())
    best = None
    history = []
    stale = step = 0
    for epoch in range(1, STOPPING_RULE["max_epochs"] + 1):
        order = np.random.default_rng(seed + epoch).permutation(len(groups))
        losses = []
        for start in range(0, len(order), batch_size):
            indices = np.concatenate([groups[index] for index in order[start:start + batch_size]])
            loss, gradients = model.loss_and_gradients(
                train_picks[indices],
                train.mask[indices],
                train_context[indices],
                train.points[indices],
                train.playoff[indices],
                train.champion[indices],
                tuple(train.league_ids[index] for index in indices),
            )
            losses.append(loss)
            step += 1
            _adam_step(model.params, gradients, moments, velocities, step)
        points, _, _ = model.forward(validation_picks, validation.mask, validation_context)
        mae = float(np.mean(np.abs(np.clip(points * 100.0, 0.0, 100.0) - validation.points * 100.0)))
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)), "validation_points_mae": mae})
        if best is None or mae < best[0] - STOPPING_RULE["minimum_improvement"]:
            best = (mae, epoch, {name: value.copy() for name, value in model.params.items()})
            stale = 0
        else:
            stale += 1
            if stale >= STOPPING_RULE["patience"]:
                break
    model.params = best[2]
    return model, normalizer, {"best_epoch": best[1], "epochs_run": len(history), "history": history}


def _adam_step(params, gradients, moments, velocities, step):
    beta1 = OPTIMIZER["beta1"]
    beta2 = OPTIMIZER["beta2"]
    for name, parameter in params.items():
        gradient = gradients[name].astype(np.float32)
        moments[name] *= beta1
        moments[name] += (1 - beta1) * gradient
        velocities[name] *= beta2
        velocities[name] += (1 - beta2) * gradient * gradient
        corrected_m = moments[name] / (1 - beta1**step)
        corrected_v = velocities[name] / (1 - beta2**step)
        parameter -= OPTIMIZER["learning_rate"] * corrected_m / (np.sqrt(corrected_v) + OPTIMIZER["epsilon"])


def predict_rows(model, normalizer, dataset, *, playoff_temperature=1.0, championship_temperature=1.0):
    picks, context = normalize_inputs(dataset, normalizer)
    points, playoff_logits, champion_logits = model.forward(picks, dataset.mask, context)
    playoff = _sigmoid(playoff_logits / playoff_temperature)
    champion = within_league_softmax(champion_logits / championship_temperature, dataset.league_ids)
    return [
        {
            **metadata,
            "predicted_points_for_percentile": float(np.clip(point * 100.0, 0.0, 100.0)),
            "predicted_playoff": float(np.clip(playoff_probability, 1e-15, 1 - 1e-15)),
            "predicted_champion": float(champion_probability),
        }
        for metadata, point, playoff_probability, champion_probability in zip(
            dataset.metadata, points, playoff, champion
        )
    ]


def within_league_softmax(logits, league_ids):
    logits = np.asarray(logits, dtype=np.float64)
    output = np.zeros(len(logits), dtype=np.float64)
    for indices in _league_groups(league_ids).values():
        values = logits[indices]
        weights = np.exp(values - values.max())
        output[indices] = weights / weights.sum()
    return output


def _championship_loss_and_gradient(logits, champion, league_ids):
    gradient = np.zeros_like(logits, dtype=np.float32)
    groups = _league_groups(league_ids)
    losses = []
    for indices in groups.values():
        labels = champion[indices]
        if not np.isclose(labels.sum(), 1.0):
            raise ValueError("championship training group does not have exactly one champion")
        values = logits[indices]
        weights = np.exp(values - values.max())
        probabilities = weights / weights.sum()
        losses.append(-math.log(max(float(probabilities[labels == 1][0]), 1e-15)))
        gradient[indices] = probabilities - labels
    gradient /= len(groups)
    return float(np.mean(losses)), gradient


def _league_groups(league_ids):
    groups = defaultdict(list)
    for index, league_id in enumerate(league_ids):
        groups[league_id].append(index)
    return {key: np.asarray(indices, dtype=np.int64) for key, indices in sorted(groups.items())}


def _sigmoid(values):
    values = np.asarray(values)
    return np.where(values >= 0, 1 / (1 + np.exp(-values)), np.exp(values) / (1 + np.exp(values)))


def _select_temperatures(model, normalizer, validation):
    picks, context = normalize_inputs(validation, normalizer)
    _, playoff_logits, champion_logits = model.forward(picks, validation.mask, context)
    playoff_best = min(
        (
            _binary_log_loss(validation.playoff, _sigmoid(playoff_logits / temperature)),
            temperature,
        )
        for temperature in TEMPERATURES
    )
    champion_best = min(
        (
            _champion_log_loss(validation.champion, within_league_softmax(champion_logits / temperature, validation.league_ids)),
            temperature,
        )
        for temperature in TEMPERATURES
    )
    return {"playoff": playoff_best[1], "championship": champion_best[1]}


def _binary_log_loss(actual, prediction):
    prediction = np.clip(prediction, 1e-15, 1 - 1e-15)
    return float(np.mean(-(actual * np.log(prediction) + (1 - actual) * np.log1p(-prediction))))


def _champion_log_loss(actual, prediction):
    return float(np.mean(-np.log(np.clip(prediction[np.asarray(actual) == 1], 1e-15, 1))))


def fit_completed_draft_model(
    split_manifest,
    baseline_manifest,
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
    batch_size=128,
    bootstrap_samples=200,
):
    if seed != SEED:
        raise ValueError(f"HDVN-06 uses the frozen seed {SEED}")
    if bootstrap_samples < 2:
        raise ValueError("bootstrap needs at least two samples")
    output_directory = Path(output_directory).resolve()
    model_path = output_directory / "model.json"
    prediction_path = output_directory / "predictions-2024.parquet"
    report_path = output_directory / "validation-report.json"
    manifest_path = output_directory / "neural-artifact.manifest.json"
    paths = (model_path, prediction_path, report_path, manifest_path)
    if any(path.exists() for path in paths):
        raise FileExistsError(f"immutable neural output already exists: {output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)

    expected_split = {
        "source_snapshot_sha256": source_snapshot_hash,
        "feature_manifest_hash": feature_manifest_hash,
        "tables_manifest_hash": tables_manifest_hash,
        "label_manifest_hash": label_manifest_hash,
    }
    datasets = load_completed_draft_datasets(split_manifest, expected=expected_split)
    split_hash = datasets.split_manifest["sha256"]
    baseline = load_baseline_bundle(baseline_manifest, expected={
        "source_snapshot_sha256": source_snapshot_hash,
        "feature_manifest_hash": feature_manifest_hash,
        "market_manifest_hash": market_manifest_hash,
        "tables_manifest_hash": tables_manifest_hash,
        "label_manifest_hash": label_manifest_hash,
        "split_manifest_hash": split_hash,
    })
    model, normalizer, training = train_network(
        datasets.train,
        datasets.validation,
        seed=seed,
        batch_size=batch_size,
    )
    temperatures = _select_temperatures(model, normalizer, datasets.validation)
    predictions = predict_rows(
        model,
        normalizer,
        datasets.validation,
        playoff_temperature=temperatures["playoff"],
        championship_temperature=temperatures["championship"],
    )
    metrics = evaluate_predictions(predictions)
    bootstrap = _clustered_bootstrap_metrics(predictions, seed=seed, samples=bootstrap_samples)
    baseline_predictions = _load_baseline_predictions(Path(baseline_manifest).parent, baseline)
    comparisons = _baseline_comparisons(
        predictions,
        baseline_predictions,
        seed=seed,
        samples=bootstrap_samples,
    )
    primary_intervals_pass = all(
        comparisons[name]["paired_points_absolute_error_difference"]["high"] < 0
        for name in PRIMARY_BASELINES
    )
    gate = {
        "predeclared_points_mae_threshold": PASS_MAE,
        "points_mae": metrics["points_percentile"]["mae"],
        "points_mae_pass": metrics["points_percentile"]["mae"] <= PASS_MAE,
        "paired_intervals_pass": primary_intervals_pass,
        "primary_baselines": list(PRIMARY_BASELINES),
    }
    gate["passed"] = gate["points_mae_pass"] and gate["paired_intervals_pass"]
    status = "candidate" if gate["passed"] else "rejected"
    probability_error = _maximum_probability_sum_error(predictions)
    if probability_error > 1e-12:
        raise ValueError("championship probabilities do not sum to one")

    payload = {
        "artifact_version": NEURAL_ARTIFACT_VERSION,
        "architecture": ARCHITECTURE,
        "parameter_count": model.parameter_count,
        "pick_feature_order": list(PICK_FEATURE_ORDER),
        "context_feature_order": list(CONTEXT_FEATURE_ORDER),
        "normalizer": {name: value.tolist() for name, value in normalizer.items()},
        "parameters": {name: value.tolist() for name, value in model.params.items()},
        "temperatures": temperatures,
    }
    model_path.write_text(canonical_json(payload) + "\n")
    _write_predictions(predictions, prediction_path)
    repeat_path = output_directory / "predictions-2024.repeat.parquet"
    _write_predictions(predictions, repeat_path)
    prediction_hash = sha256_file(prediction_path)
    repeated_prediction_hash = sha256_file(repeat_path)
    repeat_path.unlink()
    if repeated_prediction_hash != prediction_hash:
        raise ValueError("repeated prediction generation is not byte-identical")

    report = {
        "evaluation_version": EVALUATION_VERSION,
        "validation_year": 2024,
        "status": status,
        "gate": gate,
        "metrics": metrics,
        "bootstrap_intervals": bootstrap,
        "baseline_comparisons": comparisons,
        "calibration": metrics["calibration"],
        "slices": _slices(predictions),
        "market_support_and_missing_feature_coverage": _support_coverage(predictions),
        "championship_probability_maximum_sum_error": probability_error,
        "training": training,
        "loaded_partitions": ["train", "validation"],
        "opened_partition_files": list(datasets.opened_paths),
        "locked_test_loaded": False,
        "reproducibility": {
            "prediction_sha256": prediction_hash,
            "repeated_prediction_sha256": repeated_prediction_hash,
            "identical": True,
        },
    }
    report_path.write_text(canonical_json(report) + "\n")
    manifest = {
        "artifact_version": NEURAL_ARTIFACT_VERSION,
        "status": status,
        "source_snapshot_sha256": source_snapshot_hash,
        "feature_manifest_hash": feature_manifest_hash,
        "market_manifest_hash": market_manifest_hash,
        "tables_manifest_hash": tables_manifest_hash,
        "label_manifest_hash": label_manifest_hash,
        "split_manifest_hash": split_hash,
        "baseline_manifest_hash": baseline["sha256"],
        "code_revision": code_revision,
        "code_sha256": sha256_file(Path(__file__)),
        "deterministic_feature_order": {
            "pick": list(PICK_FEATURE_ORDER),
            "context": list(CONTEXT_FEATURE_ORDER),
        },
        "architecture": ARCHITECTURE,
        "parameter_count": model.parameter_count,
        "optimizer": OPTIMIZER,
        "learning_rate": OPTIMIZER["learning_rate"],
        "loss_weights": LOSS_WEIGHTS,
        "seed": seed,
        "batch_size_league_seasons": batch_size,
        "stopping_rule": STOPPING_RULE,
        "counts": {
            "train_rows": len(datasets.train.metadata),
            "validation_rows": len(datasets.validation.metadata),
            "train_league_seasons": len(set(datasets.train.league_ids)),
            "validation_league_seasons": len(set(datasets.validation.league_ids)),
        },
        "validation_metrics": metrics,
        "bootstrap_intervals": bootstrap,
        "calibration": metrics["calibration"],
        "gate": gate,
        "limitations": LIMITATIONS,
        "loaded_partitions": ["train", "validation"],
        "locked_test_loaded": False,
        "prediction_generation_sha256": prediction_hash,
        "command": command,
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in (model_path, prediction_path, report_path)
        },
    }
    if status not in ALLOWED_STATUSES:
        raise ValueError("neural artifact status is invalid")
    manifest["sha256"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    manifest_path.write_text(canonical_json(manifest) + "\n")
    load_neural_artifact(manifest_path, expected={
        "source_snapshot_sha256": source_snapshot_hash,
        "feature_manifest_hash": feature_manifest_hash,
        "market_manifest_hash": market_manifest_hash,
        "tables_manifest_hash": tables_manifest_hash,
        "label_manifest_hash": label_manifest_hash,
        "split_manifest_hash": split_hash,
        "status": status,
        "parameter_count": model.parameter_count,
    })
    for path in paths:
        path.chmod(0o444)
    return manifest


def load_neural_artifact(manifest_path, *, expected=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = _load_hashed_json(manifest_path, "neural artifact manifest")
    if manifest.get("status") not in ALLOWED_STATUSES:
        raise ValueError("neural artifact status is invalid")
    if manifest.get("locked_test_loaded") is not False:
        raise ValueError("neural artifact touched locked test")
    if manifest.get("loaded_partitions") != ["train", "validation"]:
        raise ValueError("neural artifact loaded an invalid partition set")
    if manifest.get("deterministic_feature_order") != {
        "pick": list(PICK_FEATURE_ORDER),
        "context": list(CONTEXT_FEATURE_ORDER),
    }:
        raise ValueError("neural artifact feature order mismatch")
    for filename, record in manifest.get("files", {}).items():
        path = manifest_path.parent / filename
        if sha256_file(path) != record["sha256"]:
            raise ValueError(f"neural artifact file hash mismatch: {filename}")
    payload = json.loads((manifest_path.parent / "model.json").read_text())
    model = CompletedDraftNetwork(params=payload["parameters"])
    if payload.get("parameter_count") != model.parameter_count:
        raise ValueError("neural model parameter count mismatch")
    if manifest.get("parameter_count") != model.parameter_count:
        raise ValueError("neural manifest parameter count mismatch")
    if payload.get("pick_feature_order") != list(PICK_FEATURE_ORDER):
        raise ValueError("neural model pick feature mismatch")
    if payload.get("context_feature_order") != list(CONTEXT_FEATURE_ORDER):
        raise ValueError("neural model context feature mismatch")
    for key, value in (expected or {}).items():
        if manifest.get(key) != value:
            raise ValueError(f"neural artifact context mismatch for {key}")
    return manifest


def _write_predictions(rows, path):
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("HDVN neural fitting requires pinned research dependencies") from error
    pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd")


def _load_baseline_predictions(directory, manifest):
    try:
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("HDVN neural fitting requires pinned research dependencies") from error
    filename = next(name for name in manifest["files"] if name.startswith("predictions-"))
    rows = pq.read_table(directory / filename).to_pylist()
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.pop("baseline")].append(row)
    required = {"uniform_championship", *PRIMARY_BASELINES}
    if set(grouped) != required:
        raise ValueError("baseline predictions are incomplete")
    return grouped


def _baseline_comparisons(neural_rows, baseline_sets, *, seed, samples):
    neural_by_key = {_row_key(row): row for row in neural_rows}
    result = {}
    for offset, (name, rows) in enumerate(sorted(baseline_sets.items())):
        baseline_by_key = {_row_key(row): row for row in rows}
        if set(baseline_by_key) != set(neural_by_key):
            raise ValueError(f"baseline row identity mismatch: {name}")
        aligned = [baseline_by_key[_row_key(row)] for row in neural_rows]
        differences = [
            (
                row["league_season_id"],
                abs(row["predicted_points_for_percentile"] - row["points_for_percentile"])
                - abs(baseline["predicted_points_for_percentile"] - baseline["points_for_percentile"]),
            )
            for row, baseline in zip(neural_rows, aligned)
        ]
        result[name] = {
            "metrics": evaluate_predictions(aligned),
            "paired_points_absolute_error_difference": _clustered_mean_interval(
                differences,
                seed=seed + 100 + offset,
                samples=samples,
            ),
        }
    return result


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


def _clustered_bootstrap_metrics(rows, *, seed, samples, confidence=0.95):
    clusters = defaultdict(list)
    for row in rows:
        clusters[row["league_season_id"]].append(row)
    keys = sorted(clusters)
    rng = random.Random(seed)
    distributions = defaultdict(list)
    for _ in range(samples):
        sampled = [row for _ in keys for row in clusters[rng.choice(keys)]]
        for name, value in _core_metrics(sampled).items():
            distributions[name].append(value)
    result = {}
    tail = (1 - confidence) / 2
    estimates = _core_metrics(rows)
    for name, values in distributions.items():
        values.sort()
        result[name] = {
            "estimate": estimates[name],
            "low": values[max(0, int(tail * samples))],
            "high": values[min(samples - 1, math.ceil((1 - tail) * samples) - 1)],
            "samples": samples,
            "seed": seed,
        }
    return result


def _core_metrics(rows):
    point_errors = [row["predicted_points_for_percentile"] - row["points_for_percentile"] for row in rows]
    playoff_predictions = np.asarray([row["predicted_playoff"] for row in rows])
    playoff_actual = np.asarray([row["made_playoffs"] for row in rows])
    champion_losses = [
        -math.log(max(row["predicted_champion"], 1e-15))
        for row in rows
        if row["champion"] == 1
    ]
    return {
        "points_mae": sum(abs(value) for value in point_errors) / len(point_errors),
        "points_rmse": math.sqrt(sum(value * value for value in point_errors) / len(point_errors)),
        "playoff_log_loss": _binary_log_loss(playoff_actual, playoff_predictions),
        "playoff_brier": float(np.mean((playoff_predictions - playoff_actual) ** 2)),
        "championship_log_loss": sum(champion_losses) / len(champion_losses),
    }


def _slices(rows):
    grouped = defaultdict(list)
    for row in rows:
        for field in ("scoring_format", "team_count", "draft_slot"):
            grouped[(field, row[field])].append(row)
    return [
        {
            "field": field,
            "value": value,
            "rows": len(group),
            "league_seasons": len({row["league_season_id"] for row in group}),
            "metrics": _core_metrics(group),
            "missing_feature_rows": sum(bool(row["missing_features"]) for row in group),
        }
        for (field, value), group in sorted(grouped.items(), key=lambda item: (item[0][0], str(item[0][1])))
    ]


def _support_coverage(rows):
    support = [row["market_support_drafts"] for row in rows]
    coverage = [row["market_pick_coverage"] for row in rows]
    missing = sum(row["missing_features"] for row in rows)
    return {
        "rows": len(rows),
        "market_supported_rows": len(rows) - missing,
        "missing_feature_rows": missing,
        "missing_feature_rate": missing / len(rows),
        "mean_pick_market_coverage": sum(coverage) / len(coverage),
        "minimum_market_support_drafts": min(support),
        "median_market_support_drafts": float(np.median(support)),
        "maximum_market_support_drafts": max(support),
    }


def _maximum_probability_sum_error(rows):
    sums = defaultdict(float)
    for row in rows:
        sums[row["league_season_id"]] += row["predicted_champion"]
    return max(abs(value - 1.0) for value in sums.values())


def _row_key(row):
    return int(row["season"]), row["league_id"], int(row["roster_id"])


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
