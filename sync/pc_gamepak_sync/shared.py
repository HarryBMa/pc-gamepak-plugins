"""What every exporter does the same way: a launch script per game, artwork
copied off the cartridge, and files written only when they change.

Front-ends that read files rather than load plugins cannot run an argument
list; they run a file. So each game gets a small script that runs
`pc-gamepak --drive <root> --play <n>` and waits for it, which is what lets the
front-end time the game and the cartridge carry its saves and hours.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from gamepak import install
from gamepak.cartridge import Cartridge, Game

# Every entry an exporter writes into somebody else's data starts with this, so
# it can find its own entries again and never touches anyone else's.
ID_PREFIX = "pcgamepak-"


class Entry:
    """One playable game on a cartridge that is plugged in."""

    def __init__(self, cartridge: Cartridge, game: Game):
        self.cartridge = cartridge
        self.game = game

    @property
    def id(self) -> str:
        return ID_PREFIX + self.game.key

    @property
    def title(self) -> str:
        return self.game.title or self.cartridge.title

    @property
    def stem(self) -> str:
        """A file name for this game: readable, and unique by the key."""
        slug = re.sub(r"[^A-Za-z0-9]+", "-", self.title).strip("-").lower()[:40] or "game"
        return "%s-%s" % (slug, self.game.key[:8])


def entries(cartridges: Iterable[Cartridge]) -> List[Entry]:
    return [Entry(c, g) for c in cartridges for g in c.playable_games]


def script_suffix(windows: Optional[bool] = None) -> str:
    return ".cmd" if (os.name == "nt" if windows is None else windows) else ".sh"


def script_text(launcher: Path, entry: Entry, windows: Optional[bool] = None) -> str:
    windows = os.name == "nt" if windows is None else windows
    args = install.play_args(launcher, entry.cartridge.root, entry.game.index)
    line = install.command_line(args, windows=windows)
    if windows:
        return "@echo off\r\nrem %s\r\n%s\r\n" % (entry.title, line)
    return "#!/bin/sh\n# %s\nexec %s\n" % (entry.title.replace("\n", " "), line)


def write_if_changed(path: Path, text: str, executable: bool = False) -> bool:
    """Write `text` to `path` unless it already says that. Atomic."""
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    if executable:
        mode = os.stat(temporary).st_mode
        os.chmod(temporary, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(temporary, path)
    return True


def write_scripts(directory: Path, launcher: Path, found: List[Entry]) -> Dict[str, Path]:
    """One launch script per entry in `directory`, which this owns entirely."""
    directory.mkdir(parents=True, exist_ok=True)
    scripts = {}
    for entry in found:
        path = directory / (entry.stem + script_suffix())
        write_if_changed(path, script_text(launcher, entry), executable=os.name != "nt")
        scripts[entry.id] = path
    prune(directory, set(scripts.values()))
    return scripts


def copy_art(directory: Path, entry: Entry, kind: str, name: Optional[str] = None) -> Optional[Path]:
    """Copy one picture off the cartridge, so the front-end is not reading the
    drive — and does not lose the picture the moment it is pulled."""
    source = entry.game.art.get(kind) or entry.cartridge.art.get(kind)
    if not source:
        return None
    target = directory / ((name or entry.stem + "-" + kind) + Path(source).suffix.lower())
    try:
        if not target.is_file() or target.stat().st_size != Path(source).stat().st_size:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    except OSError:
        return None
    return target


def prune(directory: Path, keep: Iterable[Path]) -> None:
    """Remove every file in a directory this owns that is not in `keep`."""
    keep = {Path(p).resolve() for p in keep}
    try:
        children = list(directory.iterdir())
    except OSError:
        return
    for child in children:
        if child.is_file() and child.resolve() not in keep:
            try:
                child.unlink()
            except OSError:
                pass


def owned_dir(frontend_id: str) -> Path:
    """Where the scripts and art for one front-end live on this machine."""
    return install.settings_dir() / "sync" / frontend_id


def first_existing(paths: Iterable[Path]) -> Optional[Path]:
    for path in paths:
        if path.is_dir():
            return path
    return None


def home() -> Path:
    return Path(os.environ.get("HOME") or os.environ.get("USERPROFILE") or os.path.expanduser("~"))
