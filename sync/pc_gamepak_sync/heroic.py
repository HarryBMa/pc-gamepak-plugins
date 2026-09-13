"""Heroic Games Launcher: cartridge games as sideloaded apps.

Heroic has no plugin API, but it keeps sideloaded games in one JSON file,
`sideload_apps/library.json`, as `{"games": [...]}`. Each cartridge game is
written there as a sideload whose executable is its launch script, and taken
out again when the cartridge goes. Only entries whose `app_name` starts with
`pcgamepak-` are ever touched.

Not yet run against Heroic itself: the field names follow Heroic's `GameInfo`
and `InstalledInfo` types. Heroic may need restarting to notice a change.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from . import shared

FRONTEND_ID = "heroic"


def config_dirs() -> List[Path]:
    home = shared.home()
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        return [Path(appdata) / "heroic"] if appdata else []
    return [
        home / ".config" / "heroic",
        home / ".var" / "app" / "com.heroicgameslauncher.hgl" / "config" / "heroic",
    ]


def game_record(entry: shared.Entry, script: Path, cover: Optional[Path], background: Optional[Path]) -> Dict:
    art = cover.as_uri() if cover else ""
    record = {
        "runner": "sideload",
        "app_name": entry.id,
        "title": entry.title,
        "install": {
            "executable": str(script),
            "platform": "Windows" if os.name == "nt" else "linux",
            "is_dlc": False,
        },
        "folder_name": str(entry.cartridge.root),
        "art_cover": art,
        "art_square": art,
        "is_installed": True,
        "canRunOffline": True,
    }
    if background:
        record["art_background"] = background.as_uri()
    return record


def merge(library: Dict, ours: List[Dict]) -> Dict:
    """`library` with every pcgamepak entry replaced by `ours`, order kept."""
    games = library.get("games") if isinstance(library.get("games"), list) else []
    kept = [g for g in games if not (isinstance(g, dict) and str(g.get("app_name", "")).startswith(shared.ID_PREFIX))]
    return dict(library, games=kept + ours)


class Exporter:
    frontend_id = FRONTEND_ID
    name = "Heroic Games Launcher"

    def __init__(self, config_dir: Optional[Path] = None, owned: Optional[Path] = None):
        self.config_dir = config_dir or shared.first_existing(config_dirs())
        self.owned = owned or shared.owned_dir(FRONTEND_ID)

    def available(self) -> bool:
        return self.config_dir is not None

    def apply(self, found: List[shared.Entry], launcher: Path) -> bool:
        library_path = self.config_dir / "sideload_apps" / "library.json"
        try:
            library = json.loads(library_path.read_text(encoding="utf-8"))
            if not isinstance(library, dict):
                library = {}
        except (OSError, ValueError):
            library = {}

        scripts = shared.write_scripts(self.owned / "scripts", launcher, found)
        art_dir = self.owned / "art"
        records, keep = [], []
        for entry in found:
            cover = shared.copy_art(art_dir, entry, "cover")
            background = shared.copy_art(art_dir, entry, "background")
            keep += [p for p in (cover, background) if p]
            records.append(game_record(entry, scripts[entry.id], cover, background))
        shared.prune(art_dir, keep)

        text = json.dumps(merge(library, records), indent=2) + "\n"
        return shared.write_if_changed(library_path, text)
