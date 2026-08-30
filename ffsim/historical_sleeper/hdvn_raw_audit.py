import gzip
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .hdvn_snapshot import RAW_HASH_TABLES, canonical_json, sha256_file


AUDIT_VERSION = "hdvn-raw-trace-v1"
_SAMPLE_LIMIT = 100


def audit_raw_sources(snapshot_database, data_dir, *, chunk_size=1024 * 1024):
    """Stream-verify every registered raw object and every canonical raw reference."""
    snapshot_database = Path(snapshot_database).expanduser().resolve()
    data_dir = Path(data_dir).expanduser().resolve()
    if chunk_size < 1:
        raise ValueError("raw audit chunk size must be positive")

    report = {
        "audit_version": AUDIT_VERSION,
        "snapshot_database": str(snapshot_database),
        "source_data_directory": str(data_dir),
        "canonical_references": 0,
        "distinct_canonical_objects": 0,
        "registered_objects": 0,
        "verified_objects": 0,
        "missing_database_references": 0,
        "missing_files": 0,
        "corrupt_gzip_files": 0,
        "wrong_byte_counts": 0,
        "wrong_hashes": 0,
        "unsafe_paths": 0,
        "unreferenced_database_objects": 0,
        "unreferenced_files": 0,
        "duplicate_content_hash_rows": 0,
        "duplicate_relative_path_rows": 0,
        "samples": {},
    }
    connection = sqlite3.connect(
        f"file:{snapshot_database.as_posix()}?mode=ro&immutable=1",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("CREATE TEMP TABLE canonical_hashes(content_hash TEXT PRIMARY KEY) WITHOUT ROWID")
        for table in RAW_HASH_TABLES:
            report["canonical_references"] += connection.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE raw_hash IS NOT NULL'
            ).fetchone()[0]
            connection.execute(
                f'INSERT OR IGNORE INTO canonical_hashes SELECT raw_hash FROM "{table}" WHERE raw_hash IS NOT NULL'
            )
        report["distinct_canonical_objects"] = connection.execute(
            "SELECT COUNT(*) FROM canonical_hashes"
        ).fetchone()[0]
        missing = connection.execute(
            """
            SELECT canonical_hashes.content_hash
            FROM canonical_hashes
            LEFT JOIN raw_objects USING (content_hash)
            WHERE raw_objects.content_hash IS NULL
            ORDER BY canonical_hashes.content_hash
            """
        )
        for row in missing:
            _record(report, "missing_database_references", row[0])

        report["registered_objects"] = connection.execute(
            "SELECT COUNT(*) FROM raw_objects"
        ).fetchone()[0]
        report["unreferenced_database_objects"] = connection.execute(
            """
            SELECT COUNT(*) FROM raw_objects
            LEFT JOIN canonical_hashes USING (content_hash)
            WHERE canonical_hashes.content_hash IS NULL
            """
        ).fetchone()[0]
        report["duplicate_content_hash_rows"] = _duplicate_count(connection, "content_hash")
        report["duplicate_relative_path_rows"] = _duplicate_count(connection, "relative_path")

        rows = connection.execute(
            "SELECT content_hash, relative_path, byte_count FROM raw_objects ORDER BY content_hash"
        )
        for row in rows:
            path = data_dir / row["relative_path"]
            try:
                resolved = path.resolve()
                resolved.relative_to(data_dir)
            except (OSError, ValueError):
                _record(report, "unsafe_paths", row["relative_path"])
                continue
            if not resolved.is_file():
                _record(report, "missing_files", row["relative_path"])
                continue
            try:
                byte_count, content_hash = _hash_gzip(resolved, chunk_size)
            except (gzip.BadGzipFile, EOFError, OSError) as error:
                _record(report, "corrupt_gzip_files", f"{row['relative_path']}: {error}")
                continue
            valid = True
            if byte_count != row["byte_count"]:
                _record(
                    report,
                    "wrong_byte_counts",
                    f"{row['relative_path']}: expected {row['byte_count']}, got {byte_count}",
                )
                valid = False
            if content_hash != row["content_hash"]:
                _record(
                    report,
                    "wrong_hashes",
                    f"{row['relative_path']}: expected {row['content_hash']}, got {content_hash}",
                )
                valid = False
            if valid:
                report["verified_objects"] += 1

        for path in data_dir.joinpath("raw").glob("*/*.json.gz"):
            relative_path = str(path.relative_to(data_dir))
            if connection.execute(
                "SELECT 1 FROM raw_objects WHERE relative_path = ?", (relative_path,)
            ).fetchone() is None:
                _record(report, "unreferenced_files", relative_path)
    finally:
        connection.close()

    failure_fields = (
        "missing_database_references",
        "missing_files",
        "corrupt_gzip_files",
        "wrong_byte_counts",
        "wrong_hashes",
        "unsafe_paths",
        "duplicate_content_hash_rows",
        "duplicate_relative_path_rows",
    )
    report["passed"] = all(report[field] == 0 for field in failure_fields)
    return report


def create_snapshot_acceptance(snapshot_database, data_dir, output, *, command):
    snapshot_database = Path(snapshot_database).expanduser().resolve()
    data_dir = Path(data_dir).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    manifest_path = snapshot_database.with_suffix(snapshot_database.suffix + ".manifest.json")
    if output.exists():
        raise FileExistsError(f"immutable acceptance sidecar already exists: {output}")
    manifest = json.loads(manifest_path.read_text())
    raw_trace = audit_raw_sources(snapshot_database, data_dir)
    source_database = Path(manifest["source_database"]).resolve()
    source_identity = _file_identity(source_database)
    snapshot_identity = _file_identity(snapshot_database)

    with closing(sqlite3.connect(f"file:{snapshot_database.as_posix()}?mode=ro&immutable=1", uri=True)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    expected_years = {2021: 928, 2022: 1539, 2023: 2151, 2024: 2570, 2025: 2825}
    actual_years = {}
    for row in manifest["strict_training_ready"]["by_context"]:
        season = int(row["season"])
        actual_years[season] = actual_years.get(season, 0) + int(row["league_seasons"])
    wal_files = [
        str(path)
        for path in (
            snapshot_database.with_name(snapshot_database.name + "-wal"),
            snapshot_database.with_name(snapshot_database.name + "-shm"),
        )
        if path.exists()
    ]
    passed = all((
        raw_trace["passed"],
        integrity == "ok",
        not foreign_key_errors,
        not wal_files,
        source_identity["canonical_path"] != snapshot_identity["canonical_path"],
        (source_identity["device"], source_identity["inode"])
        != (snapshot_identity["device"], snapshot_identity["inode"]),
        str(journal_mode).lower() != "wal",
        manifest["sha256"] == sha256_file(snapshot_database),
        manifest["strict_training_ready"]["total"] == 10013,
        actual_years == expected_years,
    ))
    acceptance = {
        "acceptance_version": 1,
        "audit_code_version": AUDIT_VERSION,
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": command,
        "source_data_directory": str(data_dir),
        "source_identity": source_identity,
        "snapshot_identity": snapshot_identity,
        "snapshot_sha256": sha256_file(snapshot_database),
        "snapshot_manifest": str(manifest_path),
        "snapshot_manifest_sha256": sha256_file(manifest_path),
        "integrity_check": integrity,
        "foreign_key_errors": len(foreign_key_errors),
        "journal_mode_read_only": journal_mode,
        "wal_dependencies": wal_files,
        "strict_training_ready": {
            "total": manifest["strict_training_ready"]["total"],
            "by_year": {str(year): actual_years.get(year, 0) for year in sorted(expected_years)},
        },
        "raw_trace": raw_trace,
        "passed": passed,
    }
    if not passed:
        raise ValueError("final snapshot acceptance failed")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(acceptance) + "\n")
    return acceptance


def make_snapshot_files_read_only(snapshot_database, acceptance_path):
    snapshot_database = Path(snapshot_database).resolve()
    paths = (
        snapshot_database,
        snapshot_database.with_suffix(snapshot_database.suffix + ".manifest.json"),
        Path(acceptance_path).resolve(),
    )
    for path in paths:
        path.chmod(0o444)
    return paths


def _hash_gzip(path, chunk_size):
    digest = hashlib.sha256()
    byte_count = 0
    with gzip.open(path, "rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
            byte_count += len(chunk)
    return byte_count, digest.hexdigest()


def _duplicate_count(connection, column):
    return connection.execute(
        f"SELECT COALESCE(SUM(count - 1), 0) FROM ("
        f"SELECT COUNT(*) AS count FROM raw_objects GROUP BY {column} HAVING COUNT(*) > 1)"
    ).fetchone()[0]


def _record(report, field, detail):
    report[field] += 1
    report["samples"].setdefault(field, [])
    if len(report["samples"][field]) < _SAMPLE_LIMIT:
        report["samples"][field].append(str(detail))


def _file_identity(path):
    stat = path.stat()
    return {
        "canonical_path": str(path.resolve()),
        "device": stat.st_dev,
        "inode": stat.st_ino,
        "bytes": stat.st_size,
    }
