import unittest

from ffsim.draft_intel.compatibility import league_compatibility


def source(*, draft_type="snake", roster_positions=None, settings=None, scoring=None):
    league = {
        "total_rosters": 12,
        "settings": {
            "type": 0,
            "best_ball": 0,
            "playoff_teams": 6,
            "playoff_round_type": 0,
            "playoff_seed_type": 0,
            "divisions": 0,
            **(settings or {}),
        },
        "roster_positions": roster_positions
        or ["QB", "RB", "WR", "TE", "SUPER_FLEX", "BN"],
        "scoring_settings": scoring or {"rec": 0.5, "bonus_rec_te": 0.5},
    }
    draft = {
        "type": draft_type,
        "settings": {"teams": 12, "rounds": 18},
        "metadata": {"scoring_type": "custom_redraft"},
    }
    return league, draft


class CompatibilityTest(unittest.TestCase):
    def test_supported_roster_and_draft_formats_remain_supported(self):
        for draft_type, flex in (
            ("snake", None),
            ("linear", "SUPER_FLEX"),
            ("snake", "REC_FLEX"),
            ("snake", "WRRB_FLEX"),
        ):
            with self.subTest(draft_type=draft_type, flex=flex):
                positions = ["QB", "RB", "WR", "TE", "BN"]
                if flex:
                    positions.insert(-1, flex)
                league, draft = source(
                    draft_type=draft_type,
                    roster_positions=positions,
                )

                report = league_compatibility(league, draft)

                self.assertEqual(report["status"], "supported")
                self.assertTrue(report["redraft_eligible"])
                self.assertTrue(all(
                    capability["status"] == "supported"
                    for capability in report["capabilities"].values()
                ))

    def test_attachment_survives_auction_best_ball_and_unsupported_rules(self):
        league, draft = source(
            draft_type="auction",
            roster_positions=["QB", "IDP_FLEX", "BN"],
            settings={"best_ball": 1, "playoff_round_type": 1},
            scoring={"rec": 1, "bonus_pass_yd_300": 2},
        )

        report = league_compatibility(league, draft)

        self.assertEqual(report["status"], "attachment_only")
        self.assertEqual(report["capabilities"]["attachment"]["status"], "supported")
        self.assertEqual(report["capabilities"]["draft_replay"]["status"], "supported")
        self.assertEqual(report["capabilities"]["draft_rollout"]["reasons"], [
            {"code": "auction_future_owners_unknown"}
        ])
        self.assertEqual(
            {reason["code"] for reason in report["capabilities"]["season_evaluation"]["reasons"]},
            {
                "best_ball",
                "unsupported_roster_positions",
                "unsupported_scoring_keys",
                "unsupported_playoff_round_type",
            },
        )

    def test_keeper_and_inconsistent_team_counts_fail_only_downstream(self):
        league, draft = source()
        draft["settings"]["teams"] = 10

        report = league_compatibility(league, draft, [{"is_keeper": True}])

        self.assertEqual(report["capabilities"]["attachment"]["status"], "supported")
        self.assertFalse(report["redraft_eligible"])
        self.assertEqual(report["redraft_ineligibility_reasons"], ["keeper_picks"])
        self.assertIn(
            "team_count_mismatch",
            {reason["code"] for reason in report["capabilities"]["draft_replay"]["reasons"]},
        )


if __name__ == "__main__":
    unittest.main()
