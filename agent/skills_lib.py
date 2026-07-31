"""Skill discovery and loading (Anthropic Agent Skills shape, adapted).

Progressive disclosure: menu() exposes only name + description (level 1,
for the system prompt); load() returns SKILL.md bodies and bundled
resources on demand (levels 2-3), confined to the skills root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str


class SkillNotFoundError(Exception):
    pass


class SkillLibrary:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def menu(self) -> list[SkillInfo]:
        if not self._root.is_dir():
            return []
        infos: list[SkillInfo] = []
        for manifest in sorted(self._root.glob("*/SKILL.md")):
            front = _frontmatter(manifest.read_text(encoding="utf-8"))
            infos.append(
                SkillInfo(
                    name=front.get("name", manifest.parent.name),
                    description=front.get("description", ""),
                )
            )
        return infos

    def load(self, path: str) -> str:
        """Read a skill file by path relative to the skills root.

        `load("account-health")` returns that skill's SKILL.md; deeper
        paths return bundled resources. Paths resolving outside the
        skills root are refused with the same error as a missing skill.
        """
        candidate = (self._root / path).resolve()
        if not candidate.is_relative_to(self._root):
            raise SkillNotFoundError(f"unknown skill: {path}")
        if candidate.is_dir():
            candidate = candidate / "SKILL.md"
        if not candidate.is_file():
            raise SkillNotFoundError(f"unknown skill: {path}")
        return candidate.read_text(encoding="utf-8")


def _frontmatter(text: str) -> dict[str, str]:
    """Minimal 'key: value' frontmatter parser (PyYAML is not in the pinned deps)."""
    if not text.startswith("---"):
        return {}
    fields: dict[str, str] = {}
    for line in text.split("\n")[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields
