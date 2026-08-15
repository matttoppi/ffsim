import json
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.validate_racing_corpus import (
    SCHEMA_VERSION,
    _evaluate_state,
    _prepare_snapshot,
    _read_checkpoint,
    _rebuild_states,
    _run_identity,
    aggregate_records,
    compare_outcomes,
    resume_keys,
    validate,
)


TEST_RUN_IDENTITY = {"snapshot_sha256": "test"}


def mode_result(headline, status, practical, survivors, work, seconds):
    return {
        "headline_candidate_id": headline,
        "decision_status": status,
        "practical_co_leader_candidate_ids": practical,
        "survivor_candidate_ids": survivors,
        "work": {"screen": work // 2, "refinement": work // 2, "total": work},
        "timing_seconds": {
            "screen": seconds / 2,
            "refinement": seconds / 2,
            "total": seconds,
        },
    }


def record(pick_no, racing, flat, run_identity=TEST_RUN_IDENTITY):
    comparison = compare_outcomes(racing, flat)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_identity": run_identity,
        "batch_id": "batch",
        "session_id": "session",
        "pick_no": pick_no,
        "status": "mismatch" if comparison["mismatch"] else "ok",
        "racing": racing,
        "flat": flat,
        "comparison": comparison,
    }


class RacingCorpusValidatorTest(unittest.TestCase):
    def test_rebuild_rejects_a_changed_league_evaluator(self):
        session = {
            "session_id": "session",
            "config": {
                "scenario": {
                    "template_draft_id": "draft",
                    "user_roster_id": 1,
                },
                "prepared": {
                    "market_snapshot_id": "market",
                    "world_bank": {"version": "world"},
                },
            },
            "states": [{
                "recorded_ready": {"league_evaluator_version": "recorded"}
            }],
        }
        template = SimpleNamespace(
            scenario={"template_draft_id": "draft"},
            prepared=SimpleNamespace(
                summary={
                    "market_snapshot_id": "market",
                    "world_bank": {"version": "world"},
                },
                evaluator=SimpleNamespace(version="changed"),
            ),
        )

        with self.assertRaisesRegex(ValueError, "league evaluator changed"):
            _rebuild_states(session, template, set())

    def test_checkpoint_and_snapshot_paths_must_differ(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "shared"
            args = SimpleNamespace(
                output=path,
                snapshot=path,
                batch_id="batch",
            )

            with self.assertRaisesRegex(ValueError, "must differ"):
                validate(args)

    def test_flat_uses_one_independent_full_budget_extension(self):
        calls = []

        class Evaluation:
            def __init__(self, candidate_ids, rollout_count):
                self.candidates = tuple(
                    SimpleNamespace(candidate_id=candidate_id)
                    for candidate_id in candidate_ids
                )
                self.rollout_count = rollout_count

            def paired_value_delta(self, _leader_id, _candidate_id):
                return SimpleNamespace(interval=(-0.1, 0.1))

        def evaluate(
            _prepared,
            _state,
            rollout_ids,
            candidate_ids,
            **_kwargs,
        ):
            if isinstance(rollout_ids, int):
                start, stop = 0, rollout_ids
            else:
                start, stop = rollout_ids.start, rollout_ids.stop
            calls.append((start, stop, tuple(candidate_ids)))
            return Evaluation(candidate_ids, stop)

        def payload(_prepared, _state, evaluations, _candidate_count):
            evaluation = evaluations[-1]
            candidate_ids = tuple(
                candidate.candidate_id for candidate in evaluation.candidates
            )
            return {
                "candidates": [
                    {"player_id": candidate_id} for candidate_id in candidate_ids
                ],
                "co_leader_candidate_ids": candidate_ids,
                "recommended_candidate_id": candidate_ids[0],
                "decision_status": "toss_up",
            }

        item = {"state": object(), "candidate_ids": ("a", "b", "c")}
        patches = (
            patch(
                "tools.validate_racing_corpus.evaluate_live_candidates",
                side_effect=evaluate,
            ),
            patch(
                "tools.validate_racing_corpus.live_recommendation_payload",
                side_effect=payload,
            ),
            patch(
                "tools.validate_racing_corpus.select_finalists",
                return_value=("a", "b"),
            ),
            patch(
                "tools.validate_racing_corpus.merge_screen_refinement",
                side_effect=lambda _previous, extension: extension,
            ),
            patch(
                "tools.validate_racing_corpus.rank_candidates",
                side_effect=lambda evaluation: evaluation.candidates,
            ),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            racing = _evaluate_state(object(), item, None, "racing")
            racing_calls = list(calls)
            calls.clear()
            flat = _evaluate_state(object(), item, None, "flat")

        self.assertEqual(racing_calls, [
            (0, 100, ("a", "b", "c")),
            (100, 150, ("a", "b")),
            (150, 225, ("a", "b")),
            (225, 300, ("a", "b")),
        ])
        self.assertEqual(calls, [
            (0, 100, ("a", "b", "c")),
            (100, 300, ("a", "b")),
        ])
        self.assertEqual(
            [stage["rollout_count"] for stage in racing["stages"]],
            [150, 225, 300],
        )
        self.assertEqual(
            [stage["rollout_count"] for stage in flat["stages"]],
            [300],
        )
        self.assertEqual(racing["work"], flat["work"])

    def test_resume_reuses_the_original_snapshot_and_requires_it(self):
        with TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.sqlite3"
            snapshot.write_bytes(b"frozen")
            with patch(
                "tools.validate_racing_corpus._snapshot_database"
            ) as backup:
                status = _prepare_snapshot("live.sqlite3", snapshot, True)

            backup.assert_not_called()
            self.assertEqual(status, "Reusing telemetry snapshot")
            self.assertEqual(snapshot.read_bytes(), b"frozen")
            snapshot.unlink()
            with self.assertRaisesRegex(
                FileNotFoundError, "Checkpoint snapshot not found"
            ):
                _prepare_snapshot("live.sqlite3", snapshot, True)

    def test_comparison_flags_every_mismatch_and_unsafe_elimination(self):
        racing = mode_result("a", "toss_up", ["a"], ["a"], 50, 1.0)
        flat = mode_result("b", "clear_leader", ["a", "b"], ["a", "b"], 100, 2.0)

        comparison = compare_outcomes(racing, flat)

        self.assertFalse(comparison["headline_match"])
        self.assertFalse(comparison["decision_status_match"])
        self.assertFalse(comparison["practical_co_leaders_match"])
        self.assertEqual(comparison["unsafe_eliminated_candidate_ids"], ["b"])
        self.assertTrue(comparison["mismatch"])

    def test_aggregate_sums_exact_work_timings_and_mismatches(self):
        tied = mode_result("a", "toss_up", ["a"], ["a"], 100, 1.0)
        flat_tied = mode_result("a", "toss_up", ["a"], ["a"], 100, 2.0)
        mismatched = mode_result("a", "toss_up", ["a"], ["a"], 100, 1.5)
        flat_mismatched = mode_result(
            "b", "toss_up", ["a", "b"], ["a", "b"], 100, 2.5
        )

        summary = aggregate_records([
            record(1, tied, flat_tied),
            record(2, mismatched, flat_mismatched),
        ], 10)

        self.assertEqual(summary["completed"], 2)
        self.assertEqual(summary["mismatches"], 1)
        self.assertEqual(summary["run_identity"], TEST_RUN_IDENTITY)
        self.assertEqual(summary["unsafe_elimination_states"], 1)
        self.assertEqual(summary["candidate_rollout_work"], {
            "racing": 200,
            "flat": 200,
        })
        self.assertEqual(summary["racing_to_flat_work_ratio"], 1.0)
        self.assertEqual(summary["timing_seconds"]["racing"]["total"], 2.5)
        self.assertEqual(summary["timing_seconds"]["flat"]["total"], 4.5)

    def test_resume_rejects_duplicates_and_trims_partial_final_record(self):
        result = mode_result("a", "clear_leader", ["a"], ["a"], 10, 1.0)
        completed = record(1, result, result)
        line = json.dumps(completed).encode() + b"\n"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.jsonl"
            path.write_bytes(line + b'{"schema_version":')

            records = _read_checkpoint(path)

            self.assertEqual(records, [completed])
            self.assertEqual(path.read_bytes(), line)
            self.assertEqual(
                resume_keys(records, "batch", TEST_RUN_IDENTITY),
                {("session", 1)},
            )
            with self.assertRaisesRegex(ValueError, "duplicate"):
                resume_keys(
                    [completed, completed], "batch", TEST_RUN_IDENTITY
                )

    def test_resume_rejects_changed_snapshot_identity_and_old_schema(self):
        result = mode_result("a", "clear_leader", ["a"], ["a"], 10, 1.0)
        with TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.sqlite3"
            snapshot.write_bytes(b"frozen-one")
            identity = _run_identity(snapshot)
            self.assertEqual(set(identity), {
                "snapshot_sha256",
                "decision_engine_version",
                "opponent_market_model_version",
                "roster_scorer_version",
                "vona_model_version",
                "seed",
                "screen_rollout_count",
                "finalist_count",
                "refinement_stages",
                "season_worlds_per_rollout",
                "evaluation_workers",
                "rollout_chunk",
                "live_temperature",
                "live_reach_rate",
            })
            completed = record(1, result, result, identity)

            snapshot.write_bytes(b"frozen-two")
            changed_snapshot = _run_identity(snapshot)
            self.assertNotEqual(
                identity["snapshot_sha256"],
                changed_snapshot["snapshot_sha256"],
            )
            with self.assertRaisesRegex(ValueError, "run identity"):
                resume_keys([completed], "batch", changed_snapshot)

            changed_seed = {**identity, "seed": identity["seed"] + 1}
            with self.assertRaisesRegex(ValueError, "run identity"):
                resume_keys([completed], "batch", changed_seed)

            changed_worlds = {
                **identity,
                "season_worlds_per_rollout": (
                    identity["season_worlds_per_rollout"] + 1
                ),
            }
            with self.assertRaisesRegex(ValueError, "run identity"):
                resume_keys([completed], "batch", changed_worlds)

            old = {**completed, "schema_version": SCHEMA_VERSION - 1}
            with self.assertRaisesRegex(ValueError, "schema version"):
                resume_keys([old], "batch", identity)


if __name__ == "__main__":
    unittest.main()
