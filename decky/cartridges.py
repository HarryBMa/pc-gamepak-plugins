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
"""

from __future__ import annotations

import os
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

    games = []
    for game in parsed["games"]:
        if not game["executable"]:
            continue  # nothing to start; the launcher shows these, a row cannot
        games.append(
            {
                "title": game["title"],
                "executable": game["executable"],
                "art": art_for(game) or art_for(parsed),
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
