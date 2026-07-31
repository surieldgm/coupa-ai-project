"""The shipped skill catalog — discovery contract and decree-rule anchors.

These tests pin the Stage 2 deliverable to the spec: three skills,
discoverable by description, each owning its decree rules (CONTEXT.md:
Monthly Contract Value, Delivered PO, Renewal Window).
"""

from __future__ import annotations

import unittest
from pathlib import Path

from agent.session import _SKILLS_DIR
from agent.skills_lib import SkillLibrary

EXPECTED = {"account-health", "follow-ups", "contract-reconciliation"}


class SkillCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.library = SkillLibrary(_SKILLS_DIR)

    def test_catalog_ships_the_three_skills(self) -> None:
        names = {s.name for s in self.library.menu()}
        self.assertEqual(names, EXPECTED)

    def test_every_skill_has_a_useful_description(self) -> None:
        for skill in self.library.menu():
            self.assertTrue(skill.description, skill.name)
            self.assertLess(len(skill.description), 250, skill.name)

    def test_frontmatter_names_match_directory_names(self) -> None:
        for directory in sorted(Path(_SKILLS_DIR).glob("*/")):
            body = self.library.load(directory.name)
            self.assertIn(f"name: {directory.name}", body)

    def test_decree_rules_live_in_their_owning_skills(self) -> None:
        reconciliation = self.library.load("contract-reconciliation")
        self.assertIn("annual_value / 12", reconciliation)

        follow_ups = self.library.load("follow-ups")
        self.assertIn("90", follow_ups)  # Renewal Window
        self.assertIn("delivery_date", follow_ups)  # Delivered PO rule

        health = self.library.load("account-health")
        self.assertIn("get_overdue_aging", health)  # no silent arithmetic


if __name__ == "__main__":
    unittest.main()
