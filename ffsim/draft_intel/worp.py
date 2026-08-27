"""Offline calibration for projected wins over replacement player."""

from bisect import bisect_right
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import sqrt
from pathlib import Path
import sqlite3

from ffsim.paths import CACHE_DIR


WORP_ARTIFACT_PATH = CACHE_DIR / "worp_calibration.json"
WORP_SCHEMA_VERSION = 1
WORP_MODEL_VERSION = "empirical-score-margin-v1"
DEFAULT_MIN_TRAINING_GAMES = 1_000
DEFAULT_MIN_VALIDATION_GAMES = 250
DEFAULT_MAX_ABSOLUTE_ERROR = 0.02
_POINTS_GRID = tuple(index / 2 for index in range(61))


@dataclass(frozen=True)
class WORPCurve:
    team_count: int
    scoring_format: str
    points_added: tuple[float, ...]
    expected_win_gain: tuple[float, ...]

    def wins_added(self, weekly_points: float) -> float:
        """Interpolate expected weekly win gain for a point advantage."""
        if not self.points_added:
            return 0.0
        sign = -1.0 if weekly_points < 0 else 1.0
        points = abs(float(weekly_points))
        if points >= self.points_added[-1]:
            return sign * self.expected_win_gain[-1]
        upper = bisect_right(self.points_added, points)
        if upper == 0:
            return 0.0
        lower = upper - 1
        left = self.points_added[lower]
        right = self.points_added[upper]
        weight = (points - left) / (right - left)
        gain = (
            self.expected_win_gain[lower] * (1 - weight)
            + self.expected_win_gain[upper] * weight
        )
        return sign * gain


def fit_worp_calibration(
    database_path,
    *,
    output_path=WORP_ARTIFACT_PATH,
    min_training_games=DEFAULT_MIN_TRAINING_GAMES,
    min_validation_games=DEFAULT_MIN_VALIDATION_GAMES,
    max_absolute_error=DEFAULT_MAX_ABSOLUTE_ERROR,
):
    """Fit candidate points-to-win curves from the historical Sleeper store."""
    database_path = Path(database_path)
    output_path = Path(output_path)
    if min_training_games < 1 or min_validation_games < 1:
        raise ValueError("WORP sample minimums must be positive")
    if not 0 < max_absolute_error < 1:
        raise ValueError("WORP maximum absolute error must be between zero and one")

    contexts = defaultdict(_empty_context)
    source_hash = sha256()
    league_seasons = set()
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        _require_tables(connection)
        rows = connection.execute(_MATCHUP_QUERY)
        current_key = None
        matchup = []
        for row in rows:
            key = (
                row["league_id"],
                int(row["season"]),
                int(row["week"]),
                int(row["matchup_id"]),
            )
            if current_key is not None and key != current_key:
                _add_matchup(contexts, current_key, matchup, source_hash, league_seasons)
                matchup = []
            current_key = key
            matchup.append(row)
        if current_key is not None:
            _add_matchup(contexts, current_key, matchup, source_hash, league_seasons)

    fitted = [
        _fit_context(
            key,
            samples,
            min_training_games=min_training_games,
            min_validation_games=min_validation_games,
            max_absolute_error=max_absolute_error,
        )
        for key, samples in sorted(contexts.items())
    ]
    artifact = {
        "schema_version": WORP_SCHEMA_VERSION,
        "model_version": WORP_MODEL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "candidate" if any(row["status"] == "candidate" for row in fitted) else "unvalidated",
        "source": {
            "database_path": str(database_path),
            "input_hash": source_hash.hexdigest(),
            "league_seasons": len(league_seasons),
            "games": sum(row["all_games"] for row in fitted),
        },
        "split": {
            "method": "league-season-sha256-mod-5",
            "validation_remainder": 0,
        },
        "thresholds": {
            "minimum_training_games": int(min_training_games),
            "minimum_validation_games": int(min_validation_games),
            "maximum_absolute_error": float(max_absolute_error),
            "confidence_level": 0.95,
        },
        "contexts": fitted,
    }
    _write_artifact(output_path, artifact)
    return artifact


def approve_worp_context(path, team_count, scoring_format, decision_reference):
    """Approve one statistically qualified context for live WORP use."""
    path = Path(path)
    decision_reference = str(decision_reference).strip()
    if not decision_reference:
        raise ValueError("WORP approval requires a decision reference")
    artifact = json.loads(path.read_text())
    if (
        artifact.get("schema_version") != WORP_SCHEMA_VERSION
        or artifact.get("model_version") != WORP_MODEL_VERSION
    ):
        raise ValueError("WORP artifact version is not supported")
    team_count = int(team_count)
    scoring_format = str(scoring_format).upper()
    row = next(
        (
            candidate
            for candidate in artifact.get("contexts", ())
            if candidate.get("team_count") == team_count
            and candidate.get("scoring_format") == scoring_format
        ),
        None,
    )
    if row is None:
        raise ValueError("WORP artifact does not contain the requested context")
    if row.get("status") != "candidate":
        raise ValueError("WORP context must pass candidate gates before approval")
    row["status"] = "validated"
    row["approval"] = {
        "decision_reference": decision_reference,
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    artifact["status"] = "validated"
    _write_artifact(path, artifact)
    return artifact


def load_worp_curve(team_count, scoring_format, path=WORP_ARTIFACT_PATH):
    """Load one exact validated context; never fall back across league formats."""
    path = Path(path)
    context = {
        "team_count": int(team_count),
        "scoring_format": str(scoring_format).upper(),
    }
    if not path.exists():
        return None, {"status": "artifact_missing", **context}
    artifact = json.loads(path.read_text())
    if artifact.get("schema_version") != WORP_SCHEMA_VERSION:
        return None, {"status": "schema_mismatch", **context}
    if artifact.get("model_version") != WORP_MODEL_VERSION:
        return None, {"status": "model_mismatch", **context}
    row = next(
        (
            candidate
            for candidate in artifact.get("contexts", ())
            if candidate.get("team_count") == context["team_count"]
            and candidate.get("scoring_format") == context["scoring_format"]
        ),
        None,
    )
    if row is None:
        return None, {"status": "context_missing", **context}
    if row.get("status") != "validated":
        return None, {
            "status": row.get("status", "unvalidated"),
            "training_games": row.get("training_games", 0),
            "validation_games": row.get("validation_games", 0),
            **context,
        }
    approval = row.get("approval") or {}
    if not approval.get("decision_reference"):
        return None, {"status": "approval_missing", **context}
    points = tuple(float(value) for value in row.get("points_added", ()))
    gains = tuple(float(value) for value in row.get("expected_win_gain", ()))
    if (
        len(points) < 2
        or len(points) != len(gains)
        or points[0] != 0
        or gains[0] != 0
        or any(right <= left for left, right in zip(points, points[1:]))
        or any(right < left for left, right in zip(gains, gains[1:]))
    ):
        return None, {"status": "invalid_curve", **context}
    return WORPCurve(context["team_count"], context["scoring_format"], points, gains), {
        "status": "validated",
        "model_version": WORP_MODEL_VERSION,
        "training_games": row["training_games"],
        "validation_games": row["validation_games"],
        **context,
        "decision_reference": approval["decision_reference"],
    }


def projected_worp(value_over_replacement, projection_weeks, regular_season_weeks, curve):
    """Convert season VORP to regular-season projected wins."""
    if projection_weeks < 1 or regular_season_weeks < 1:
        raise ValueError("WORP week counts must be positive")
    weekly_points = float(value_over_replacement) / projection_weeks
    return curve.wins_added(weekly_points) * regular_season_weeks


def _empty_context():
    return {
        "train": Counter(),
        "validation": Counter(),
        "all": Counter(),
        "train_games": 0,
        "validation_games": 0,
        "all_games": 0,
        "train_leagues": set(),
        "validation_leagues": set(),
    }


def _require_tables(connection):
    available = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    required = {"league_seasons", "weekly_matchups", "quality_flags"}
    missing = sorted(required - available)
    if missing:
        raise ValueError("Historical database is missing tables: " + ", ".join(missing))


def _add_matchup(contexts, key, rows, source_hash, league_seasons):
    if len(rows) != 2:
        return
    left, right = rows
    left_score = _score(left)
    right_score = _score(right)
    if left_score is None or right_score is None:
        return
    context_key = (int(left["total_rosters"]), str(left["scoring_format"]).upper())
    league_key = f"{key[0]}:{key[1]}"
    validation = int(sha256(league_key.encode()).hexdigest()[:8], 16) % 5 == 0
    margin = int(round((left_score - right_score) * 100))
    samples = contexts[context_key]
    target = samples["validation"] if validation else samples["train"]
    target[margin] += 1
    target[-margin] += 1
    samples["all"][margin] += 1
    samples["all"][-margin] += 1
    split = "validation" if validation else "train"
    samples[f"{split}_games"] += 1
    samples["all_games"] += 1
    samples[f"{split}_leagues"].add(league_key)
    league_seasons.add(league_key)
    source_hash.update(
        f"{league_key}|{key[2]}|{key[3]}|{context_key[0]}|{context_key[1]}|{margin}\n".encode()
    )


def _score(row):
    value = row["custom_points"] if row["custom_points"] is not None else row["points"]
    return None if value is None else float(value)


def _fit_context(key, samples, *, min_training_games, min_validation_games, max_absolute_error):
    train_curve = _curve(samples["train"])
    validation_curve = _curve(samples["validation"])
    all_curve = _curve(samples["all"])
    errors = [
        observed - predicted
        for predicted, observed in zip(train_curve, validation_curve)
    ]
    rmse = sqrt(sum(error * error for error in errors) / len(errors))
    max_error = max(map(abs, errors))
    observations = max(1, sum(samples["validation"].values()))
    allowed = [
        max(
            max_absolute_error,
            1.96 * sqrt(max(observed * (1 - observed), 0.0) / observations),
        )
        for observed in validation_curve
    ]
    enough = (
        samples["train_games"] >= min_training_games
        and samples["validation_games"] >= min_validation_games
    )
    passes = all(abs(error) <= limit for error, limit in zip(errors, allowed))
    status = "candidate" if enough and passes else "insufficient_data" if not enough else "validation_failed"
    return {
        "team_count": key[0],
        "scoring_format": key[1],
        "status": status,
        "training_games": samples["train_games"],
        "validation_games": samples["validation_games"],
        "all_games": samples["all_games"],
        "training_league_seasons": len(samples["train_leagues"]),
        "validation_league_seasons": len(samples["validation_leagues"]),
        "points_added": list(_POINTS_GRID),
        "expected_win_gain": all_curve,
        "validation": {
            "rmse": rmse,
            "maximum_absolute_error": max_error,
            "maximum_allowed_error": max(allowed),
            "passed": bool(enough and passes),
        },
    }

def _write_artifact(path, artifact):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _curve(margins):
    observations = sum(margins.values())
    if not observations:
        return [0.0] * len(_POINTS_GRID)
    return [
        sum(
            count * (_win_credit(margin + int(round(points * 100))) - _win_credit(margin))
            for margin, count in margins.items()
        )
        / observations
        for points in _POINTS_GRID
    ]


def _win_credit(margin):
    return 1.0 if margin > 0 else 0.5 if margin == 0 else 0.0


_MATCHUP_QUERY = """
SELECT
    w.league_id,
    w.season,
    w.week,
    w.matchup_id,
    w.roster_id,
    w.points,
    w.custom_points,
    l.total_rosters,
    l.scoring_format
FROM weekly_matchups AS w
JOIN league_seasons AS l
  ON l.league_id = w.league_id AND l.season = w.season
WHERE l.is_candidate = 1
  AND l.total_rosters IS NOT NULL
  AND w.matchup_id IS NOT NULL
  AND w.week <= COALESCE(l.playoff_week_start - 1, l.last_scored_leg)
  AND NOT EXISTS (
      SELECT 1
      FROM quality_flags AS q
      WHERE q.scope = 'league_season'
        AND q.entity_key = w.league_id || ':' || w.season
        AND q.severity = 'error'
  )
ORDER BY w.league_id, w.season, w.week, w.matchup_id, w.roster_id
"""
