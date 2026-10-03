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


def comment_safe(text: str) -> str:
    """A title fit to sit in a script comment.

    The title comes off a cartridge somebody may have handed you. In a .cmd
    file `rem FTL & calc` runs calc: `&`, `|`, `<`, `>` and `^` end a `rem`
    line early. Anything but plain printable text is dropped rather than
    escaped, because it is only ever a label for a person reading the file.
    """
    return re.sub(r"[^A-Za-z0-9 .,:;'!?()\[\]_+-]", "", text)[:80]


def script_text(launcher: Path, entry: Entry, windows: Optional[bool] = None) -> str:
    """A launch script for one game.

    It checks the cartridge is there before asking the launcher to play it.
    Heroic, Pegasus and ES-DE all read their lists at start, so a game can stay
    on screen after its cartridge has gone, until the front-end restarts; Play
    on it then says to plug the cartridge in rather than doing nothing.
    """
    windows = os.name == "nt" if windows is None else windows
    root = entry.cartridge.root
    args = install.play_args(launcher, root, entry.game.index)
    line = install.command_line(args, windows=windows)
    label = comment_safe(entry.title)
    conf = str(root / "cartridge.conf")
    message = "Plug in the cartridge for %s, then press Play again." % label
    if windows:
        return (
            "@echo off\r\n"
            "rem %s\r\n"
            "if not exist %s (\r\n"
            "  powershell -NoProfile -WindowStyle Hidden -Command \"Add-Type -AssemblyName PresentationFramework; "
            "[System.Windows.MessageBox]::Show('%s', 'PC GamePak') | Out-Null\"\r\n"
            "  exit /b 1\r\n"
            ")\r\n"
            "%s\r\n"
        ) % (label, install.quote_windows(conf), message.replace("'", "''"), line)
    return (
        "#!/bin/sh\n"
        "# %s\n"
        "if [ ! -f %s ]; then\n"
        "  notify-send 'PC GamePak' %s 2>/dev/null || echo %s >&2\n"
        "  exit 1\n"
        "fi\n"
        "exec %s\n"
    ) % (label, install.quote_posix(conf), install.quote_posix(message), install.quote_posix(message), line)


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


def write_scripts(directory: Path, launcher: Path, found: List[Entry], keep_gone: bool = False) -> Dict[str, Path]:
    """One launch script per entry in `directory`, which this owns entirely.

    `keep_gone` leaves the scripts of games whose cartridge has left. A
    front-end that has not re-read its list still shows those games, and Play on
    one runs its script — which has to exist to say "plug the cartridge in".
    Deleting it made Play do nothing at all, silently, in Heroic. Only right
    where the front-end runs the script its own entry names and nothing else;
    ES-DE lists every script in its folder as a game, so there the scripts go.
    """
    directory.mkdir(parents=True, exist_ok=True)
    scripts = {}
    for entry in found:
        path = directory / (entry.stem + script_suffix())
        write_if_changed(path, script_text(launcher, entry), executable=os.name != "nt")
        scripts[entry.id] = path
    if not keep_gone:
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
