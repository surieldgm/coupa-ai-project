"""SkillLibrary — filesystem seam on a temp dir."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.skills_lib import SkillLibrary, SkillNotFoundError

SKILL_MD = """---
name: account-health
description: Diagnose the account's AR health.
---

Step 1: fetch invoices.
"""


class SkillLibraryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        skill = self.root / "account-health"
        (skill / "resources").mkdir(parents=True)
        (skill / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
        (skill / "resources" / "rubric.md").write_text("the rubric", encoding="utf-8")
        self.library = SkillLibrary(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_menu_reads_frontmatter_only(self) -> None:
        menu = self.library.menu()
        self.assertEqual(len(menu), 1)
        self.assertEqual(menu[0].name, "account-health")
        self.assertEqual(menu[0].description, "Diagnose the account's AR health.")

    def test_load_by_skill_name_returns_body(self) -> None:
        body = self.library.load("account-health")
        self.assertIn("Step 1: fetch invoices.", body)

    def test_load_bundled_resource(self) -> None:
        self.assertEqual(self.library.load("account-health/resources/rubric.md"), "the rubric")

    def test_traversal_is_refused_like_a_missing_skill(self) -> None:
        outside = self.root.parent / "secret.txt"
        outside.write_text("nope", encoding="utf-8")
        try:
            with self.assertRaises(SkillNotFoundError):
                self.library.load("../secret.txt")
        finally:
            outside.unlink()

    def test_unknown_skill_raises(self) -> None:
        with self.assertRaises(SkillNotFoundError):
            self.library.load("no-such-skill")


if __name__ == "__main__":
    unittest.main()
