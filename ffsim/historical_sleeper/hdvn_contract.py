import hashlib
import json
from pathlib import Path

from .hdvn_snapshot import canonical_json, sha256_file


FEATURE_VERSION = "hdvn-features-v1"
LABEL_VERSION = "hdvn-labels-v1"
MARKET_VERSION = "hdvn-rolling-market-v1"
PREFIX_VERSION = "hdvn-prefix-v1"
MODEL_INPUT_MODE = "market_and_construction_only"
REQUIRED_FIELDS = (
    "name",
    "type",
    "source",
    "observation_time_rule",
    "transformation",
    "null_meaning",
    "leakage_classification",
    "completed_draft_available",
    "prefix_available",
    "model_eligible",
)


def _feature(
    group,
    name,
    type_,
    source,
    observation,
    transformation="identity",
    null="not observed or not supported; never imputed",
    classification="draft_time_source",
    completed=True,
    prefix=True,
    eligible=True,
):
    return {
        "group": group,
        "name": name,
        "type": type_,
        "source": source,
        "observation_time_rule": observation,
        "transformation": transformation,
        "null_meaning": null,
        "leakage_classification": classification,
        "completed_draft_available": completed,
        "prefix_available": prefix,
        "model_eligible": eligible,
    }


AT_DRAFT = "source fact existed no later than target draft start"
BEFORE_DRAFT = "source artifact timestamp is strictly before target draft start"
OBSERVED_PICK = "derived only from picks with pick_no at or before the prefix"
PRIOR_DRAFTS = "derived only from drafts completed strictly before target draft start"
LABEL_ONLY = "observed after the season; label only"
PROHIBITED = "prohibited historical draft-time input"

FEATURES = (
    _feature("league_context", "season", "integer", "league_seasons.season", AT_DRAFT),
    _feature("league_context", "team_count", "integer", "league_seasons.total_rosters", AT_DRAFT),
    _feature("league_context", "scoring_format", "categorical", "league_seasons.scoring_format", AT_DRAFT),
    _feature("league_context", "scoring_settings_hash", "sha256", "league_seasons.scoring_settings_json", AT_DRAFT, "canonical JSON SHA-256"),
    _feature("league_context", "roster_positions", "json[string]", "league_seasons.roster_positions_json", AT_DRAFT, "canonical JSON"),
    _feature("league_context", "draft_type", "categorical", "drafts.draft_type", AT_DRAFT),
    _feature("league_context", "round_count", "integer", "drafts.rounds", AT_DRAFT),
    _feature("draft_geometry", "draft_slot", "integer", "draft_picks.draft_slot and effective_roster_id", AT_DRAFT, "first owned slot"),
    _feature("draft_geometry", "draft_geometry", "categorical", "drafts settings and type", AT_DRAFT, "snake, linear, or unsupported"),
    _feature("draft_geometry", "overall_pick", "integer", "draft_picks.pick_no", OBSERVED_PICK),
    _feature("draft_geometry", "round", "integer", "draft_picks.round", OBSERVED_PICK),
    _feature("draft_geometry", "remaining_picks", "integer", "draft ownership geometry", AT_DRAFT, "owned picks after prefix"),
    _feature("draft_geometry", "next_user_pick", "integer", "draft ownership geometry", AT_DRAFT, "next owned overall pick", "no later owned pick"),
    _feature("pick_sequence", "position_sequence", "json[string]", "draft_picks.position", OBSERVED_PICK, "ordered canonical position list"),
    _feature("pick_sequence", "pick_player_ids", "json[string]", "draft_picks.player_id", OBSERVED_PICK, "audit identity only", classification="audit_only", eligible=False),
    _feature("roster_construction", "first_qb_round", "integer", "position_sequence", OBSERVED_PICK, "minimum round by position", "position not selected"),
    _feature("roster_construction", "first_rb_round", "integer", "position_sequence", OBSERVED_PICK, "minimum round by position", "position not selected"),
    _feature("roster_construction", "first_wr_round", "integer", "position_sequence", OBSERVED_PICK, "minimum round by position", "position not selected"),
    _feature("roster_construction", "first_te_round", "integer", "position_sequence", OBSERVED_PICK, "minimum round by position", "position not selected"),
    _feature("roster_construction", "position_counts_r3", "json[integer]", "position_sequence", OBSERVED_PICK, "counts through round 3"),
    _feature("roster_construction", "position_counts_r5", "json[integer]", "position_sequence", OBSERVED_PICK, "counts through round 5"),
    _feature("roster_construction", "position_counts_r8", "json[integer]", "position_sequence", OBSERVED_PICK, "counts through round 8"),
    _feature("roster_construction", "position_counts", "json[integer]", "position_sequence", OBSERVED_PICK, "counts through observed prefix"),
    _feature("starter_flex_coverage", "starter_slots", "integer", "roster_positions", AT_DRAFT, "non-bench slot count"),
    _feature("starter_flex_coverage", "starter_covered", "integer", "position_sequence and roster_positions", OBSERVED_PICK, "maximum legal slot matching"),
    _feature("starter_flex_coverage", "flex_slots", "integer", "roster_positions", AT_DRAFT, "flex-family slot count"),
    _feature("starter_flex_coverage", "flex_covered", "integer", "position_sequence and roster_positions", OBSERVED_PICK, "legal matched flex-family slots"),
    _feature("roster_construction", "bench_structure", "json[integer]", "unmatched drafted positions", OBSERVED_PICK, "position counts after maximum starter matching"),
    _feature("market_relative_value", "market_rank_by_pick", "json[number|null]", "rolling prior-draft market board", PRIOR_DRAFTS, "lookup by preserved player_id", "unsupported player or context"),
    _feature("market_relative_value", "market_adp_by_pick", "json[number|null]", "rolling prior-draft market board", PRIOR_DRAFTS, "mean historical overall pick", "unsupported player or context"),
    _feature("market_relative_value", "market_value_by_pick", "json[number|null]", "rolling prior-draft market board", PRIOR_DRAFTS, "ADP minus actual pick", "unsupported player or context"),
    _feature("market_relative_value", "cumulative_market_value", "number", "market_value_by_pick", PRIOR_DRAFTS, "sum of supported pick values"),
    _feature("market_relative_value", "market_support_drafts", "integer", "rolling prior-draft market board", PRIOR_DRAFTS),
    _feature("market_relative_value", "market_cutoff_ms", "integer", "rolling prior-draft market board", PRIOR_DRAFTS),
    _feature("remaining_board_context", "available_by_position", "json[integer]", "rolling board minus observed picks", OBSERVED_PICK),
    _feature("remaining_board_context", "available_by_tier", "json[integer]", "rolling board minus observed picks", OBSERVED_PICK, "rank bands of team_count players"),
    _feature("remaining_board_context", "best_rank_by_position", "json[number]", "rolling board minus observed picks", OBSERVED_PICK),
    _feature("remaining_board_context", "tier_boundary_distance", "json[number]", "rolling board minus observed picks", OBSERVED_PICK, "available count to end of current rank band"),
    _feature("remaining_board_context", "recent_position_runs", "json[integer]", "draft_picks.position", OBSERVED_PICK, "counts over prior team_count observed picks"),
    _feature("prefix_state", "prefix_pick_no", "integer", "draft_picks.pick_no", OBSERVED_PICK, completed=False),
    _feature("prefix_state", "prefix_round", "integer", "draft_picks.round", OBSERVED_PICK, completed=False),
    _feature("prefix_state", "observed_picks", "json[object]", "draft_picks", OBSERVED_PICK, "picks through prefix only", completed=False),
    _feature("prefix_state", "current_roster", "json[string]", "observed team picks", OBSERVED_PICK, "positions only", completed=False),
    _feature("prefix_state", "prefix_bucket", "categorical", "prefix round and total rounds", OBSERVED_PICK, "early, middle, or late", completed=False),
    _feature("prefix_state", "prefix_weight", "number", "prefix sampler", OBSERVED_PICK, "one sampled prefix has team weight 1", classification="audit_only", completed=False, eligible=False),
    _feature("label", "points_for_percentile", "number", "team_seasons.matchup_points_for", LABEL_ONLY, "within-league midrank percentile", classification="label", eligible=False),
    _feature("label", "regular_season_win_percentage", "number", "team_seasons h2h wins/losses/ties", LABEL_ONLY, "(wins + 0.5 ties) / games", classification="label", eligible=False),
    _feature("label", "made_playoffs", "boolean", "team_seasons.made_playoffs", LABEL_ONLY, classification="label", eligible=False),
    _feature("label", "champion", "boolean", "team_seasons.champion", LABEL_ONLY, classification="label", eligible=False),
    _feature("identity_provenance", "team_table_version", "string", "HDVN table generator", AT_DRAFT, classification="audit_only", prefix=False, eligible=False),
    _feature("identity_provenance", "prefix_version", "string", "HDVN prefix generator", AT_DRAFT, classification="audit_only", completed=False, eligible=False),
    _feature("identity_provenance", "league_season_id", "string", "league_seasons league_id and season", AT_DRAFT, classification="audit_only", completed=False, eligible=False),
    _feature("identity_provenance", "league_id", "string", "league_seasons.league_id", AT_DRAFT, classification="audit_only", eligible=False),
    _feature("identity_provenance", "draft_id", "string", "drafts.draft_id", AT_DRAFT, classification="audit_only", eligible=False),
    _feature("identity_provenance", "roster_id", "integer", "rosters.roster_id", AT_DRAFT, classification="audit_only", eligible=False),
    _feature("identity_provenance", "owner_id", "string", "rosters.owner_id", AT_DRAFT, classification="audit_only", eligible=False),
    _feature("identity_provenance", "market_provenance_hash", "sha256", "rolling market board provenance", PRIOR_DRAFTS, classification="audit_only", eligible=False),
    _feature("identity_provenance", "source_manifest_hash", "sha256", "accepted source manifest", AT_DRAFT, classification="audit_only", eligible=False),
    _feature("identity_provenance", "feature_manifest_hash", "sha256", "final feature manifest", AT_DRAFT, classification="audit_only", eligible=False),
    _feature("identity_provenance", "feature_version", "string", "feature registry", AT_DRAFT, classification="audit_only", eligible=False),
    _feature("identity_provenance", "label_version", "string", "label contract", LABEL_ONLY, classification="audit_only", eligible=False),
    _feature("identity_provenance", "training_eligible", "boolean", "training acceptance rules", LABEL_ONLY, classification="audit_only", eligible=False),
    _feature("identity_provenance", "exclusion_reasons", "json[string]", "training acceptance rules", LABEL_ONLY, "sorted reason codes", classification="audit_only", eligible=False),
    _feature("identity_provenance", "prefix_sampling_method", "string", "prefix sampler", OBSERVED_PICK, classification="audit_only", completed=False, eligible=False),
    _feature("identity_provenance", "sampled_bucket", "string", "prefix sampler", OBSERVED_PICK, classification="audit_only", completed=False, eligible=False),
    _feature("prohibited", "current_projections_for_historical_draft", "prohibited", "current projection cache", PROHIBITED, classification="prohibited", completed=False, prefix=False, eligible=False),
    _feature("prohibited", "post_draft_projections", "prohibited", "projection snapshot after draft", PROHIBITED, classification="prohibited", completed=False, prefix=False, eligible=False),
    _feature("prohibited", "post_season_player_outcomes", "prohibited", "historical player actuals", PROHIBITED, classification="prohibited", completed=False, prefix=False, eligible=False),
    _feature("prohibited", "future_drafts_in_market_board", "prohibited", "target or later draft picks", PROHIBITED, classification="prohibited", completed=False, prefix=False, eligible=False),
    _feature("prohibited", "later_injuries_or_news", "prohibited", "injury/news observation after draft", PROHIBITED, classification="prohibited", completed=False, prefix=False, eligible=False),
    _feature("prohibited", "outcome_labels_as_features", "prohibited", "HDVN labels", PROHIBITED, classification="prohibited", completed=False, prefix=False, eligible=False),
)
FEATURE_BY_NAME = {feature["name"]: feature for feature in FEATURES}

TEAM_COLUMN_FEATURES = {
    "team_table_version": "team_table_version",
    "league_id": "league_id",
    "season": "season",
    "draft_id": "draft_id",
    "roster_id": "roster_id",
    "owner_id": "owner_id",
    "draft_slot": "draft_slot",
    "draft_geometry": "draft_geometry",
    "draft_type": "draft_type",
    "round_count": "round_count",
    "team_count": "team_count",
    "scoring_format": "scoring_format",
    "scoring_settings_hash": "scoring_settings_hash",
    "roster_positions_json": "roster_positions",
    "position_sequence_json": "position_sequence",
    "pick_player_ids_json": "pick_player_ids",
    "pick_numbers_json": "overall_pick",
    "pick_rounds_json": "round",
    "first_qb_round": "first_qb_round",
    "first_rb_round": "first_rb_round",
    "first_wr_round": "first_wr_round",
    "first_te_round": "first_te_round",
    "position_counts_r3_json": "position_counts_r3",
    "position_counts_r5_json": "position_counts_r5",
    "position_counts_r8_json": "position_counts_r8",
    "position_counts_json": "position_counts",
    "starter_slots": "starter_slots",
    "starter_covered": "starter_covered",
    "flex_slots": "flex_slots",
    "flex_covered": "flex_covered",
    "bench_structure_json": "bench_structure",
    "market_rank_by_pick_json": "market_rank_by_pick",
    "market_adp_by_pick_json": "market_adp_by_pick",
    "market_value_by_pick_json": "market_value_by_pick",
    "cumulative_market_value": "cumulative_market_value",
    "market_support_drafts": "market_support_drafts",
    "market_cutoff_ms": "market_cutoff_ms",
    "market_provenance_hash": "market_provenance_hash",
    "source_manifest_hash": "source_manifest_hash",
    "feature_manifest_hash": "feature_manifest_hash",
    "feature_version": "feature_version",
    "label_version": "label_version",
    "points_for_percentile": "points_for_percentile",
    "regular_season_win_percentage": "regular_season_win_percentage",
    "made_playoffs": "made_playoffs",
    "champion": "champion",
    "training_eligible": "training_eligible",
    "exclusion_reasons_json": "exclusion_reasons",
}

PREFIX_COLUMN_FEATURES = {
    "prefix_version": "prefix_version",
    "league_season_id": "league_season_id",
    "league_id": "league_id",
    "season": "season",
    "draft_id": "draft_id",
    "roster_id": "roster_id",
    "owner_id": "owner_id",
    "team_count": "team_count",
    "scoring_format": "scoring_format",
    "draft_slot": "draft_slot",
    "prefix_round": "prefix_round",
    "prefix_pick_no": "prefix_pick_no",
    "prefix_bucket": "prefix_bucket",
    "observed_picks_json": "observed_picks",
    "current_roster_json": "current_roster",
    "position_counts_json": "position_counts",
    "remaining_picks": "remaining_picks",
    "next_user_pick": "next_user_pick",
    "available_by_position_json": "available_by_position",
    "available_by_tier_json": "available_by_tier",
    "best_rank_by_position_json": "best_rank_by_position",
    "tier_boundary_distance_json": "tier_boundary_distance",
    "recent_position_runs_json": "recent_position_runs",
    "market_support_drafts": "market_support_drafts",
    "market_cutoff_ms": "market_cutoff_ms",
    "points_for_percentile": "points_for_percentile",
    "regular_season_win_percentage": "regular_season_win_percentage",
    "made_playoffs": "made_playoffs",
    "champion": "champion",
    "prefix_weight": "prefix_weight",
    "prefix_sampling_method": "prefix_sampling_method",
    "sampled_bucket": "sampled_bucket",
    "feature_version": "feature_version",
    "source_manifest_hash": "source_manifest_hash",
    "label_version": "label_version",
    "training_eligible": "training_eligible",
}

MATERIALIZED_COLUMN_FEATURES = {
    "team": TEAM_COLUMN_FEATURES,
    "prefix": PREFIX_COLUMN_FEATURES,
}


def feature_manifest():
    validate_registry()
    materialized = {
        table: dict(sorted(columns.items()))
        for table, columns in MATERIALIZED_COLUMN_FEATURES.items()
    }
    model_eligible = {
        table: sorted(
            column
            for column, feature_name in columns.items()
            if FEATURE_BY_NAME[feature_name]["model_eligible"]
        )
        for table, columns in MATERIALIZED_COLUMN_FEATURES.items()
    }
    body = {
        "feature_version": FEATURE_VERSION,
        "model_input_mode": MODEL_INPUT_MODE,
        "features": list(FEATURES),
        "materialized_columns": materialized,
        "model_eligible_columns": model_eligible,
    }
    return {**body, "sha256": hashlib.sha256(canonical_json(body).encode()).hexdigest()}


def validate_registry():
    names = set()
    for feature in FEATURES:
        missing = set(REQUIRED_FIELDS) - feature.keys()
        if missing:
            raise ValueError(f"feature {feature.get('name')} missing {sorted(missing)}")
        if feature["name"] in names:
            raise ValueError(f"duplicate feature {feature['name']}")
        names.add(feature["name"])
        if feature["leakage_classification"] in {"label", "prohibited"} and feature["model_eligible"]:
            raise ValueError(f"leaking feature marked eligible: {feature['name']}")
    return True

def validate_materialized_columns(table, columns, used_eligible_columns=None):
    if table not in MATERIALIZED_COLUMN_FEATURES:
        raise ValueError(f"unknown materialized table: {table}")
    contract = MATERIALIZED_COLUMN_FEATURES[table]
    columns = set(columns)
    unknown = columns - contract.keys()
    missing = contract.keys() - columns
    if unknown:
        raise ValueError(f"unregistered materialized columns: {sorted(unknown)}")
    if missing:
        raise ValueError(f"registered materialized columns missing: {sorted(missing)}")
    eligible = {
        column
        for column, feature_name in contract.items()
        if FEATURE_BY_NAME[feature_name]["model_eligible"]
    }
    used = eligible if used_eligible_columns is None else set(used_eligible_columns)
    unused = eligible - used
    ineligible = used - eligible
    if unused:
        raise ValueError(f"unused eligible columns: {sorted(unused)}")
    if ineligible:
        raise ValueError(f"ineligible model columns: {sorted(ineligible)}")
    return True


def write_final_feature_manifest(snapshot_manifest_path, acceptance_path, output):
    snapshot_manifest_path = Path(snapshot_manifest_path).resolve()
    acceptance_path = Path(acceptance_path).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"immutable feature manifest already exists: {output}")
    source = json.loads(snapshot_manifest_path.read_text())
    acceptance = json.loads(acceptance_path.read_text())
    if not acceptance.get("passed"):
        raise ValueError("source snapshot acceptance did not pass")
    if source["sha256"] != acceptance["snapshot_sha256"]:
        raise ValueError("source snapshot hash mismatch")
    manifest = feature_manifest()
    for table, contract in MATERIALIZED_COLUMN_FEATURES.items():
        validate_materialized_columns(
            table,
            contract,
            manifest["model_eligible_columns"][table],
        )
    body = {
        **{key: value for key, value in manifest.items() if key != "sha256"},
        "source_snapshot_sha256": source["sha256"],
        "source_manifest_sha256": sha256_file(snapshot_manifest_path),
        "source_acceptance_sha256": sha256_file(acceptance_path),
        "finalized_at": acceptance["completed_at"],
    }
    final = {**body, "sha256": hashlib.sha256(canonical_json(body).encode()).hexdigest()}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(final) + "\n")
    output.chmod(0o444)
    return final


def validate_feature_observations(observations, target_draft_ms):
    """Reject unknown, prohibited, or post-draft observations at the feature boundary."""
    for observation in observations:
        name = observation.get("name")
        if name not in FEATURE_BY_NAME:
            raise ValueError(f"unregistered feature: {name}")
        feature = FEATURE_BY_NAME[name]
        if not feature["model_eligible"]:
            raise ValueError(f"feature is not a model input: {name}")
        observed_at = observation.get("observed_at_ms")
        if observed_at is None:
            raise ValueError(f"feature observation time missing: {name}")
        if int(observed_at) > int(target_draft_ms):
            raise ValueError(f"post-draft feature observation: {name}")
    return True
