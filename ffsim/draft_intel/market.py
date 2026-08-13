import csv
import hashlib
import io
import json
import math
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ffsim.draft_intel.storage import SCHEMA, _atomic_write
from ffsim.paths import CACHE_DIR, PROJECT_ROOT


CSV_COLUMNS = {"sleeper_id", "adp", "rank", "std_dev", "tier"}
FANTASYPROS_URL = "https://api.fantasypros.com/public/v2/json/nfl/{season}/consensus-rankings"
FANTASYPROS_REFRESH_INTERVAL = timedelta(hours=12)
FANTASYPROS_CONTEXTS = (
    ("1qb", "STD", "ALL"),
    ("1qb", "HALF", "ALL"),
    ("1qb", "PPR", "ALL"),
    ("superflex", "HALF", "OP"),
)
FANTASYPROS_SOURCE_IDS = {
    "79": "espn",
    "80": "cbs",
    "236": "yahoo",
    "291": "nfl",
    "439": "rtsports",
    "624": "fantrax",
    "4350": "sleeper",
    "7661": "ffpc",
}
TEAM_ALIASES = {"JAC": "JAX"}


def import_market_csv(
    csv_path,
    *,
    source,
    season,
    scoring,
    observed_at,
    league_format="1qb",
    team_count=None,
    storage_dir=None,
    retrieved_at=None,
):
    storage_dir = Path(storage_dir or CACHE_DIR / "draft_intel")
    database_path = storage_dir / "history.sqlite3"
    if not database_path.exists():
        raise FileNotFoundError("Draft intelligence store is missing; run draft-audit --persist first")

    observed_at = _timestamp(observed_at)
    retrieved_at = _timestamp(retrieved_at or datetime.now(timezone.utc))
    source = source.strip()
    scoring = scoring.strip().upper()
    league_format = league_format.strip().lower()
    if not source or not scoring or not league_format:
        raise ValueError("source, scoring, and league_format are required")
    if season <= 0 or team_count is not None and team_count <= 0:
        raise ValueError("season and team_count must be positive")

    payload = Path(csv_path).read_bytes()
    raw_hash = hashlib.sha256(payload).hexdigest()
    snapshot_id = hashlib.sha256(
        json.dumps(
            {
                "raw_snapshot_hash": raw_hash,
                "source": source,
                "season": season,
                "scoring": scoring,
                "league_format": league_format,
                "team_count": team_count,
                "observed_at": observed_at,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    raw_relative = Path("raw") / f"market-{raw_hash}.csv"
    raw_path = storage_dir / raw_relative

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        _ensure_market_schema(connection)
        observations = _parse_csv(payload, _sleeper_ids(connection))
        existing = connection.execute(
            "SELECT observation_count FROM market_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if existing:
            if existing[0] != len(observations):
                raise ValueError(f"Stored market snapshot {snapshot_id} conflicts with this import")
        else:
            if not raw_path.exists():
                _atomic_write(raw_path, payload)
            with connection:
                connection.execute(
                    """
                    INSERT INTO market_snapshots (
                        snapshot_id, source, source_type, season, scoring, league_format,
                        team_count,
                        observed_at, retrieved_at, raw_snapshot_hash, raw_snapshot_path,
                        observation_count
                    ) VALUES (?, ?, 'manual_csv', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        source,
                        season,
                        scoring,
                        league_format,
                        team_count,
                        observed_at,
                        retrieved_at,
                        raw_hash,
                        raw_relative.as_posix(),
                        len(observations),
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO market_observations (
                        snapshot_id, canonical_player_id, source_player_id,
                        adp, rank, std_dev, tier
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ((snapshot_id, *observation) for observation in observations),
                )
    finally:
        connection.close()

    return {
        "snapshot_id": snapshot_id,
        "database_path": str(database_path),
        "raw_snapshot_path": str(raw_path),
        "raw_snapshot_hash": raw_hash,
        "observation_count": len(observations),
    }


def load_market_snapshot_at(
    *,
    source,
    season,
    scoring,
    at,
    league_format="1qb",
    team_count=None,
    max_age=None,
    storage_dir=None,
):
    database_path = Path(storage_dir or CACHE_DIR / "draft_intel") / "history.sqlite3"
    if not database_path.exists():
        return None

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        _ensure_market_schema(connection)
        at = _timestamp(at)
        scoring = scoring.strip().upper()
        league_format = league_format.strip().lower()
        snapshot = connection.execute(
            """
            SELECT * FROM market_snapshots
            WHERE source = ? AND season = ? AND UPPER(scoring) = ?
              AND league_format = ? AND team_count IS ?
              AND observed_at <= ? AND retrieved_at <= ?
            ORDER BY observed_at DESC, retrieved_at DESC
            LIMIT 1
            """,
            (source, season, scoring, league_format, team_count, at, at),
        ).fetchone()
        if snapshot is None:
            return None
        if max_age is not None:
            age = datetime.fromisoformat(at) - datetime.fromisoformat(snapshot["observed_at"])
            if age > max_age:
                return None
        observations = connection.execute(
            """
            SELECT canonical_player_id, source_player_id, adp, rank, std_dev, tier
            FROM market_observations
            WHERE snapshot_id = ?
            ORDER BY COALESCE(rank, adp), canonical_player_id
            """,
            (snapshot["snapshot_id"],),
        ).fetchall()
        result = dict(snapshot)
        result["observations"] = [dict(observation) for observation in observations]
        return result
    finally:
        connection.close()


def refresh_fantasypros_adp(
    *,
    season=2026,
    storage_dir=None,
    sleeper_players_path=None,
    contexts=FANTASYPROS_CONTEXTS,
    now=None,
    fetch_payload=None,
    api_key=None,
):
    """Fetch each due ADP context once and persist every platform in its response."""
    storage_dir = Path(storage_dir or CACHE_DIR / "draft_intel")
    database_path = storage_dir / "history.sqlite3"
    if not database_path.exists():
        raise FileNotFoundError("Draft intelligence store is missing; run draft-audit --persist first")

    now = _datetime(now or datetime.now(timezone.utc))
    contexts = tuple(_market_context(context) for context in contexts)
    status = fantasypros_market_status(
        season=season,
        storage_dir=storage_dir,
        contexts=contexts,
        now=now,
    )
    due = tuple(
        context
        for context, context_status in zip(contexts, status["contexts"], strict=True)
        if not context_status["fresh"]
    )
    if not due:
        return {**status, "fetched_contexts": [], "skipped_contexts": list(contexts)}

    api_key = api_key or _fantasypros_api_key()
    fetch_payload = fetch_payload or _fetch_fantasypros_payload
    if sleeper_players_path is None:
        from ffsim.loaders.players import PlayerLoader

        sleeper_players = PlayerLoader().refresh_sleeper_players()
    else:
        sleeper_players_path = Path(sleeper_players_path)
        try:
            sleeper_players = json.loads(sleeper_players_path.read_text())
        except (json.JSONDecodeError, OSError) as error:
            raise ValueError(f"Invalid Sleeper player identity cache {sleeper_players_path}") from error
    if not isinstance(sleeper_players, dict):
        raise ValueError("Sleeper player identity cache must contain an object")

    fetched = []
    for league_format, scoring, position in due:
        payload = fetch_payload(
            season=season,
            scoring=scoring,
            position=position,
            api_key=api_key,
        )
        result = _store_fantasypros_payload(
            payload,
            season=season,
            scoring=scoring,
            league_format=league_format,
            position=position,
            sleeper_players=sleeper_players,
            storage_dir=storage_dir,
            retrieved_at=now,
        )
        fetched.append(result)

    status = fantasypros_market_status(
        season=season,
        storage_dir=storage_dir,
        contexts=contexts,
        now=now,
    )
    return {
        **status,
        "fetched_contexts": fetched,
        "skipped_contexts": [context for context in contexts if context not in due],
    }


def fantasypros_market_status(
    *,
    season=2026,
    storage_dir=None,
    contexts=FANTASYPROS_CONTEXTS,
    now=None,
):
    storage_dir = Path(storage_dir or CACHE_DIR / "draft_intel")
    database_path = storage_dir / "history.sqlite3"
    now = _datetime(now or datetime.now(timezone.utc))
    contexts = tuple(_market_context(context) for context in contexts)
    if not database_path.exists():
        return {
            "season": season,
            "refresh_interval_hours": 12,
            "fresh": False,
            "next_refresh_at": None,
            "contexts": [
                _missing_context_status(context) for context in contexts
            ],
        }

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        _ensure_market_schema(connection)
        results = []
        next_refreshes = []
        for league_format, scoring, position in contexts:
            latest = connection.execute(
                """
                SELECT retrieved_at, observed_at, raw_snapshot_hash
                FROM market_snapshots
                WHERE source = 'fantasypros:consensus'
                  AND season = ? AND scoring = ? AND league_format = ?
                ORDER BY retrieved_at DESC
                LIMIT 1
                """,
                (season, scoring, league_format),
            ).fetchone()
            if latest is None:
                results.append(_missing_context_status((league_format, scoring, position)))
                continue
            retrieved_at = _datetime(latest["retrieved_at"])
            next_refresh = retrieved_at + FANTASYPROS_REFRESH_INTERVAL
            results.append({
                "league_format": league_format,
                "scoring": scoring,
                "position": position,
                "fresh": now < next_refresh,
                "retrieved_at": retrieved_at.isoformat(),
                "observed_at": latest["observed_at"],
                "next_refresh_at": next_refresh.isoformat(),
                "raw_snapshot_hash": latest["raw_snapshot_hash"],
            })
            next_refreshes.append(next_refresh)
    finally:
        connection.close()

    return {
        "season": season,
        "refresh_interval_hours": 12,
        "fresh": all(context["fresh"] for context in results),
        "next_refresh_at": min(next_refreshes).isoformat() if next_refreshes else None,
        "contexts": results,
    }


def _store_fantasypros_payload(
    payload,
    *,
    season,
    scoring,
    league_format,
    position,
    sleeper_players,
    storage_dir,
    retrieved_at,
):
    if not isinstance(payload, bytes):
        raise TypeError("FantasyPros fetch must return raw bytes")
    try:
        response = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("FantasyPros returned invalid JSON") from error
    raw_hash = hashlib.sha256(payload).hexdigest()
    raw_relative = Path("raw") / f"fantasypros-{raw_hash}.json"
    raw_path = storage_dir / raw_relative
    if not raw_path.exists():
        _atomic_write(raw_path, payload)
    players = _validate_fantasypros_response(
        response,
        season=season,
        scoring=scoring,
        position=position,
    )

    database_path = storage_dir / "history.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        _ensure_market_schema(connection)
        mapped, unmatched = _fantasypros_identity_map(
            players,
            sleeper_players,
            _sleeper_ids(connection),
        )
        observations = _fantasypros_observations(players, mapped)
        observed_at = datetime.fromtimestamp(
            int(response["last_updated_ts"]), timezone.utc
        ).isoformat()
        retrieved_at = retrieved_at.isoformat()
        with connection:
            _store_fantasypros_ids(connection, mapped, retrieved_at)
            snapshots = []
            for source, source_observations in observations.items():
                snapshot_id = hashlib.sha256(json.dumps(
                    {
                        "raw_snapshot_hash": raw_hash,
                        "source": source,
                        "season": season,
                        "scoring": scoring,
                        "league_format": league_format,
                        "observed_at": observed_at,
                        "retrieved_at": retrieved_at,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()).hexdigest()
                connection.execute(
                    """
                    INSERT OR IGNORE INTO market_snapshots (
                        snapshot_id, source, source_type, season, scoring,
                        league_format, team_count, observed_at, retrieved_at,
                        raw_snapshot_hash, raw_snapshot_path, observation_count
                    ) VALUES (?, ?, 'fantasypros_api', ?, ?, ?, NULL, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        source,
                        season,
                        scoring,
                        league_format,
                        observed_at,
                        retrieved_at,
                        raw_hash,
                        raw_relative.as_posix(),
                        len(source_observations),
                    ),
                )
                connection.executemany(
                    """
                    INSERT OR IGNORE INTO market_observations (
                        snapshot_id, canonical_player_id, source_player_id,
                        adp, rank, std_dev, tier
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ((snapshot_id, *observation) for observation in source_observations),
                )
                snapshots.append({
                    "source": source,
                    "snapshot_id": snapshot_id,
                    "observation_count": len(source_observations),
                })
    finally:
        connection.close()

    return {
        "league_format": league_format,
        "scoring": scoring,
        "position": position,
        "raw_snapshot_path": str(raw_path),
        "raw_snapshot_hash": raw_hash,
        "response_player_count": len(players),
        "mapped_player_count": len(mapped),
        "unmatched_players": unmatched,
        "snapshots": snapshots,
    }


def _validate_fantasypros_response(response, *, season, scoring, position):
    if not isinstance(response, dict):
        raise ValueError("FantasyPros response must be an object")
    players = response.get("players")
    if (
        response.get("tier") != "premium"
        or response.get("limit") is not None
        or not isinstance(players, list)
        or response.get("count") != len(players)
    ):
        raise ValueError("FantasyPros did not return a complete Premium response")
    if str(response.get("year")) != str(season):
        raise ValueError("FantasyPros response season does not match the request")
    if str(response.get("scoring")).upper() != scoring:
        raise ValueError("FantasyPros response scoring does not match the request")
    if str(response.get("position_id")).upper() != position:
        raise ValueError("FantasyPros response position does not match the request")
    if not isinstance(response.get("last_updated_ts"), int):
        raise ValueError("FantasyPros response is missing last_updated_ts")
    return players


def _fantasypros_identity_map(players, sleeper_players, canonical_sleeper_ids):
    by_sportsdata = {}
    ambiguous_sportsdata = set()
    defenses = {}
    for source_id, player in sleeper_players.items():
        sleeper_id = str(player.get("player_id") or source_id)
        canonical_player_id = canonical_sleeper_ids.get(sleeper_id)
        if canonical_player_id is None:
            continue
        sportsdata_id = player.get("sportradar_id")
        if sportsdata_id:
            sportsdata_id = str(sportsdata_id)
            existing = by_sportsdata.get(sportsdata_id)
            if existing is not None and existing != canonical_player_id:
                ambiguous_sportsdata.add(sportsdata_id)
                by_sportsdata.pop(sportsdata_id)
            elif sportsdata_id not in ambiguous_sportsdata:
                by_sportsdata[sportsdata_id] = canonical_player_id
        if str(player.get("position")).upper() == "DEF" and player.get("team"):
            defenses[str(player["team"]).upper()] = canonical_player_id

    mapped = {}
    unmatched = []
    for player in players:
        fantasypros_id = str(player.get("player_id") or "")
        canonical_player_id = None
        if str(player.get("player_position_id")).upper() == "DST":
            team = TEAM_ALIASES.get(
                str(player.get("player_team_id")).upper(),
                str(player.get("player_team_id")).upper(),
            )
            canonical_player_id = defenses.get(team)
        elif player.get("sportsdata_id"):
            canonical_player_id = by_sportsdata.get(str(player["sportsdata_id"]))
        if not fantasypros_id or canonical_player_id is None:
            unmatched.append({
                "fantasypros_id": fantasypros_id or None,
                "name": player.get("player_name"),
                "position": player.get("player_position_id"),
            })
            continue
        existing = mapped.setdefault(fantasypros_id, canonical_player_id)
        if existing != canonical_player_id:
            raise ValueError(f"Conflicting FantasyPros player ID {fantasypros_id}")
    return mapped, unmatched


def _fantasypros_observations(players, mapped):
    observations = {"fantasypros:consensus": []}
    for player in players:
        fantasypros_id = str(player.get("player_id") or "")
        canonical_player_id = mapped.get(fantasypros_id)
        if canonical_player_id is None:
            continue
        adp = _positive_float(player.get("rank_ave"))
        rank = _positive_integer(player.get("rank_ecr"))
        if adp is not None or rank is not None:
            observations["fantasypros:consensus"].append((
                canonical_player_id,
                fantasypros_id,
                adp,
                rank,
                _nonnegative_float(player.get("rank_std")),
                _positive_integer(player.get("tier")),
            ))
        experts = player.get("experts") or {}
        if not isinstance(experts, dict):
            raise ValueError(f"Invalid FantasyPros source ranks for player {fantasypros_id}")
        for source_id, source_adp in experts.items():
            source_name = FANTASYPROS_SOURCE_IDS.get(str(source_id), f"source-{source_id}")
            source = f"fantasypros:{source_name}"
            adp = _positive_float(source_adp)
            if adp is not None:
                observations.setdefault(source, []).append((
                    canonical_player_id,
                    fantasypros_id,
                    adp,
                    None,
                    None,
                    None,
                ))
    return {source: rows for source, rows in observations.items() if rows}


def _store_fantasypros_ids(connection, mapped, observed_at):
    for fantasypros_id, canonical_player_id in mapped.items():
        existing = connection.execute(
            "SELECT canonical_player_id FROM player_external_ids WHERE source = 'fantasypros' AND external_id = ?",
            (fantasypros_id,),
        ).fetchone()
        if existing and existing[0] != canonical_player_id:
            raise ValueError(f"FantasyPros ID {fantasypros_id} conflicts with stored identity")
        existing = connection.execute(
            "SELECT external_id FROM player_external_ids WHERE source = 'fantasypros' AND canonical_player_id = ?",
            (canonical_player_id,),
        ).fetchone()
        if existing and existing[0] != fantasypros_id:
            raise ValueError(f"Canonical player {canonical_player_id} has conflicting FantasyPros IDs")
    connection.executemany(
        """
        INSERT INTO player_external_ids (
            canonical_player_id, source, external_id,
            first_seen_at, last_seen_at, confidence
        ) VALUES (?, 'fantasypros', ?, ?, ?, 1.0)
        ON CONFLICT(source, external_id) DO UPDATE SET
            last_seen_at = excluded.last_seen_at,
            confidence = excluded.confidence
        """,
        (
            (canonical_player_id, fantasypros_id, observed_at, observed_at)
            for fantasypros_id, canonical_player_id in mapped.items()
        ),
    )


def _fetch_fantasypros_payload(*, season, scoring, position, api_key):
    query = urlencode({
        "position": position,
        "type": "ADP",
        "scoring": scoring,
        "week": 0,
        "experts": "show",
    })
    request = Request(
        f"{FANTASYPROS_URL.format(season=season)}?{query}",
        headers={
            "x-api-key": api_key,
            "Cache-Control": "no-cache",
            "User-Agent": "ffsim/1.0",
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read()


def _fantasypros_api_key(env_path=None):
    key = os.environ.get("FANTASYPROS_API_KEY")
    env_path = Path(env_path or PROJECT_ROOT / ".env")
    if not key and env_path.exists():
        for raw_line in env_path.read_text().splitlines():
            name, separator, value = raw_line.partition("=")
            if separator and name.strip() == "FANTASYPROS_API_KEY":
                key = value.strip().strip("'\"")
                break
    if not key:
        raise ValueError("FANTASYPROS_API_KEY is missing from the environment or .env")
    if any(character.isspace() for character in key):
        raise ValueError("FANTASYPROS_API_KEY contains whitespace")
    return key


def _ensure_market_schema(connection):
    connection.executescript(SCHEMA)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(market_snapshots)")}
    if "league_format" not in columns:
        connection.execute(
            "ALTER TABLE market_snapshots ADD COLUMN league_format TEXT NOT NULL DEFAULT '1qb'"
        )
        connection.commit()


def _market_context(context):
    if len(context) != 3:
        raise ValueError("Market context must contain league_format, scoring, and position")
    league_format, scoring, position = (str(value).strip() for value in context)
    league_format = league_format.lower()
    scoring = scoring.upper()
    position = position.upper()
    if not league_format or scoring not in {"STD", "HALF", "PPR"} or position not in {"ALL", "OP"}:
        raise ValueError(f"Unsupported FantasyPros market context {context}")
    if (league_format == "superflex") != (position == "OP"):
        raise ValueError(f"League format and position disagree for context {context}")
    return league_format, scoring, position


def _missing_context_status(context):
    league_format, scoring, position = context
    return {
        "league_format": league_format,
        "scoring": scoring,
        "position": position,
        "fresh": False,
        "retrieved_at": None,
        "observed_at": None,
        "next_refresh_at": None,
        "raw_snapshot_hash": None,
    }


def _positive_float(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def _positive_integer(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _nonnegative_float(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _datetime(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Market timestamps must include a timezone")
    return value.astimezone(timezone.utc)


def _sleeper_ids(connection):
    return dict(connection.execute(
        """
        SELECT external_id, canonical_player_id
        FROM player_external_ids
        WHERE source = 'sleeper'
        """
    ))


def _parse_csv(payload, sleeper_ids):
    try:
        reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig"), newline=""))
    except UnicodeDecodeError as error:
        raise ValueError("Market CSV must be UTF-8") from error
    fieldnames = reader.fieldnames or ()
    columns = set(fieldnames)
    if len(columns) != len(fieldnames):
        raise ValueError("Market CSV has duplicate columns")
    if "sleeper_id" not in columns or not {"adp", "rank"} & columns:
        raise ValueError("Market CSV requires sleeper_id and at least one of adp or rank")
    unknown_columns = columns - CSV_COLUMNS
    if unknown_columns:
        raise ValueError(f"Unknown market CSV columns: {', '.join(sorted(unknown_columns))}")

    observations = []
    seen = set()
    for line_number, row in enumerate(reader, start=2):
        if None in row:
            raise ValueError(f"Too many values on line {line_number}")
        sleeper_id = (row["sleeper_id"] or "").strip()
        if not sleeper_id:
            raise ValueError(f"Missing sleeper_id on line {line_number}")
        if sleeper_id in seen:
            raise ValueError(f"Duplicate sleeper_id {sleeper_id} on line {line_number}")
        canonical_player_id = sleeper_ids.get(sleeper_id)
        if canonical_player_id is None:
            raise ValueError(f"Unknown sleeper_id {sleeper_id} on line {line_number}")

        adp = _number(row, "adp", line_number, float)
        rank = _number(row, "rank", line_number, int)
        std_dev = _number(row, "std_dev", line_number, float)
        tier = _number(row, "tier", line_number, int)
        if adp is None and rank is None:
            raise ValueError(f"Line {line_number} requires adp or rank")
        if any(value is not None and value <= 0 for value in (adp, rank, tier)):
            raise ValueError(f"adp, rank, and tier must be positive on line {line_number}")
        if std_dev is not None and std_dev < 0:
            raise ValueError(f"std_dev must be non-negative on line {line_number}")
        observations.append((canonical_player_id, sleeper_id, adp, rank, std_dev, tier))
        seen.add(sleeper_id)
    if not observations:
        raise ValueError("Market CSV has no observations")
    return observations


def _number(row, name, line_number, value_type):
    value = (row.get(name) or "").strip()
    if not value:
        return None
    try:
        converted = value_type(value)
    except ValueError as error:
        raise ValueError(f"Invalid {name} on line {line_number}: {value}") from error
    if isinstance(converted, float) and not math.isfinite(converted):
        raise ValueError(f"Invalid {name} on line {line_number}: {value}")
    if value_type is int and str(converted) != value:
        raise ValueError(f"Invalid {name} on line {line_number}: {value}")
    return converted


def _timestamp(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Market snapshot timestamps must include a timezone")
    return value.astimezone(timezone.utc).isoformat()
