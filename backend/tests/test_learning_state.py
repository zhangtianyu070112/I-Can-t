from __future__ import annotations

import unittest

from app.services.learning_state import (
    evaluation_overview,
    learning_overview,
    profile_overview,
    workshop_overview,
)


class LearningStateTest(unittest.TestCase):
    def test_dashboard_exposes_complete_learning_loop(self):
        result = learning_overview("demo")

        self.assertIn("learner", result)
        self.assertIn("focus", result)
        self.assertGreaterEqual(len(result.get("journey") or []), 7)
        self.assertGreaterEqual(len(result.get("metrics") or []), 4)
        self.assertTrue(result.get("next_actions"))
        self.assertTrue(all(item.get("route") for item in result["journey"]))

    def test_profile_and_evidence_contracts_are_stable(self):
        profile = profile_overview("demo")
        workshop = workshop_overview("demo")
        evaluation = evaluation_overview("demo")

        self.assertEqual(len(profile.get("dimensions") or []), 6)
        self.assertIn("weak_points", profile.get("focus") or {})
        self.assertIn("latest", workshop)
        self.assertIn("quality", workshop)
        self.assertIn("evidence", evaluation)
        self.assertIn("score", evaluation)


if __name__ == "__main__":
    unittest.main()
