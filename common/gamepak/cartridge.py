"""Finding PC GamePak cartridges and reading what is on them.

The format is PC GamePak's, read the way its launcher reads it
(`core/src/cartridge.rs`), so every front-end built on this sees the same games
in the same order:

    title=Stardew Valley
    executable=steam://rungameid/413150
    cover=.gamepak/cover.jpg

or a collection:

    [collection]
    title=God of War Collection

    [game]
    title=God of War (2018)
    executable=steam://rungameid/310970

Games are numbered in the order `cartridge.conf` lists them, counting every
non-empty `[game]` section whether or not it can be played, because that number
is what `pc-gamepak --play <n>` takes. A front-end that skipped the unplayable
ones before numbering would start the wrong game.

Python 3.7 or later and the standard library only: GOG Galaxy runs its
integrations on an embedded 3.7.
"""

from __future__ import annotations

import hashlib
import os
import string
from pathlib import Path
from typing import Dict, List, Optional

CONF_NAME = "cartridge.conf"
ASSET_DIR = ".gamepak"

# The launcher refuses a larger "cover", and so does this: a cartridge is a
# drive somebody may have handed you, and art gets copied into other programs.
MAX_ART_BYTES = 8 * 1024 * 1024

ART_KEYS = ("cover", "background", "logo", "icon")

# What the launcher falls back to when `cover=` is absent.
DEFAULT_COVERS = (
    "cover.png", "cover.jpg", "cover.jpeg", "cover.webp",
    "poster.png", "poster.jpg", "box.png", "box.jpg",
)

# Where Linux desktops mount removable media, most likely first. SteamOS mounts
# one level shallower than most desktops, so two levels are checked.
LINUX_MOUNT_ROOTS = ("/run/media", "/media", "/mnt")


class Game:
    """One game on a cartridge."""

    def __init__(self, index: int, title: str, executable: str, art: Dict[str, str]):
        self.index = index
        self.title = title
        self.executable = executable
        self.art = art

    @property
    def playable(self) -> bool:
        return bool(self.executable)

    @property
    def key(self) -> str:
        """Stable across plugging in again, and across machines.

        The executable, not the drive or the title: a Steam URI or a path on the
        cartridge names the same game wherever the drive is mounted, and a
        front-end that keys its library entries on this keeps them from one
        insert to the next.
        """
        return hashlib.sha1(self.executable.encode("utf-8")).hexdigest()[:16]

    def __repr__(self) -> str:
        return "Game(%d, %r)" % (self.index, self.title)


class Cartridge:
    """A mounted cartridge."""

    def __init__(self, root: Path, title: str, is_bundle: bool, art: Dict[str, str], games: List[Game]):
        self.root = root
        self.title = title
        self.is_bundle = is_bundle
        self.art = art
        self.games = games

    @property
    def playable_games(self) -> List[Game]:
        return [game for game in self.games if game.playable]

    def __repr__(self) -> str:
        return "Cartridge(%r, %r, %d games)" % (str(self.root), self.title, len(self.games))


def parse_conf(text: str) -> Dict[str, object]:
    """Split a cartridge.conf into its head section and its `[game]` sections."""
    sections = {}  # type: Dict[str, Dict[str, str]]
    games = []  # type: List[Dict[str, str]]
    current = sections.setdefault("general", {})

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("["):
            end = line.find("]")
            if end < 0:
                continue
            name = line[1:end].strip().lower()
            if name == "game":
                current = {}
                games.append(current)
            else:
                current = sections.setdefault(name, {})
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        current[key.strip().lower()] = value.strip()

    # An empty [game] is not a game: the launcher drops it before numbering.
    games = [game for game in games if game]
    return {"sections": sections, "games": games}


def resolve_art(root: Path, relative: str) -> Optional[str]:
    """An art path the cartridge supplied, made absolute, or None.

    Anything that would leave the drive is refused — absolute paths, drive
    letters and `..` alike — as is anything missing or absurdly large. A bare
    filename is also looked for in `.gamepak/`, where the wizard keeps artwork.
    """
    if not relative or not relative.strip():
        return None
    relative = relative.strip()
    if ":" in relative or relative.startswith(("/", "\\")):
        return None
    parts = [part for part in relative.replace("\\", "/").split("/") if part not in ("", ".")]
    if not parts or ".." in parts:
        return None

    candidates = [root.joinpath(*parts)]
    if len(parts) == 1:
        candidates.append(root / ASSET_DIR / parts[0])
    for path in candidates:
        try:
            if path.is_file() and 0 < path.stat().st_size <= MAX_ART_BYTES:
                return str(path)
        except OSError:
            continue
    return None


def _art(root: Path, section: Dict[str, str], guess_cover: bool) -> Dict[str, str]:
    art = {}
    for key in ART_KEYS:
        found = resolve_art(root, section.get(key, ""))
        if found:
            art[key] = found
    # Only the cover is guessed at. An absent hero stays absent.
    if guess_cover and "cover" not in art:
        for name in DEFAULT_COVERS:
            found = resolve_art(root, name)
            if found:
                art["cover"] = found
                break
    # The drive's own icon picture is there whether or not the conf names it.
    if "icon" not in art:
        found = resolve_art(root, "icon.png")
        if found:
            art["icon"] = found
    return art


def read_cartridge(root: Path) -> Optional[Cartridge]:
    """The cartridge at `root`, or None if there is not one."""
    root = Path(root)
    try:
        text = (root / CONF_NAME).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    parsed = parse_conf(text)
    sections = parsed["sections"]  # type: Dict[str, Dict[str, str]]
    raw_games = parsed["games"]  # type: List[Dict[str, str]]

    if raw_games:
        head = sections.get("collection", {})
        art = _art(root, head, guess_cover=True)
        games = []
        for index, raw in enumerate(raw_games):
            game_art = _art(root, raw, guess_cover=False)
            games.append(Game(
                index,
                raw.get("title") or "Unknown Game",
                raw.get("executable", ""),
                game_art or dict(art),
            ))
        if "cover" not in art:
            # A collection with no picture of its own borrows its first game's.
            art.update({k: v for k, v in games[0].art.items() if k == "cover"})
        return Cartridge(root, head.get("title") or "Game Collection", True, art, games)

    head = sections.get("general", {})
    art = _art(root, head, guess_cover=True)
    title = head.get("title") or "Unknown Game"
    return Cartridge(root, title, False, art, [Game(0, title, head.get("executable", ""), art)])


def candidate_roots() -> List[Path]:
    """Every place a cartridge could be mounted on this machine right now."""
    if os.name == "nt":
        return _windows_roots()
    return _linux_roots(LINUX_MOUNT_ROOTS)


def _windows_roots() -> List[Path]:
    system = os.path.splitdrive(os.environ.get("SystemRoot", "C:\\Windows"))[0].upper()
    roots = []
    for letter in string.ascii_uppercase:
        drive = letter + ":"
        # A stray C:\cartridge.conf would otherwise pin a cartridge in forever.
        if drive == system:
            continue
        root = Path(drive + "\\")
        try:
            if (root / CONF_NAME).is_file():
                roots.append(root)
        except OSError:
            continue  # an empty card reader, a drive pulled mid-look
    return roots


def _linux_roots(bases) -> List[Path]:
    found = []
    for base in bases:
        base_path = Path(base)
        try:
            firsts = [p for p in base_path.iterdir() if p.is_dir()]
        except OSError:
            continue
        for first in firsts:
            try:
                if (first / CONF_NAME).is_file():
                    found.append(first)
                    continue
                for second in first.iterdir():
                    if second.is_dir() and (second / CONF_NAME).is_file():
                        found.append(second)
            except OSError:
                continue
    return found


def scan(roots: Optional[List[Path]] = None) -> List[Cartridge]:
    """Every cartridge mounted right now, lowest drive or mount path first."""
    found = []
    for root in sorted(roots if roots is not None else candidate_roots(), key=str):
        cartridge = read_cartridge(root)
        if cartridge is not None:
            found.append(cartridge)
    return found
