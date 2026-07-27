from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GroupConfig:
    id: str
    sigle: str
    official_sigle: str
    nom: str
    ordre: int
    logo_text: str
    logo_color: str = "#8D949A"
    optional: bool = False


@dataclass(frozen=True)
class ProjectConfig:
    groups: list[GroupConfig]
    vote_colors: dict[str, str]
    layout_colors: dict[str, str]

    @property
    def groups_by_id(self) -> dict[str, GroupConfig]:
        return {group.id: group for group in self.groups}


def load_config(path: str | Path = "groupes_politiques.json") -> ProjectConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    groups = [GroupConfig(**group) for group in data["groups"]]
    return ProjectConfig(
        groups=sorted(groups, key=lambda group: group.ordre),
        vote_colors=data["vote_colors"],
        layout_colors=data["layout_colors"],
    )
