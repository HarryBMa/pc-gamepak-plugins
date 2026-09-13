"""Package a plugin for release.

    python tools/package.py decky     dist/pc-gamepak-decky-<version>.zip   (run `pnpm run build` in decky/ first)
    python tools/package.py galaxy    dist/pc-gamepak-galaxy-<version>.zip  (vendors galaxy.plugin.api for GOG Galaxy's Python)
    python tools/package.py sync      dist/pc-gamepak-sync-<version>.pyz    (one file: `python pc-gamepak-sync.pyz`)

The Playnite extension packs itself: `playnite/build.ps1 -Pack`.
Each prints the path it wrote, and nothing else, so a workflow can upload it.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipapp
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DIST = REPO / "dist"

# GOG Galaxy embeds 64-bit CPython 3.13 on Windows; its integrations must bring
# wheels built for exactly that.
GALAXY_PIP_TARGET = ["--platform", "win_amd64", "--python-version", "3.13",
                     "--implementation", "cp", "--only-binary=:all:"]


def add_tree(archive: zipfile.ZipFile, source: Path, prefix: str) -> None:
    for path in sorted(source.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            archive.write(path, prefix + "/" + path.relative_to(source).as_posix())


def decky() -> Path:
    plugin = REPO / "decky"
    version = json.loads((plugin / "package.json").read_text(encoding="utf-8"))["version"]
    if not (plugin / "dist" / "index.js").is_file():
        sys.exit("decky/dist/index.js is missing: run `pnpm run build` in decky/ first")
    out = DIST / ("pc-gamepak-decky-%s.zip" % version)
    # The folder inside the zip is the one Decky installs, and the name PC
    # GamePak's settings look for.
    name = "pc-gamepak-decky"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in ("main.py", "cartridges.py", "plugin.json", "package.json", "README.md"):
            archive.write(plugin / file, name + "/" + file)
        archive.write(REPO / "LICENSE", name + "/LICENSE")
        add_tree(archive, plugin / "dist", name + "/dist")
        add_tree(archive, plugin / "assets", name + "/assets")
    return out


def galaxy() -> Path:
    plugin = REPO / "gog-galaxy"
    version = json.loads((plugin / "manifest.json").read_text(encoding="utf-8"))["version"]
    out = DIST / ("pc-gamepak-galaxy-%s.zip" % version)
    name = "pc-gamepak-galaxy"
    with tempfile.TemporaryDirectory() as tmp:
        vendor = Path(tmp) / "vendor"
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
             "--target", str(vendor), "-r", str(plugin / "requirements.txt")] + GALAXY_PIP_TARGET,
            check=True,
        )
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in ("manifest.json", "plugin.py", "catalog.py"):
                archive.write(plugin / file, name + "/" + file)
            add_tree(archive, REPO / "common" / "gamepak", name + "/gamepak")
            # Galaxy puts the integration's own folder on the path, so the
            # dependencies sit beside plugin.py rather than in a subfolder.
            add_tree(archive, vendor, name)
    return out


def sync() -> Path:
    source = REPO / "sync" / "pc_gamepak_sync" / "__init__.py"
    version = re.search(r'__version__ = "([^"]+)"', source.read_text(encoding="utf-8"))
    version = version.group(1) if version else "0.1.0"
    out = DIST / ("pc-gamepak-sync-%s.pyz" % version)
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "app"
        shutil.copytree(REPO / "sync" / "pc_gamepak_sync", staging / "pc_gamepak_sync",
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(REPO / "common" / "gamepak", staging / "gamepak",
                        ignore=shutil.ignore_patterns("__pycache__"))
        zipapp.create_archive(staging, out, interpreter="/usr/bin/env python3", main="pc_gamepak_sync.__main__:main")
    return out


def main() -> int:
    targets = {"decky": decky, "galaxy": galaxy, "sync": sync}
    if len(sys.argv) != 2 or sys.argv[1] not in targets:
        print(__doc__)
        return 2
    DIST.mkdir(exist_ok=True)
    print(targets[sys.argv[1]]())
    return 0


if __name__ == "__main__":
    sys.exit(main())
