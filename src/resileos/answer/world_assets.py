"""
World-building asset registry + hub learn.

Stores world objects as Titanos facts plus an on-disk asset index
(image, video, audio, game_codex, scene, prop).

Subject: world:<world_id>:asset:<asset_id>
Relations: kind, path, url, title, tags, parent_scene, codex_ref, status
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Literal, Optional

from resileos.answer.hub_train import ensure_hub_subject, train_hub
from resileos.answer.workbench import Workbench

AssetKind = Literal["image", "video", "audio", "game_codex", "scene", "prop", "other"]

_ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def _check_id(name: str, label: str) -> str:
    n = name.strip().lower()
    if not _ID_RE.match(n):
        raise ValueError(f"invalid {label} id {name!r}; use [a-z0-9_]{{1,64}}")
    return n


@dataclass
class WorldAsset:
    world_id: str
    asset_id: str
    kind: AssetKind
    title: str = ""
    path: str = ""          # local path under assets/ or absolute
    url: str = ""           # remote render / CDN
    tags: str = ""          # comma-separated
    parent_scene: str = ""
    codex_ref: str = ""     # game / animation codex key
    status: str = "draft"   # draft | ready | archived

    def subject(self) -> str:
        wid = _check_id(self.world_id, "world")
        aid = _check_id(self.asset_id, "asset")
        return f"world:{wid}:asset:{aid}"

    def triples(self) -> list[tuple[str, str, str]]:
        s = self.subject()
        rows = [
            (s, "kind", self.kind),
            (s, "status", self.status),
        ]
        if self.title:
            rows.append((s, "title", self.title[:256]))
        if self.path:
            rows.append((s, "path", self.path[:512]))
        if self.url:
            rows.append((s, "url", self.url[:512]))
        if self.tags:
            rows.append((s, "tags", self.tags[:256]))
        if self.parent_scene:
            rows.append((s, "parent_scene", self.parent_scene[:64]))
        if self.codex_ref:
            rows.append((s, "codex_ref", self.codex_ref[:128]))
        return rows


@dataclass
class AssetIndex:
    """Sidecar JSON index (paths/URLs) mirrored into Titanos on register."""

    path: Path
    assets: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "AssetIndex":
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(path=path, assets=dict(data.get("assets", {})))
        return cls(path=path, assets={})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"assets": self.assets}, indent=2),
            encoding="utf-8",
        )

    def put(self, asset: WorldAsset) -> None:
        self.assets[asset.subject()] = asdict(asset)
        self.save()


def register_asset(wb: Workbench, asset: WorldAsset, index: Optional[AssetIndex] = None) -> int:
    """Learn asset triples into Titanos; optionally update sidecar index."""
    n = train_hub(wb, asset.triples(), require_hub_prefix=True)
    if index is not None:
        index.put(asset)
    return n


def register_many(
    wb: Workbench,
    assets: Iterable[WorldAsset],
    index: Optional[AssetIndex] = None,
) -> int:
    total = 0
    for a in assets:
        total += register_asset(wb, a, index=index)
    return total


def list_assets_for_world(wb: Workbench, world_id: str, kind: Optional[str] = None) -> list[str]:
    """Return asset subjects that have kind recorded (scan via known index preferred)."""
    # Without a secondary index query API, callers should use AssetIndex.
    # This helper returns empty and documents the index path.
    _ = (wb, world_id, kind)
    return []


def asset_from_dict(d: dict) -> WorldAsset:
    return WorldAsset(
        world_id=str(d["world_id"]),
        asset_id=str(d["asset_id"]),
        kind=d.get("kind", "other"),  # type: ignore[arg-type]
        title=str(d.get("title", "")),
        path=str(d.get("path", "")),
        url=str(d.get("url", "")),
        tags=str(d.get("tags", "")),
        parent_scene=str(d.get("parent_scene", "")),
        codex_ref=str(d.get("codex_ref", "")),
        status=str(d.get("status", "draft")),
    )
