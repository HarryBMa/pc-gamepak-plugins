"""Heroic Games Launcher: cartridge games as sideloaded apps.

Heroic has no plugin API, but it keeps sideloaded games in one JSON file,
`sideload_apps/library.json`, as `{"games": [...]}`. Each cartridge game is
written there as a sideload whose executable is its launch script. Only entries
whose `app_name` starts with `pcgamepak-` are ever touched.

When a cartridge is pulled its games are not taken out at once. Heroic only
re-reads the file on a library refresh, so until then it shows the old tiles,
and Play on a tile whose record has gone hangs at "Launching" — Heroic looks up
game info for nothing. So a pulled cartridge's games stay, marked not installed,
for as long as Heroic is running: Play on one runs its script, which says to
plug the cartridge in. The first time Heroic is not running they are removed,
with their scripts and art, and its next start shows only what is plugged in.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional

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


def is_ours(game) -> bool:
    return isinstance(game, dict) and str(game.get("app_name", "")).startswith(shared.ID_PREFIX)


def games_in(library: Dict) -> List:
    return library.get("games") if isinstance(library.get("games"), list) else []


def merge(library: Dict, ours: List[Dict]) -> Dict:
    """`library` with every pcgamepak entry replaced by `ours`, order kept."""
    kept = [g for g in games_in(library) if not is_ours(g)]
    return dict(library, games=kept + ours)


def heroic_running() -> bool:
    """Whether Heroic is open, so its view of the library may be stale."""
    if os.name == "nt":
        try:
            listed = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Heroic.exe", "/NH", "/FO", "CSV"],
                capture_output=True, text=True, timeout=10,
                creationflags=0x08000000,  # CREATE_NO_WINDOW: no console flashing every look
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return True  # cannot tell: assume open, which is the safe side
        return "heroic.exe" in listed.lower()
    try:
        entries = os.listdir("/proc")
    except OSError:
        return True
    for pid in entries:
        if not pid.isdigit():
            continue
        try:
            with open("/proc/%s/comm" % pid, encoding="utf-8") as handle:
                if handle.read().strip().lower() == "heroic":
                    return True
        except OSError:
            continue
    return False


class Exporter:
    frontend_id = FRONTEND_ID
    name = "Heroic Games Launcher"

    def __init__(self, config_dir: Optional[Path] = None, owned: Optional[Path] = None,
                 running: Callable[[], bool] = heroic_running):
        self.config_dir = config_dir or shared.first_existing(config_dirs())
        self.owned = owned or shared.owned_dir(FRONTEND_ID)
        self.running = running

    def available(self) -> bool:
        return self.config_dir is not None

    def state(self) -> bool:
        """Part of what the sync loop watches: Heroic closing is the moment a
        pulled cartridge's games can finally be taken out."""
        return self.running()

    def apply(self, found: List[shared.Entry], launcher: Path, switched_on: bool = True) -> bool:
        library_path = self.config_dir / "sideload_apps" / "library.json"
        try:
            library = json.loads(library_path.read_text(encoding="utf-8"))
            if not isinstance(library, dict):
                library = {}
        except (OSError, ValueError):
            library = {}

        # A pulled cartridge's games stay, not installed, while Heroic is open
        # and may still be showing them. Closed, or switched off, they go.
        remember = switched_on and self.running()
        records = {}  # type: Dict[str, Dict]
        if remember:
            for game in games_in(library):
                if is_ours(game):
                    records[game["app_name"]] = dict(game, is_installed=False)

        # Their scripts stay with them: Play on a remembered game has to find a
        # script, which says to plug the cartridge in.
        scripts = shared.write_scripts(self.owned / "scripts", launcher, found, keep_gone=remember)
        art_dir = self.owned / "art"
        art = []
        for entry in found:
            cover = shared.copy_art(art_dir, entry, "cover")
            background = shared.copy_art(art_dir, entry, "background")
            art += [p for p in (cover, background) if p]
            records[entry.id] = game_record(entry, scripts[entry.id], cover, background)
        if not remember:
            shared.prune(art_dir, art)

        text = json.dumps(merge(library, list(records.values())), indent=2) + "\n"
        return shared.write_if_changed(library_path, text)
