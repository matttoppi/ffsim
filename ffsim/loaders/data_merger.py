import pandas as pd

from ffsim.loaders.pff import canonical_team, normalized_name


class DataMerger:
    last_projection_report = {}

    @staticmethod
    def merge_data(fantasy_calc_df, sleeper_df, pff_df, injury_df=None):
        del injury_df  # The unverified injury snapshot is intentionally inactive.
        sleeper = sleeper_df.copy()
        fantasy_calc = fantasy_calc_df.copy()
        projections = pff_df.copy()

        sleeper["player_id"] = sleeper["player_id"].astype(str)
        if not fantasy_calc.empty:
            fantasy_calc["sleeper_id"] = fantasy_calc["sleeper_id"].astype(str)
            fantasy_columns = [
                column for column in ("sleeper_id", "value_1qb", "redraft_value")
                if column in fantasy_calc.columns
            ]
            sleeper = sleeper.merge(
                fantasy_calc[fantasy_columns].drop_duplicates("sleeper_id"),
                left_on="player_id",
                right_on="sleeper_id",
                how="left",
            )

        sleeper["normalized_name"] = sleeper["full_name"].map(normalized_name)
        sleeper["canonical_team"] = sleeper["team"].map(canonical_team)
        sleeper["position"] = sleeper["position"].astype(str).str.upper().replace({"DST": "DEF"})
        sleeper["projection_key"] = sleeper.apply(DataMerger._projection_key, axis=1)
        projections["projection_key"] = projections.apply(DataMerger._projection_key, axis=1)

        id_column = next(
            (column for column in ("sleeperId", "sleeper_id") if column in projections.columns),
            None,
        )
        valid_stable_ids = set()
        position_mismatches = set()
        if id_column:
            projections["_stable_id"] = projections[id_column].fillna("").astype(str)
            projection_ids = projections[projections["_stable_id"] != ""]
            for stable_id, rows in projection_ids.groupby("_stable_id"):
                sleeper_rows = sleeper[sleeper["player_id"] == stable_id]
                if len(rows) == len(sleeper_rows) == 1:
                    if rows.iloc[0]["position"] == sleeper_rows.iloc[0]["position"]:
                        valid_stable_ids.add(stable_id)
                    else:
                        position_mismatches.add(stable_id)
        sleeper["join_key"] = sleeper.apply(
            lambda row: ("id", row["player_id"])
            if row["player_id"] in valid_stable_ids
            else (("position_mismatch", row["player_id"]) if row["player_id"] in position_mismatches else ("identity", *row["projection_key"])),
            axis=1,
        )
        projections["join_key"] = projections.apply(
            lambda row: ("id", row["_stable_id"])
            if row.get("_stable_id", "") in valid_stable_ids
            else ("identity", *row["projection_key"]),
            axis=1,
        )

        sleeper_counts = sleeper["join_key"].value_counts()
        projection_counts = projections["join_key"].value_counts()
        unique_keys = {
            key for key, count in sleeper_counts.items()
            if count == 1 and projection_counts.get(key, 0) == 1
        }
        projections = projections.copy()
        projections["_projection_index"] = projections.index
        matched = sleeper.merge(
            projections.drop(columns=["normalized_name", "canonical_team", "projection_key"], errors="ignore"),
            on="join_key",
            how="left",
            suffixes=("", "_pff"),
        )
        matched.loc[~matched["join_key"].isin(unique_keys), "_projection_index"] = pd.NA
        matched["projection_match_status"] = matched.apply(
            lambda row: DataMerger._match_status(row, sleeper_counts, projection_counts), axis=1
        )

        report_rows = [
            {
                "sleeper_id": str(row.player_id),
                "name": DataMerger._text(row.full_name),
                "position": DataMerger._text(row.position),
                "team": DataMerger._text(row.canonical_team),
                "status": row.projection_match_status,
            }
            for row in matched.itertuples()
            if row.projection_match_status != "matched"
        ]
        used = {int(value) for value in matched["_projection_index"].dropna()}
        DataMerger.last_projection_report = {
            "matched": int((matched["projection_match_status"] == "matched").sum()),
            "unmatched_or_ambiguous": sorted(
                report_rows,
                key=lambda row: (row["status"], row["name"], row["position"], row["team"], row["sleeper_id"]),
            ),
            "unused_projections": sorted(
                {
                    f"{row.playerName}/{row.position}/{row.canonical_team}"
                    for row in pff_df.itertuples()
                    if row.Index not in used
                }
            ),
        }
        return DataMerger.clean_merged_data(matched)

    @staticmethod
    def _projection_key(row):
        position = str(row.get("position") or "").upper().replace("DST", "DEF")
        team = canonical_team(row.get("canonical_team") or row.get("team") or row.get("teamName"))
        if position == "DEF":
            return (team, position, team)
        return (normalized_name(row.get("normalized_name") or row.get("full_name") or row.get("playerName")), position, team)

    @staticmethod
    def _match_status(row, sleeper_counts, projection_counts):
        key = row["join_key"]
        if key[0] == "position_mismatch":
            return "position_mismatch"
        if sleeper_counts.get(key, 0) > 1 or projection_counts.get(key, 0) > 1:
            return "ambiguous"
        return "matched" if projection_counts.get(key, 0) == 1 else "unmatched"

    @staticmethod
    def _text(value):
        return "" if pd.isna(value) else str(value)

    @staticmethod
    def clean_merged_data(df):
        df = df.copy()
        for column in df.columns:
            if pd.api.types.is_object_dtype(df[column]):
                df[column] = df[column].fillna("")
            elif column not in {"byeWeek", "_projection_index"}:
                df[column] = df[column].fillna(0)
        df["byeWeek"] = df["byeWeek"].where(df["byeWeek"].notna(), None)
        df["sleeper_id"] = df["player_id"]
        return df
