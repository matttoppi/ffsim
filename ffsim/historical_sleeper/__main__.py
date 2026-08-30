import argparse
import json
import signal
import shutil
import sys
import time
import shlex
from datetime import datetime, timezone
from pathlib import Path

from .dashboard import crawler_runtime, render_dashboard, sqlite_storage
from .crawl import DatasetCrawler, progress_line
from .export import export_parquet
from .continuous_survival import fit_continuous_survival
from .empirical_survival import build_empirical_survival
from .hierarchical_survival import build_hierarchical_survival
from .historical_projections import import_historical_projection_snapshot
from .hdvn_baselines import fit_baselines
from .hdvn_neural import fit_completed_draft_model
from .hdvn_residual import run_residual_alpha
from .manager_choice import build_manager_choice_artifact
from .opponent_model import fit_opponent_model
from .rank20_survival import build_rank20_survival_artifact
from .roster_manager_choice import build_roster_manager_choice_artifact
from .wait_reach_replay import run_wait_reach_replay
from .hdvn_contract import write_final_feature_manifest
from .hdvn_market import materialize_rolling_markets
from .hdvn_labels import materialize_labels_and_split
from .hdvn_snapshot import create_snapshot
from .hdvn_raw_audit import create_snapshot_acceptance, make_snapshot_files_read_only
from .hdvn_synthetic import run_synthetic_dry_run
from .hdvn_tables import materialize_training_tables
from .ingest import TARGET_SEASONS
from .rebuild import rebuild_from_raw
from .report import (
    DEFAULT_CANDIDATE_BUFFER,
    DEFAULT_MIN_TRAINING_READY_PER_YEAR,
    DEFAULT_TRAINING_READY_TARGET,
    quality_report,
    validate_dataset,
)
from .store import Store


DEFAULT_DATA_DIR = Path.home() / ".cache" / "ffsim" / "historical_sleeper"
DEFAULT_SEED = "mtoppi"


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "historical-projection-import":
        _print(
            import_historical_projection_snapshot(
                args.csv,
                args.evidence,
                args.output,
            )
        )
        return 0
    if args.command == "hdvn-dry-run":
        _print(run_synthetic_dry_run(args.output))
        return 0
    if args.command == "hdvn-feature-manifest":
        _print(
            write_final_feature_manifest(
                args.snapshot_manifest,
                args.acceptance,
                args.output,
            )
        )
        return 0
    if args.command == "hdvn-market":
        acceptance = json.loads(args.acceptance.read_text())
        features = json.loads(args.features.read_text())
        if not acceptance.get("passed"):
            raise ValueError("source snapshot acceptance did not pass")
        if features["source_snapshot_sha256"] != acceptance["snapshot_sha256"]:
            raise ValueError("feature and snapshot hashes do not match")
        command = shlex.join(
            ["python3", "-m", "ffsim.historical_sleeper", *(argv or sys.argv[1:])]
        )
        _print(
            materialize_rolling_markets(
                args.snapshot,
                args.output,
                source_snapshot_hash=acceptance["snapshot_sha256"],
                feature_manifest_hash=features["sha256"],
                command=command,
                min_support_drafts=args.min_support_drafts,
            )
        )
        return 0
    if args.command == "hdvn-tables":
        acceptance = json.loads(args.acceptance.read_text())
        features = json.loads(args.features.read_text())
        market_manifest = json.loads(args.market_manifest.read_text())
        if not acceptance.get("passed"):
            raise ValueError("source snapshot acceptance did not pass")
        if market_manifest["source_snapshot_sha256"] != acceptance["snapshot_sha256"]:
            raise ValueError("market and snapshot hashes do not match")
        if market_manifest["feature_manifest_hash"] != features["sha256"]:
            raise ValueError("market and feature hashes do not match")
        command = shlex.join(
            ["python3", "-m", "ffsim.historical_sleeper", *(argv or sys.argv[1:])]
        )
        _print(
            materialize_training_tables(
                args.snapshot,
                args.market_database,
                args.output,
                source_snapshot_hash=acceptance["snapshot_sha256"],
                source_manifest_hash=acceptance["snapshot_manifest_sha256"],
                feature_manifest_hash=features["sha256"],
                market_manifest_hash=market_manifest["sha256"],
                command=command,
                seed=args.seed,
                epoch=args.epoch,
                batch_size=args.batch_size,
            )
        )
        return 0
    if args.command == "hdvn-labels-split":
        acceptance = json.loads(args.acceptance.read_text())
        features = json.loads(args.features.read_text())
        tables_manifest = json.loads(args.tables_manifest.read_text())
        if not acceptance.get("passed"):
            raise ValueError("source snapshot acceptance did not pass")
        if tables_manifest["source_snapshot_sha256"] != acceptance["snapshot_sha256"]:
            raise ValueError("tables and snapshot hashes do not match")
        if tables_manifest["feature_manifest_hash"] != features["sha256"]:
            raise ValueError("tables and feature hashes do not match")
        command = shlex.join(
            ["python3", "-m", "ffsim.historical_sleeper", *(argv or sys.argv[1:])]
        )
        _print(
            materialize_labels_and_split(
                args.team_table,
                args.prefix_table,
                args.output,
                source_snapshot_hash=acceptance["snapshot_sha256"],
                feature_manifest_hash=features["sha256"],
                tables_manifest_hash=tables_manifest["sha256"],
                command=command,
                batch_size=args.batch_size,
            )
        )
        return 0
    if args.command == "hdvn-baselines":
        acceptance = json.loads(args.acceptance.read_text())
        features = json.loads(args.features.read_text())
        tables_manifest = json.loads(args.tables_manifest.read_text())
        market_manifest = json.loads(args.market_manifest.read_text())
        labels_manifest = json.loads(args.labels_manifest.read_text())
        if not acceptance.get("passed"):
            raise ValueError("source snapshot acceptance did not pass")
        if tables_manifest["feature_manifest_hash"] != features["sha256"]:
            raise ValueError("tables and feature hashes do not match")
        if labels_manifest["tables_manifest_hash"] != tables_manifest["sha256"]:
            raise ValueError("labels and tables hashes do not match")
        if tables_manifest["market_manifest_hash"] != market_manifest["sha256"]:
            raise ValueError("tables and market hashes do not match")
        command = shlex.join(
            ["python3", "-m", "ffsim.historical_sleeper", *(argv or sys.argv[1:])]
        )
        _print(
            fit_baselines(
                args.split_manifest,
                args.output,
                source_snapshot_hash=acceptance["snapshot_sha256"],
                feature_manifest_hash=features["sha256"],
                label_manifest_hash=labels_manifest["label_contract"]["sha256"],
                tables_manifest_hash=tables_manifest["sha256"],
                market_manifest_hash=market_manifest["sha256"],
                command=command,
                code_revision=args.code_revision,
                seed=args.seed,
                bootstrap_samples=args.bootstrap_samples,
            )
        )
        return 0
    if args.command == "hdvn-neural":
        acceptance = json.loads(args.acceptance.read_text())
        features = json.loads(args.features.read_text())
        tables_manifest = json.loads(args.tables_manifest.read_text())
        market_manifest = json.loads(args.market_manifest.read_text())
        labels_manifest = json.loads(args.labels_manifest.read_text())
        if not acceptance.get("passed"):
            raise ValueError("source snapshot acceptance did not pass")
        if tables_manifest["feature_manifest_hash"] != features["sha256"]:
            raise ValueError("tables and feature hashes do not match")
        if labels_manifest["tables_manifest_hash"] != tables_manifest["sha256"]:
            raise ValueError("labels and tables hashes do not match")
        if tables_manifest["market_manifest_hash"] != market_manifest["sha256"]:
            raise ValueError("tables and market hashes do not match")
        command = shlex.join(
            ["python3", "-m", "ffsim.historical_sleeper", *(argv or sys.argv[1:])]
        )
        _print(
            fit_completed_draft_model(
                args.split_manifest,
                args.baseline_manifest,
                args.output,
                source_snapshot_hash=acceptance["snapshot_sha256"],
                feature_manifest_hash=features["sha256"],
                label_manifest_hash=labels_manifest["label_contract"]["sha256"],
                tables_manifest_hash=tables_manifest["sha256"],
                market_manifest_hash=market_manifest["sha256"],
                command=command,
                code_revision=args.code_revision,
                seed=args.seed,
                batch_size=args.batch_size,
                bootstrap_samples=args.bootstrap_samples,
            )
        )
        return 0
    if args.command == "hdvn-residual-alpha":
        acceptance = json.loads(args.acceptance.read_text())
        features = json.loads(args.features.read_text())
        tables_manifest = json.loads(args.tables_manifest.read_text())
        market_manifest = json.loads(args.market_manifest.read_text())
        labels_manifest = json.loads(args.labels_manifest.read_text())
        if not acceptance.get("passed"):
            raise ValueError("source snapshot acceptance did not pass")
        if tables_manifest["feature_manifest_hash"] != features["sha256"]:
            raise ValueError("tables and feature hashes do not match")
        if labels_manifest["tables_manifest_hash"] != tables_manifest["sha256"]:
            raise ValueError("labels and tables hashes do not match")
        if tables_manifest["market_manifest_hash"] != market_manifest["sha256"]:
            raise ValueError("tables and market hashes do not match")
        command = shlex.join(
            ["python3", "-m", "ffsim.historical_sleeper", *(argv or sys.argv[1:])]
        )
        _print(
            run_residual_alpha(
                args.split_manifest,
                args.output,
                source_snapshot_hash=acceptance["snapshot_sha256"],
                feature_manifest_hash=features["sha256"],
                label_manifest_hash=labels_manifest["label_contract"]["sha256"],
                tables_manifest_hash=tables_manifest["sha256"],
                market_manifest_hash=market_manifest["sha256"],
                command=command,
                code_revision=args.code_revision,
                seed=args.seed,
                bootstrap_samples=args.bootstrap_samples,
            )
        )
        return 0
    if args.command == "opponent-model":
        acceptance = json.loads(args.acceptance.read_text())
        features = json.loads(args.features.read_text())
        if not acceptance.get("passed"):
            raise ValueError("source snapshot acceptance did not pass")
        if features["source_snapshot_sha256"] != acceptance["snapshot_sha256"]:
            raise ValueError("feature and snapshot hashes do not match")
        command = shlex.join(
            ["python3", "-m", "ffsim.historical_sleeper", *(argv or sys.argv[1:])]
        )
        _print(
            fit_opponent_model(
                args.market_database,
                args.market_manifest,
                args.output,
                expected_source_hash=acceptance["snapshot_sha256"],
                expected_feature_hash=features["sha256"],
                command=command,
                code_revision=args.code_revision,
                seed=args.seed,
                bootstrap_samples=args.bootstrap_samples,
            )
        )
        return 0
    if args.command == "continuous-survival":
        acceptance = json.loads(args.acceptance.read_text())
        features = json.loads(args.features.read_text())
        if not acceptance.get("passed"):
            raise ValueError("source snapshot acceptance did not pass")
        if features["source_snapshot_sha256"] != acceptance["snapshot_sha256"]:
            raise ValueError("feature and snapshot hashes do not match")
        command = shlex.join(
            ["python3", "-m", "ffsim.historical_sleeper", *(argv or sys.argv[1:])]
        )
        _print(
            fit_continuous_survival(
                args.market_database,
                args.market_manifest,
                args.output,
                expected_source_hash=acceptance["snapshot_sha256"],
                expected_feature_hash=features["sha256"],
                command=command,
                code_revision=args.code_revision,
                seed=args.seed,
                bootstrap_samples=args.bootstrap_samples,
            )
        )
        return 0
    if args.command == "empirical-survival":
        acceptance = json.loads(args.acceptance.read_text())
        features = json.loads(args.features.read_text())
        if not acceptance.get("passed"):
            raise ValueError("source snapshot acceptance did not pass")
        if features["source_snapshot_sha256"] != acceptance["snapshot_sha256"]:
            raise ValueError("feature and snapshot hashes do not match")
        command = shlex.join(
            ["python3", "-m", "ffsim.historical_sleeper", *(argv or sys.argv[1:])]
        )
        _print(
            build_empirical_survival(
                args.market_database,
                args.market_manifest,
                args.output,
                expected_source_hash=acceptance["snapshot_sha256"],
                expected_feature_hash=features["sha256"],
                command=command,
                code_revision=args.code_revision,
            )
        )
        return 0
    if args.command == "hierarchical-survival":
        acceptance = json.loads(args.acceptance.read_text())
        features = json.loads(args.features.read_text())
        if not acceptance.get("passed"):
            raise ValueError("source snapshot acceptance did not pass")
        if features["source_snapshot_sha256"] != acceptance["snapshot_sha256"]:
            raise ValueError("feature and snapshot hashes do not match")
        command = shlex.join(
            ["python3", "-m", "ffsim.historical_sleeper", *(argv or sys.argv[1:])]
        )
        _print(
            build_hierarchical_survival(
                args.market_database,
                args.market_manifest,
                args.output,
                expected_source_hash=acceptance["snapshot_sha256"],
                expected_feature_hash=features["sha256"],
                command=command,
                code_revision=args.code_revision,
                bootstrap_samples=args.bootstrap_samples,
            )
        )
        return 0
    if args.command == "rank20-survival":
        acceptance = json.loads(args.acceptance.read_text())
        features = json.loads(args.features.read_text())
        if not acceptance.get("passed"):
            raise ValueError("source snapshot acceptance did not pass")
        if features["source_snapshot_sha256"] != acceptance["snapshot_sha256"]:
            raise ValueError("feature and snapshot hashes do not match")
        command = shlex.join(
            ["python3", "-m", "ffsim.historical_sleeper", *(argv or sys.argv[1:])]
        )
        _print(
            build_rank20_survival_artifact(
                args.market_database,
                args.market_manifest,
                args.evidence,
                args.output,
                expected_source_hash=acceptance["snapshot_sha256"],
                expected_feature_hash=features["sha256"],
                command=command,
                code_revision=args.code_revision,
            )
        )
        return 0
    if args.command == "manager-choice":
        acceptance = json.loads(args.acceptance.read_text())
        features = json.loads(args.features.read_text())
        if not acceptance.get("passed"):
            raise ValueError("source snapshot acceptance did not pass")
        if features["source_snapshot_sha256"] != acceptance["snapshot_sha256"]:
            raise ValueError("feature and snapshot hashes do not match")
        command = shlex.join(
            ["python3", "-m", "ffsim.historical_sleeper", *(argv or sys.argv[1:])]
        )
        _print(
            build_manager_choice_artifact(
                args.source_database,
                args.market_database,
                args.market_manifest,
                args.benchmark,
                args.output,
                expected_source_hash=acceptance["snapshot_sha256"],
                expected_feature_hash=features["sha256"],
                command=command,
                code_revision=args.code_revision,
            )
        )
        return 0
    if args.command == "roster-manager-choice":
        acceptance = json.loads(args.acceptance.read_text())
        features = json.loads(args.features.read_text())
        if not acceptance.get("passed"):
            raise ValueError("source snapshot acceptance did not pass")
        if features["source_snapshot_sha256"] != acceptance["snapshot_sha256"]:
            raise ValueError("feature and snapshot hashes do not match")
        command = shlex.join(
            ["python3", "-m", "ffsim.historical_sleeper", *(argv or sys.argv[1:])]
        )
        _print(
            build_roster_manager_choice_artifact(
                args.source_database,
                args.market_database,
                args.market_manifest,
                args.benchmark,
                args.output,
                expected_source_hash=acceptance["snapshot_sha256"],
                expected_feature_hash=features["sha256"],
                command=command,
                code_revision=args.code_revision,
            )
        )
        return 0
    if args.command == "wait-reach-replay":
        command = shlex.join(
            ["python3", "-m", "ffsim.historical_sleeper", *(argv or sys.argv[1:])]
        )
        _print(
            run_wait_reach_replay(
                args.market_database,
                args.opponent_manifest,
                args.output,
                command=command,
                code_revision=args.code_revision,
                seed=args.seed,
                bootstrap_samples=args.bootstrap_samples,
            )
        )
        return 0
    store = Store(args.data_dir)

    if args.command == "status":
        try:
            _poll_status(
                store,
                interval=args.interval,
                once=args.once or not sys.stdout.isatty(),
                verbose=args.verbose,
            )
        except KeyboardInterrupt:
            print()
        return 0
    if args.command == "retry-failures":
        _print(store.retry_failures())
        return 0
    if args.command == "validate":
        report = validate_dataset(store)
        _print(report)
        return 0 if report["structurally_valid"] else 1
    if args.command == "export":
        _print(export_parquet(store, args.output, batch_size=args.batch_size))
        return 0
    if args.command == "rebuild":
        _print(rebuild_from_raw(store, args.output))
        return 0
    if args.command == "hdvn-snapshot":
        _print(create_snapshot(store.database_path, args.output))
        return 0
    if args.command == "hdvn-accept-snapshot":
        command = shlex.join(
            ["python3", "-m", "ffsim.historical_sleeper", *(argv or sys.argv[1:])]
        )
        acceptance = create_snapshot_acceptance(
            args.snapshot,
            args.data_dir,
            args.output,
            command=command,
        )
        make_snapshot_files_read_only(args.snapshot, args.output)
        _print(acceptance)
        return 0


    crawler = DatasetCrawler(
        store,
        requests_per_minute=args.rate,
        timeout=args.timeout,
        max_retries=args.retries,
        refresh=args.refresh,
    )
    if args.command == "seed":
        _print({"seeded": crawler.seed(args.usernames or [DEFAULT_SEED], args.seasons)})
        return 0
    if args.command == "players":
        _print({"players": crawler.refresh_players()})
        return 0

    previous_handler = signal.getsignal(signal.SIGINT)

    def stop(_signum, _frame):
        print("Stop requested. Finishing active requests; no new work will start.", flush=True)
        crawler.stop_event.set()

    signal.signal(signal.SIGINT, stop)
    try:
        if args.command == "collect":
            result = _run_collection(crawler, store, args)
        elif args.command == "discover":
            result = crawler.run_discovery(
                max_depth=args.max_depth,
                workers=args.workers,
                limit=args.limit,
                progress=progress_line,
            )
        else:
            enqueued = store.enqueue_hydration_candidates(args.enqueue) if args.enqueue else 0
            result = crawler.run_hydration(
                workers=args.workers,
                limit=args.limit,
                progress=progress_line,
            )
            result["enqueued"] = enqueued
    finally:
        signal.signal(signal.SIGINT, previous_handler)
    _print(result)
    return 2 if result["stopped_for_rate_limit"] else 0


def _run_collection(crawler, store, args, *, progress=progress_line):
    if args.discovery_batch < 1 or args.hydration_batch < 1:
        raise ValueError("collection batch sizes must be positive")
    if (
        args.target_training_ready < 1
        or args.candidate_buffer < 1
        or args.min_training_ready_per_year < 0
    ):
        raise ValueError("collection targets and candidate buffer are invalid")
    store.set_collection_targets(
        args.target_training_ready,
        args.candidate_buffer,
        args.min_training_ready_per_year,
    )
    seeded = crawler.seed(args.usernames or [DEFAULT_SEED], args.seasons)
    totals = {
        "cycles": 0,
        "seeded": seeded,
        "training_ready_target": args.target_training_ready,
        "candidate_buffer": args.candidate_buffer,
        "min_training_ready_per_year": args.min_training_ready_per_year,
        "discovery_completed": 0,
        "discovery_failed": 0,
        "discovery_paused_cycles": 0,
        "hydration_completed": 0,
        "hydration_failed": 0,
        "hydration_enqueued": 0,
        "requests": 0,
        "failed_attempts": 0,
        "stopped_for_rate_limit": False,
    }
    while not crawler.stop_event.is_set():
        quality = quality_report(store)
        training_ready = quality["training_ready_leagues"]
        ready_by_year = quality["training_ready_by_year"]
        quota_years = tuple(
            season for season in args.seasons if season in TARGET_SEASONS
        )
        year_quotas_met = all(
            ready_by_year.get(str(season), 0) >= args.min_training_ready_per_year
            for season in quota_years
        )
        if training_ready >= args.target_training_ready and year_quotas_met:
            totals["stop_reason"] = "training_ready_target_reached"
            break
        status = store.status()
        hydration_queue = status["hydration_queue"]
        awaiting = max(
            0,
            status["candidate_leagues"]
            - sum(
                hydration_queue.get(state, 0)
                for state in ("pending", "in_progress", "done", "failed")
            ),
        )
        hydration_backlog = (
            awaiting
            + hydration_queue.get("pending", 0)
            + hydration_queue.get("in_progress", 0)
        )
        pause_discovery = hydration_backlog >= args.candidate_buffer
        totals["cycles"] += 1
        if progress:
            mode = "hydrate backlog" if pause_discovery else "discover + hydrate"
            print(
                f"collection cycle {totals['cycles']} · {mode} · "
                f"{training_ready:,}/{args.target_training_ready:,} training-ready",
                flush=True,
            )
        if pause_discovery:
            discovery = _empty_work_result()
            totals["discovery_paused_cycles"] += 1
        else:
            discovery = crawler.run_discovery(
                max_depth=args.max_depth,
                workers=args.discovery_workers,
                limit=args.discovery_batch,
                progress=progress,
            )
        totals["discovery_completed"] += discovery["completed"]
        totals["discovery_failed"] += discovery["failed"]
        totals["requests"] += discovery["requests"]
        totals["failed_attempts"] += discovery["failed_attempts"]
        if discovery["stopped_for_rate_limit"] or crawler.stop_event.is_set():
            totals["stopped_for_rate_limit"] = discovery["stopped_for_rate_limit"]
            if discovery.get("stop_reason"):
                totals["stop_reason"] = discovery["stop_reason"]
            break

        deficient_seasons = sorted(
            quota_years,
            key=lambda season: (ready_by_year.get(str(season), 0), season),
        )
        enqueued = store.enqueue_hydration_candidates(
            args.hydration_batch,
            preferred_seasons=deficient_seasons,
        )
        hydration = crawler.run_hydration(
            workers=args.hydration_workers,
            limit=args.hydration_batch,
            progress=progress,
        )
        totals["hydration_enqueued"] += enqueued
        totals["hydration_completed"] += hydration["completed"]
        totals["hydration_failed"] += hydration["failed"]
        totals["requests"] += hydration["requests"]
        totals["failed_attempts"] += hydration["failed_attempts"]
        if hydration["stopped_for_rate_limit"]:
            totals["stopped_for_rate_limit"] = True
            totals["stop_reason"] = hydration.get("stop_reason")
            break
        if (
            not pause_discovery
            and discovery["submitted"] == 0
            and hydration["submitted"] == 0
            and enqueued == 0
        ):
            totals["stop_reason"] = "queues_exhausted"
            break
    totals["status"] = store.status()
    return totals


def _empty_work_result():
    return {
        "submitted": 0,
        "completed": 0,
        "failed": 0,
        "elapsed_seconds": 0.0,
        "stopped_for_rate_limit": False,
        "requests": 0,
        "failed_attempts": 0,
    }


def _parser():
    parser = argparse.ArgumentParser(
        prog="python -m ffsim.historical_sleeper",
        description="Build a resumable historical Sleeper NFL dataset.",
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser(
        "collect",
        help="seed, discover, and hydrate continuously until complete or stopped",
    )
    collect.add_argument("usernames", nargs="*", help=f"default: {DEFAULT_SEED}")
    collect.add_argument("--seasons", nargs="+", type=int, default=list(TARGET_SEASONS))
    collect.add_argument("--max-depth", type=int, default=2)
    collect.add_argument("--discovery-workers", type=int, default=8)
    collect.add_argument("--hydration-workers", type=int, default=4)
    collect.add_argument(
        "--discovery-batch",
        type=int,
        default=500,
        help="discovery tasks per cycle (default: 500)",
    )
    collect.add_argument(
        "--hydration-batch",
        type=int,
        default=50,
        help="hydration candidates per cycle (default: 50)",
    )
    collect.add_argument(
        "--target-training-ready",
        type=int,
        default=DEFAULT_TRAINING_READY_TARGET,
        help="stop after this many training-ready leagues (default: 10000)",
    )
    collect.add_argument(
        "--candidate-buffer",
        type=int,
        default=DEFAULT_CANDIDATE_BUFFER,
        help="pause discovery above this hydration backlog (default: 500)",
    )
    collect.add_argument(
        "--min-training-ready-per-year",
        type=int,
        default=DEFAULT_MIN_TRAINING_READY_PER_YEAR,
        help="minimum ready leagues for each requested target year (default: 500)",
    )
    _network_arguments(collect)

    seed = subparsers.add_parser("seed", help="resolve users and queue all target seasons")
    seed.add_argument("usernames", nargs="*", help=f"default: {DEFAULT_SEED}")
    seed.add_argument("--seasons", nargs="+", type=int, default=list(TARGET_SEASONS))
    _network_arguments(seed)

    discover = subparsers.add_parser("discover", help="start or resume graph discovery")
    discover.add_argument("--max-depth", type=int, default=2)
    discover.add_argument("--workers", type=int, default=8)
    discover.add_argument("--limit", type=int)
    _network_arguments(discover)

    hydrate = subparsers.add_parser("hydrate", help="queue candidates and resume hydration")
    hydrate.add_argument("--enqueue", type=int, metavar="N", help="queue up to N qualifying leagues")
    hydrate.add_argument("--workers", type=int, default=4)
    hydrate.add_argument("--limit", type=int)
    _network_arguments(hydrate)

    players = subparsers.add_parser("players", help="refresh Sleeper's player dimension")
    _network_arguments(players)

    status = subparsers.add_parser("status", help="poll crawl and dataset counts")
    status.add_argument("--interval", type=float, default=5.0)
    status.add_argument("--once", action="store_true", help="print one JSON snapshot and exit")
    status.add_argument("--verbose", action="store_true", help="show detailed dataset and storage rows")
    subparsers.add_parser("retry-failures", help="return failed work to pending queues")
    subparsers.add_parser("validate", help="run integrity and dataset-quality checks")

    export = subparsers.add_parser("export", help="write analysis-ready Parquet tables")
    export.add_argument("--output", type=Path, default=DEFAULT_DATA_DIR / "exports")
    export.add_argument("--batch-size", type=int, default=50_000)

    rebuild = subparsers.add_parser("rebuild", help="rebuild normalized data without network calls")
    rebuild.add_argument("--output", type=Path, required=True)

    snapshot = subparsers.add_parser(
        "hdvn-snapshot",
        help="create an immutable native SQLite research snapshot and manifest",
    )
    snapshot.add_argument("--output", type=Path, required=True)
    acceptance = subparsers.add_parser(
        "hdvn-accept-snapshot",
        help="run the full raw trace and lock the accepted final snapshot",
    )
    acceptance.add_argument("--snapshot", type=Path, required=True)
    acceptance.add_argument("--output", type=Path, required=True)
    features = subparsers.add_parser(
        "hdvn-feature-manifest",
        help="freeze the point-in-time feature contract for an accepted snapshot",
    )
    features.add_argument("--snapshot-manifest", type=Path, required=True)
    features.add_argument("--acceptance", type=Path, required=True)
    features.add_argument("--output", type=Path, required=True)
    market = subparsers.add_parser(
        "hdvn-market",
        help="materialize all leakage-safe rolling population market boards",
    )
    market.add_argument("--snapshot", type=Path, required=True)
    market.add_argument("--acceptance", type=Path, required=True)
    market.add_argument("--features", type=Path, required=True)
    market.add_argument("--output", type=Path, required=True)
    market.add_argument("--min-support-drafts", type=int, default=25)
    tables = subparsers.add_parser(
        "hdvn-tables",
        help="materialize bounded team and sampled-prefix Parquet tables",
    )
    tables.add_argument("--snapshot", type=Path, required=True)
    tables.add_argument("--acceptance", type=Path, required=True)
    tables.add_argument("--features", type=Path, required=True)
    tables.add_argument("--market-database", type=Path, required=True)
    tables.add_argument("--market-manifest", type=Path, required=True)
    tables.add_argument("--output", type=Path, required=True)
    tables.add_argument("--seed", type=int, default=20260828)
    tables.add_argument("--epoch", type=int, default=0)
    tables.add_argument("--batch-size", type=int, default=10_000)
    labels_split = subparsers.add_parser(
        "hdvn-labels-split",
        help="freeze derived labels and whole-league temporal partitions",
    )
    labels_split.add_argument("--acceptance", type=Path, required=True)
    labels_split.add_argument("--features", type=Path, required=True)
    labels_split.add_argument("--tables-manifest", type=Path, required=True)
    labels_split.add_argument("--team-table", type=Path, required=True)
    labels_split.add_argument("--prefix-table", type=Path, required=True)
    labels_split.add_argument("--output", type=Path, required=True)
    labels_split.add_argument("--batch-size", type=int, default=10_000)
    baselines = subparsers.add_parser(
        "hdvn-baselines",
        help="fit required simple baselines on train and evaluate on 2024",
    )
    baselines.add_argument("--acceptance", type=Path, required=True)
    baselines.add_argument("--features", type=Path, required=True)
    baselines.add_argument("--tables-manifest", type=Path, required=True)
    baselines.add_argument("--market-manifest", type=Path, required=True)
    baselines.add_argument("--labels-manifest", type=Path, required=True)
    baselines.add_argument("--split-manifest", type=Path, required=True)
    baselines.add_argument("--output", type=Path, required=True)
    baselines.add_argument("--code-revision", required=True)
    baselines.add_argument("--seed", type=int, default=20260828)
    baselines.add_argument("--bootstrap-samples", type=int, default=200)
    neural = subparsers.add_parser(
        "hdvn-neural",
        help="fit the fixed completed-draft neural model and evaluate on 2024",
    )
    neural.add_argument("--acceptance", type=Path, required=True)
    neural.add_argument("--features", type=Path, required=True)
    neural.add_argument("--tables-manifest", type=Path, required=True)
    neural.add_argument("--market-manifest", type=Path, required=True)
    neural.add_argument("--labels-manifest", type=Path, required=True)
    neural.add_argument("--split-manifest", type=Path, required=True)
    neural.add_argument("--baseline-manifest", type=Path, required=True)
    neural.add_argument("--output", type=Path, required=True)
    neural.add_argument("--code-revision", required=True)
    neural.add_argument("--seed", type=int, default=20260828)
    neural.add_argument("--batch-size", type=int, default=128)
    neural.add_argument("--bootstrap-samples", type=int, default=200)
    residual = subparsers.add_parser(
        "hdvn-residual-alpha",
        help="search training-year folds for stable alpha beyond the historical market",
    )
    residual.add_argument("--acceptance", type=Path, required=True)
    residual.add_argument("--features", type=Path, required=True)
    residual.add_argument("--tables-manifest", type=Path, required=True)
    residual.add_argument("--market-manifest", type=Path, required=True)
    residual.add_argument("--labels-manifest", type=Path, required=True)
    residual.add_argument("--split-manifest", type=Path, required=True)
    residual.add_argument("--output", type=Path, required=True)
    residual.add_argument("--code-revision", required=True)
    residual.add_argument("--seed", type=int, default=20260828)
    residual.add_argument("--bootstrap-samples", type=int, default=200)
    opponent = subparsers.add_parser(
        "opponent-model",
        help="fit and validate the offline population choice and survival model",
    )
    opponent.add_argument("--acceptance", type=Path, required=True)
    opponent.add_argument("--features", type=Path, required=True)
    opponent.add_argument("--market-database", type=Path, required=True)
    opponent.add_argument("--market-manifest", type=Path, required=True)
    opponent.add_argument("--output", type=Path, required=True)
    opponent.add_argument("--code-revision", required=True)
    opponent.add_argument("--seed", type=int, default=20260828)
    opponent.add_argument("--bootstrap-samples", type=int, default=200)
    continuous = subparsers.add_parser(
        "continuous-survival",
        help="fit the fixed monotonic player-survival model on rolling train folds",
    )
    continuous.add_argument("--acceptance", type=Path, required=True)
    continuous.add_argument("--features", type=Path, required=True)
    continuous.add_argument("--market-database", type=Path, required=True)
    continuous.add_argument("--market-manifest", type=Path, required=True)
    continuous.add_argument("--output", type=Path, required=True)
    continuous.add_argument("--code-revision", required=True)
    continuous.add_argument("--seed", type=int, default=20260828)
    continuous.add_argument("--bootstrap-samples", type=int, default=200)
    empirical = subparsers.add_parser(
        "empirical-survival",
        help="materialize the supported exact empirical survival lookup",
    )
    empirical.add_argument("--acceptance", type=Path, required=True)
    empirical.add_argument("--features", type=Path, required=True)
    empirical.add_argument("--market-database", type=Path, required=True)
    empirical.add_argument("--market-manifest", type=Path, required=True)
    empirical.add_argument("--output", type=Path, required=True)
    empirical.add_argument("--code-revision", required=True)
    hierarchical = subparsers.add_parser(
        "hierarchical-survival",
        help="fit the offline hierarchical position-survival model",
    )
    projection_import = subparsers.add_parser(
        "historical-projection-import",
        help="import one approved point-in-time projection snapshot",
    )
    projection_import.add_argument("--csv", type=Path, required=True)
    projection_import.add_argument("--evidence", type=Path, required=True)
    projection_import.add_argument("--output", type=Path, required=True)
    hierarchical.add_argument("--acceptance", type=Path, required=True)
    hierarchical.add_argument("--features", type=Path, required=True)
    hierarchical.add_argument("--market-database", type=Path, required=True)
    hierarchical.add_argument("--market-manifest", type=Path, required=True)
    hierarchical.add_argument("--output", type=Path, required=True)
    hierarchical.add_argument("--code-revision", required=True)
    hierarchical.add_argument("--bootstrap-samples", type=int, default=200)
    rank20 = subparsers.add_parser(
        "rank20-survival",
        help="build the validated offline rank-20 survival artifact",
    )
    rank20.add_argument("--acceptance", type=Path, required=True)
    rank20.add_argument("--features", type=Path, required=True)
    rank20.add_argument("--market-database", type=Path, required=True)
    rank20.add_argument("--market-manifest", type=Path, required=True)
    rank20.add_argument("--evidence", type=Path, required=True)
    rank20.add_argument("--output", type=Path, required=True)
    rank20.add_argument("--code-revision", required=True)
    manager = subparsers.add_parser(
        "manager-choice",
        help="build the locked-benchmark-backed offline manager choice artifact",
    )
    manager.add_argument("--acceptance", type=Path, required=True)
    manager.add_argument("--features", type=Path, required=True)
    manager.add_argument("--source-database", type=Path, required=True)
    manager.add_argument("--market-database", type=Path, required=True)
    manager.add_argument("--market-manifest", type=Path, required=True)
    manager.add_argument("--benchmark", type=Path, required=True)
    manager.add_argument("--output", type=Path, required=True)
    manager.add_argument("--code-revision", required=True)
    roster_manager = subparsers.add_parser(
        "roster-manager-choice",
        help="build the corrected offline roster-aware manager artifact",
    )
    roster_manager.add_argument("--acceptance", type=Path, required=True)
    roster_manager.add_argument("--features", type=Path, required=True)
    roster_manager.add_argument("--source-database", type=Path, required=True)
    roster_manager.add_argument("--market-database", type=Path, required=True)
    roster_manager.add_argument("--market-manifest", type=Path, required=True)
    roster_manager.add_argument("--benchmark", type=Path, required=True)
    roster_manager.add_argument("--output", type=Path, required=True)
    roster_manager.add_argument("--code-revision", required=True)
    replay = subparsers.add_parser(
        "wait-reach-replay",
        help="replay offline next-turn survival and wait urgency on 2024",
    )
    replay.add_argument("--market-database", type=Path, required=True)
    replay.add_argument("--opponent-manifest", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)
    replay.add_argument("--code-revision", required=True)
    replay.add_argument("--seed", type=int, default=20260828)
    replay.add_argument("--bootstrap-samples", type=int, default=200)







    dry_run = subparsers.add_parser(
        "hdvn-dry-run",
        help="run the deterministic network-free HDVN contract fixture",
    )
    dry_run.add_argument("--output", type=Path, required=True)
    return parser


def _network_arguments(parser):
    parser.add_argument("--rate", type=int, default=750, help="global requests/minute (default: 750)")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--refresh", action="store_true", help="ignore retained endpoint responses")


def _poll_status(
    store,
    *,
    interval=5.0,
    once=False,
    stream=sys.stdout,
    sleep=time.sleep,
    max_updates=None,
    runtime_fn=crawler_runtime,
    storage_fn=sqlite_storage,
    verbose=False,
):
    if interval <= 0:
        raise ValueError("status interval must be positive")
    updates = 0
    while True:
        snapshot = {
            "status": store.status(),
            "quality": quality_report(store),
            "runtime": runtime_fn(),
            "storage": storage_fn(store.database_path),
            "updated_at": datetime.now(timezone.utc).astimezone().strftime(
                "%Y-%m-%d %H:%M:%S %Z"
            ),
        }
        if once:
            stream.write(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
        else:
            terminal = getattr(stream, "isatty", lambda: False)()
            if terminal:
                stream.write("\033[2J\033[H")
            width = shutil.get_terminal_size((100, 30)).columns if terminal else 100
            stream.write(
                render_dashboard(
                    snapshot,
                    interval,
                    width=width,
                    color=terminal,
                    verbose=verbose,
                )
                + "\n"
            )
        stream.flush()
        updates += 1
        if once or (max_updates is not None and updates >= max_updates):
            return
        sleep(interval)


def _print(value):
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
