import re
import unicodedata

import pandas as pd

from ffsim.paths import DATA_DIR


TEAM_ALIASES = {
    "ARZ": "ARI",
    "BLT": "BAL",
    "CLV": "CLE",
    "HST": "HOU",
    "JAC": "JAX",
    "LA": "LAR",
    "LVR": "LV",
    "OAK": "LV",
    "SD": "LAC",
    "SDG": "LAC",
    "SL": "LAR",
    "STL": "LAR",
}


def canonical_team(team):
    if pd.isna(team):
        return ""
    value = str(team or "").strip().upper()
    return TEAM_ALIASES.get(value, value)


def normalized_name(name):
    if pd.isna(name):
        return ""
    value = unicodedata.normalize("NFKD", str(name or ""))
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv|v|vi)$", "", value, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]", "", value.lower())


class PFFLoader:
    @staticmethod
    def get_and_clean_data():
        df = pd.read_csv(DATA_DIR / "projections" / "players.csv")
        required = {"playerName", "teamName", "position", "byeWeek", "games"}
        missing = sorted(required - set(df.columns))
        if missing:
            raise ValueError(f"PFF projection file is missing required columns: {', '.join(missing)}")

        df["normalized_name"] = df["playerName"].map(normalized_name)
        df["canonical_team"] = df["teamName"].map(canonical_team)
        df["position"] = df["position"].astype(str).str.upper().replace({"DST": "DEF"})
        df["projection_key"] = list(
            zip(df["normalized_name"], df["position"], df["canonical_team"])
        )
        duplicates = df[df.duplicated("projection_key", keep=False)]
        if not duplicates.empty:
            keys = sorted({"/".join(key) for key in duplicates["projection_key"]})
            raise ValueError("Duplicate PFF projections: " + ", ".join(keys))
        for id_column in ("sleeperId", "sleeper_id"):
            if id_column in df.columns:
                ids = df[id_column].dropna().astype(str)
                duplicates = sorted(ids[ids.duplicated(keep=False)].unique())
                if duplicates:
                    raise ValueError("Duplicate PFF Sleeper IDs: " + ", ".join(duplicates))
        return df
