"""Finding cartridges and reading what is on them.

Kept apart from `main.py` so it is plain Python with no Decky imports: it can be
run and tested on any machine, which is the only way this half gets verified
without a Deck in front of you.

The format is PC GamePak's, unchanged:

    executable=steam://rungameid/413150
    title=Stardew Valley
    cover=cover.jpg

or, for more than one game:

    [collection]
    title=God of War Collection
    cover=collection.jpg

    [game]
    title=God of War (2018)
    executable=steam://rungameid/310970
    cover=cover_0.jpg

Art paths are relative to `cartridge.conf` and may sit in `.gamepak/`. Nothing
outside the cartridge is ever read: a path that climbs out with `..` is refused,
which is the same rule the launcher applies.

The one file here that is also written is `.gamepak/stats.json`, the cartridge's
own count of how often it has been played. It lives on the drive so the number
follows the cartridge between a desktop and a Deck, which only works if both of
them keep it.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

# Where desktops mount removable media. Ordered by how likely they are.
MOUNT_ROOTS = ("/run/media", "/media", "/mnt")

CONF_NAME = "cartridge.conf"
ASSET_DIR = ".gamepak"

# A cover is inlined into the UI, so a huge one is a mistake rather than a
# design. The launcher uses the same ceiling.
MAX_ART_BYTES = 8 * 1024 * 1024

ART_KEYS = ("cover", "background", "logo", "icon")

# What the cartridge remembers about being played, written by PC GamePak's
# launcher and read — and added to — here. The point of it living on the drive
# rather than on the host is that a cartridge carried between a desktop and a
# Deck keeps one count, so this plugin reading the desktop's hours is not a
# nicety, it is the feature working.
STATS_FILE = "stats.json"

# The longest a session started here may be credited with. Matches the
# launcher's ceiling, and for the same reason: wall clock is the only clock,
# and a Deck left suspended would otherwise wake up and add a week.
MAX_SESSION_SECONDS = 16 * 60 * 60


def parse_conf(text: str) -> dict[str, Any]:
    """Parse a cartridge.conf into `{title, executable, art, games}`.

    Both shapes come back the same way. A single game is a collection of one,
    so the caller never has to branch.
    """
    collection: dict[str, str] = {}
    general: dict[str, str] = {}
    games: list[dict[str, str]] = []
    section: dict[str, str] | None = general

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue

        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip().lower()
            if name == "collection":
                section = collection
            elif name == "game":
                games.append({})
                section = games[-1]
            else:
                section = general
            continue

        if "=" not in line or section is None:
            continue
        key, _, value = line.partition("=")
        section[key.strip().lower()] = value.strip()

    if games:
        head = collection or general
        return {
            "title": head.get("title", "Unknown cartridge"),
            "executable": games[0].get("executable", ""),
            "art": {k: head.get(k, "") for k in ART_KEYS},
            "games": [
                {
                    "title": g.get("title", "Unknown game"),
                    "executable": g.get("executable", ""),
                    "art": {k: g.get(k, "") for k in ART_KEYS},
                }
                for g in games
            ],
        }

    title = general.get("title", "Unknown game")
    executable = general.get("executable", "")
    art = {k: general.get(k, "") for k in ART_KEYS}
    return {
        "title": title,
        "executable": executable,
        "art": art,
        # One game, expressed as a list, so callers never special-case.
        "games": [{"title": title, "executable": executable, "art": art}],
    }


def resolve_art(root: Path, relative: str) -> str | None:
    """Turn a relative art path into an absolute one, or refuse it.

    Refuses anything that leaves the cartridge, anything missing, and anything
    absurdly large. Also looks in `.gamepak/` for a bare filename, because that
    is where the wizard puts art it copied.
    """
    if not relative:
        return None

    candidates = [root / relative]
    if "/" not in relative and "\\" not in relative:
        candidates.append(root / ASSET_DIR / relative)

    for path in candidates:
        try:
            resolved = path.resolve()
            resolved.relative_to(root.resolve())  # raises if it climbed out
        except (ValueError, OSError):
            continue
        if resolved.is_file() and resolved.stat().st_size <= MAX_ART_BYTES:
            return str(resolved)
    return None


def find_default_art(root: Path) -> str | None:
    """What the launcher falls back to when `cover=` is absent."""
    for name in ("cover.png", "cover.jpg", "poster.png", "box.png"):
        found = resolve_art(root, name)
        if found:
            return found
    return None


# Where PC GamePak keeps its settings, and the key that says which front-ends
# should handle a cartridge. Read, never written: the launcher owns this file.
#
# The whole contract between the two projects is one boolean in one JSON file.
# No socket, no daemon, no protocol to version — which matters because this is
# Python inside Steam's process tree and that is Rust in a window, and anything
# richer would be a thing to keep in step forever.
SETTINGS_DIRS = (
    os.path.join(
        os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
        "pc-gamepak",
    ),
)
SETTINGS_FILE = "settings.json"
FRONTEND_ID = "decky"


def settings_path() -> Path | None:
    """The launcher's settings file, if it is where it should be."""
    override = os.environ.get("PC_GAMEPAK_CONFIG_DIR")
    roots = (override,) + SETTINGS_DIRS if override else SETTINGS_DIRS
    for root in roots:
        candidate = Path(root) / SETTINGS_FILE
        if candidate.is_file():
            return candidate
    return None


def is_enabled() -> bool:
    """Whether this plugin has been made a front-end in PC GamePak's settings.

    **True when there is no answer**, which is the one judgement call here. A Deck
    with this plugin installed and PC GamePak not installed at all has no settings
    file to read, and refusing to work until a program the user does not have says
    it may would be absurd — the plugin is documented as needing nothing else.

    So the file only ever switches it *off*, and only when it explicitly says so.
    """
    path = settings_path()
    if path is None:
        return True
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return True
    frontends = data.get("frontends")
    if not isinstance(frontends, dict):
        return True
    value = frontends.get(FRONTEND_ID)
    return value if isinstance(value, bool) else True


def stats_key(executable: str) -> str:
    """The identity of a game, the way `.gamepak/stats.json` keys it.

    Kept in step with `stats::key_for` in gamepak-core, and it has to be: a row
    written by the launcher on Windows must be the row this finds on a Deck.
    Separators are normalised, and case is folded for URIs only — two files on
    a case-sensitive filesystem really can differ by case, and collapsing them
    would merge two games into one row.
    """
    trimmed = executable.strip().replace("\\", "/")
    scheme, sep, _ = trimmed.partition("://")
    is_uri = bool(sep) and len(scheme) >= 2 and scheme[:1].isalpha() and all(
        ch.isalnum() or ch in "+-." for ch in scheme
    )
    return trimmed.lower() if is_uri else trimmed


def stats_path(root: Path) -> Path:
    return root / ASSET_DIR / STATS_FILE


def read_stats(root: Path) -> dict[str, dict[str, Any]]:
    """What the cartridge has recorded, or nothing.

    A missing file and an unreadable one answer the same, on purpose: this is
    called to draw a line under a game's name, and a cartridge with no history
    and one whose history will not parse both have nothing to show.
    """
    try:
        with open(stats_path(root), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    games = data.get("games")
    return games if isinstance(games, dict) else {}


def write_stats(root: Path, games: dict[str, Any]) -> bool:
    """Replace the stats file, whole, or say it could not be done.

    Written beside itself and renamed into place, so a cartridge pulled out
    mid-write loses the update rather than ending up with a truncated file that
    reads as an empty history.
    """
    path = stats_path(root)
    temporary = path.with_suffix(".json.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "games": games}, handle, indent=2, sort_keys=True)
        os.replace(temporary, path)
        return True
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        return False


def record_launch(root: Path, executable: str, title: str = "", host: str = "") -> bool:
    """Count a launch on the cartridge.

    The count only. This plugin hands a `steam://` URI to Steam and is told
    nothing about what happens next — not when the game starts, and not when it
    stops — so there is no honest duration to add here. The launcher, which is
    a window that stays open for the session, records the hours; a cartridge
    played on a Deck gains launches and a last-played, which is the part
    somebody actually looks for.

    Returns False when the drive would not take the write. A read-only
    cartridge is a reason not to have a count, never a reason not to play.
    """
    key = stats_key(executable)
    if not key:
        return False

    games = read_stats(root)
    entry = games.get(key)
    if not isinstance(entry, dict):
        entry = {}

    now = int(time.time())
    if title.strip():
        entry["title"] = title.strip()
    entry["launches"] = int(entry.get("launches") or 0) + 1
    entry.setdefault("seconds", 0)
    if not entry.get("firstPlayed"):
        entry["firstPlayed"] = now
    entry["lastPlayed"] = now
    entry["lastHost"] = host or host_name()
    games[key] = entry
    return write_stats(root, games)


def host_name() -> str:
    """What to call this machine in `lastHost`.

    A Deck's hostname is usually `steamdeck`, which is exactly the useful thing
    to see next to a last-played date on a cartridge that also gets plugged
    into a desktop.
    """
    for var in ("HOSTNAME", "COMPUTERNAME"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    try:
        return Path("/etc/hostname").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def read_cartridge(root: Path) -> dict[str, Any] | None:
    """Read one mounted cartridge, or None if there is not one here."""
    conf = root / CONF_NAME
    if not conf.is_file():
        return None

    try:
        text = conf.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    parsed = parse_conf(text)

    def art_for(entry: dict[str, Any]) -> dict[str, str]:
        out: dict[str, str] = {}
        for key in ART_KEYS:
            found = resolve_art(root, entry["art"].get(key, ""))
            if found:
                out[key] = found
        if "cover" not in out:
            fallback = find_default_art(root)
            if fallback:
                out["cover"] = fallback
        return out

    history = read_stats(root)

    games = []
    for game in parsed["games"]:
        if not game["executable"]:
            continue  # nothing to start; the launcher shows these, a row cannot
        recorded = history.get(stats_key(game["executable"]))
        games.append(
            {
                "title": game["title"],
                "executable": game["executable"],
                "art": art_for(game) or art_for(parsed),
                # Whatever every machine that has played this cartridge has
                # recorded, including this one. Empty for a game nobody has
                # started yet.
                "stats": recorded if isinstance(recorded, dict) else {},
            }
        )

    return {
        "id": volume_id(root),
        "title": parsed["title"],
        "mount": str(root),
        "art": art_for(parsed),
        "games": games,
    }


def volume_id(root: Path) -> str:
    """A name for this cartridge that survives a different mount point.

    The filesystem UUID if `/dev/disk/by-uuid` can be walked back to this
    mount, otherwise the mount's basename. Not a stable identity in the second
    case, which is why it is only used for display grouping and de-duplication.
    """
    try:
        target = os.stat(root).st_dev
        by_uuid = Path("/dev/disk/by-uuid")
        if by_uuid.is_dir():
            for entry in by_uuid.iterdir():
                try:
                    if os.stat(entry).st_rdev == target:
                        return entry.name
                except OSError:
                    continue
    except OSError:
        pass
    return root.name


def candidate_mounts(roots: tuple[str, ...] = MOUNT_ROOTS) -> list[Path]:
    """Every directory a desktop might have mounted removable media at.

    Two levels: `/run/media/<user>/<label>` on most desktops, and
    `/run/media/<label>` on SteamOS, so both are checked.
    """
    found: list[Path] = []
    for base in roots:
        base_path = Path(base)
        if not base_path.is_dir():
            continue
        try:
            for first in base_path.iterdir():
                if not first.is_dir():
                    continue
                if (first / CONF_NAME).is_file():
                    found.append(first)
                    continue
                try:
                    for second in first.iterdir():
                        if second.is_dir() and (second / CONF_NAME).is_file():
                            found.append(second)
                except OSError:
                    continue
        except OSError:
            continue
    return found


def scan(roots: tuple[str, ...] = MOUNT_ROOTS) -> list[dict[str, Any]]:
    """Every cartridge mounted right now."""
    out = []
    for mount in candidate_mounts(roots):
        cartridge = read_cartridge(mount)
        if cartridge and cartridge["games"]:
            out.append(cartridge)
    return out
