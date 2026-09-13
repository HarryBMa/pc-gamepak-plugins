"""ES-DE (EmulationStation Desktop Edition): a "PC GamePak" system.

ES-DE takes extra systems from `custom_systems/es_systems.xml` in its
application data folder. This adds one system, `pcgamepak`, whose ROM folder is
a directory this owns: a launch script per game on a plugged-in cartridge.
Titles go in the system's `gamelist.xml`, and cover, background and logo in
`downloaded_media/pcgamepak/{covers,fanart,marquees}`, named after each script
as ES-DE expects.

Other custom systems in the same file are left exactly as they are. ES-DE reads
all of this at start.

Not yet run against ES-DE itself: the layout follows its user guide.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional

from . import shared

FRONTEND_ID = "esde"
SYSTEM = "pcgamepak"

MEDIA = (("cover", "covers"), ("background", "fanart"), ("logo", "marquees"))


def data_dirs() -> List[Path]:
    override = os.environ.get("ESDE_APPDATA_DIR")
    dirs = [Path(override)] if override else []
    return dirs + [shared.home() / "ES-DE"]


def system_element(roms: Path, windows: Optional[bool] = None) -> ET.Element:
    windows = os.name == "nt" if windows is None else windows
    system = ET.Element("system")
    for tag, text in (
        ("name", SYSTEM),
        ("fullname", "PC GamePak"),
        ("path", str(roms)),
        ("extension", ".cmd .CMD" if windows else ".sh"),
        ("command", "cmd.exe /C %ROM%" if windows else "/bin/sh %ROM%"),
        ("platform", "pc"),
        ("theme", "pc"),
    ):
        ET.SubElement(system, tag).text = text
    return system


def merge_systems(text: str, system: ET.Element) -> str:
    """`es_systems.xml` with our system replaced, everyone else's untouched."""
    # A hand-edited file that does not parse raises here, and is left alone:
    # somebody else's systems are not ours to repair or overwrite.
    root = ET.fromstring(text) if text.strip() else ET.Element("systemList")
    if root.tag != "systemList":
        raise ValueError("es_systems.xml does not start with <systemList>")
    for existing in list(root.findall("system")):
        if (existing.findtext("name") or "").strip() == SYSTEM:
            root.remove(existing)
    root.append(system)
    _indent(root)
    return '<?xml version="1.0"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def gamelist_text(found: List[shared.Entry], scripts: dict) -> str:
    root = ET.Element("gameList")
    for entry in found:
        game = ET.SubElement(root, "game")
        ET.SubElement(game, "path").text = "./" + scripts[entry.id].name
        ET.SubElement(game, "name").text = entry.title
    _indent(root)
    return '<?xml version="1.0"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def _indent(element: ET.Element, level: int = 0) -> None:
    # ElementTree.indent is 3.9+; GOG Galaxy's Python is 3.7, and this package
    # is kept runnable there.
    pad = "\n" + "\t" * level
    children = list(element)
    if children:
        if not (element.text or "").strip():
            element.text = pad + "\t"
        for child in children:
            _indent(child, level + 1)
            child.tail = pad + "\t"
        children[-1].tail = pad


class Exporter:
    frontend_id = FRONTEND_ID
    name = "ES-DE"

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or shared.first_existing(data_dirs())

    def available(self) -> bool:
        return self.data_dir is not None

    def apply(self, found: List[shared.Entry], launcher: Path) -> bool:
        changed = False
        roms = self.data_dir / "pc-gamepak" / "roms"
        scripts = shared.write_scripts(roms, launcher, found)

        systems_file = self.data_dir / "custom_systems" / "es_systems.xml"
        try:
            current = systems_file.read_text(encoding="utf-8")
        except OSError:
            current = ""
        changed |= shared.write_if_changed(systems_file, merge_systems(current, system_element(roms)))

        changed |= shared.write_if_changed(
            self.data_dir / "gamelists" / SYSTEM / "gamelist.xml", gamelist_text(found, scripts)
        )

        for kind, folder in MEDIA:
            directory = self.data_dir / "downloaded_media" / SYSTEM / folder
            keep = []
            for entry in found:
                copied = shared.copy_art(directory, entry, kind, name=scripts[entry.id].stem)
                if copied:
                    keep.append(copied)
            shared.prune(directory, keep)
        return changed
