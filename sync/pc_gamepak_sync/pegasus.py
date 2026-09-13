"""Pegasus Frontend: a "PC GamePak" collection of whatever is plugged in.

Pegasus reads `metadata.pegasus.txt` from the directories listed in its
`game_dirs.txt`. This owns one such directory, inside Pegasus's own config
folder, holding the metadata file, a launch script per game and the artwork,
and adds that directory to `game_dirs.txt` once. Pegasus reads both at start,
so a cartridge plugged in while it is running appears on its next start.

Not yet run against Pegasus itself: the keys follow its metadata and asset
documentation.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from . import shared

FRONTEND_ID = "pegasus"
COLLECTION = "PC GamePak"


def config_dirs() -> List[Path]:
    home = shared.home()
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        return [Path(local) / "pegasus-frontend"] if local else []
    return [
        home / ".config" / "pegasus-frontend",
        home / ".var" / "app" / "org.pegasus_frontend.Pegasus" / "config" / "pegasus-frontend",
    ]


def one_line(value: str) -> str:
    # A newline would start a new key; Pegasus has no escaping for it.
    return " ".join(value.split())


def metadata_text(found: List[shared.Entry], files: dict, art: dict, windows: Optional[bool] = None) -> str:
    windows = os.name == "nt" if windows is None else windows
    launch = 'cmd /c "{file.path}"' if windows else 'sh "{file.path}"'
    lines = [
        "# Written by pc-gamepak-sync. Rewritten whenever a cartridge comes or goes.",
        "collection: " + COLLECTION,
        "shortname: pcgamepak",
        "launch: " + launch,
        "",
    ]
    for entry in found:
        lines.append("game: " + one_line(entry.title))
        lines.append("file: " + files[entry.id])
        for key, asset in (("cover", "boxFront"), ("background", "background"), ("logo", "logo")):
            if (entry.id, key) in art:
                lines.append("assets.%s: %s" % (asset, art[(entry.id, key)]))
        lines.append("")
    return "\n".join(lines)


def with_game_dir(text: str, directory: str) -> Optional[str]:
    """`game_dirs.txt` with `directory` added, or None if it is already there."""
    listed = [line.strip() for line in text.splitlines()]
    if any(os.path.normcase(os.path.normpath(line)) == os.path.normcase(os.path.normpath(directory))
           for line in listed if line):
        return None
    body = text if not text or text.endswith("\n") else text + "\n"
    return body + directory + "\n"


class Exporter:
    frontend_id = FRONTEND_ID
    name = "Pegasus Frontend"

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or shared.first_existing(config_dirs())

    def available(self) -> bool:
        return self.config_dir is not None

    @property
    def games_dir(self) -> Path:
        return self.config_dir / "pc-gamepak"

    def apply(self, found: List[shared.Entry], launcher: Path) -> bool:
        changed = False
        scripts = shared.write_scripts(self.games_dir / "scripts", launcher, found)
        files = {key: "scripts/" + path.name for key, path in scripts.items()}

        art, keep = {}, []
        for entry in found:
            for kind in ("cover", "background", "logo"):
                copied = shared.copy_art(self.games_dir / "media", entry, kind)
                if copied:
                    art[(entry.id, kind)] = "media/" + copied.name
                    keep.append(copied)
        shared.prune(self.games_dir / "media", keep)

        changed |= shared.write_if_changed(self.games_dir / "metadata.pegasus.txt", metadata_text(found, files, art))

        dirs_file = self.config_dir / "game_dirs.txt"
        try:
            current = dirs_file.read_text(encoding="utf-8")
        except OSError:
            current = ""
        updated = with_game_dir(current, str(self.games_dir))
        if updated is not None:
            changed |= shared.write_if_changed(dirs_file, updated)
        return changed
