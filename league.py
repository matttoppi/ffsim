class ScoringSettings:
    def __init__(self, scoring_data):
        for key, value in scoring_data.items():
            setattr(self, key, value)

class LeagueSettings:
    def __init__(self, settings_data):
        for key, value in settings_data.items():
            setattr(self, key, value)

class League:
    def __init__(self, league_data):
        self.name = league_data.get("name")
        self.total_rosters = league_data.get("total_rosters")
        self.roster_positions = league_data.get("roster_positions")
        self.loser_bracket_id = league_data.get("loser_bracket_id")
        self.group_id = league_data.get("group_id")
        self.bracket_id = league_data.get("bracket_id")
        self.previous_league_id = league_data.get("previous_league_id")
        self.league_id = league_data.get("league_id")
        self.draft_id = league_data.get("draft_id")
        self.last_read_id = league_data.get("last_read_id")
        self.last_pinned_message_id = league_data.get("last_pinned_message_id")
        self.last_message_time = league_data.get("last_message_time")
        self.last_message_text_map = league_data.get("last_message_text_map")
        self.last_message_attachment = league_data.get("last_message_attachment")
        self.last_author_is_bot = league_data.get("last_author_is_bot")
        self.last_author_id = league_data.get("last_author_id")
        self.last_author_display_name = league_data.get("last_author_display_name")
        self.last_author_avatar = league_data.get("last_author_avatar")
        self.scoring_settings = ScoringSettings(league_data.get("scoring_settings", {}))
        self.settings = LeagueSettings(league_data.get("settings", {}))
        self.sport = league_data.get("sport")
        self.season_type = league_data.get("season_type")
        self.season = league_data.get("season")
        self.shard = league_data.get("shard")
        self.last_message_id = league_data.get("last_message_id")
        self.company_id = league_data.get("company_id")
        self.avatar = league_data.get("avatar")
        self.metadata = league_data.get("metadata", {})
        self.status = league_data.get("status")

# # Example usage:
# import json

# league_json_str = 'your JSON string here'
# league_data = json.loads(league_json_str)
# league = League(league_data)

# # You can now access any attribute of the league object, for example:
# print(league.name)
# print(league.season)
# print(league.scoring_settings.pass_td)
# print(league.settings.reserve_slots)
