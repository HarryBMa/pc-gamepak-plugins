"""pc-gamepak-sync: keep file-based front-ends in step with what is plugged in.

    python -m pc_gamepak_sync              watch, and sync every front-end switched on
    python -m pc_gamepak_sync --once       sync once and exit
    python -m pc_gamepak_sync --list       say what was found and what is on

A front-end is synced when PC GamePak's settings switch it on
(`"frontends": {"heroic": true}`) and its data folder exists. When one is
switched off, or a cartridge leaves, its entries are taken out again.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Run from a checkout: common/ sits beside sync/. A release zip carries gamepak/
# next to this package instead, which is already on the path.
_HERE = Path(__file__).resolve()
for _candidate in (_HERE.parents[2] / "common", _HERE.parents[1]):
    if (_candidate / "gamepak").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from gamepak import install, scan  # noqa: E402

from . import esde, heroic, pegasus, shared  # noqa: E402

EXPORTERS = (heroic.Exporter, pegasus.Exporter, esde.Exporter)


def log(message: str) -> None:
    print(time.strftime("%H:%M:%S ") + message, flush=True)


def signature(cartridges, switches) -> tuple:
    """What, if it changes, means the front-ends need writing again."""
    shape = []
    for cartridge in cartridges:
        try:
            stamp = (cartridge.root / "cartridge.conf").stat().st_mtime_ns
        except OSError:
            stamp = 0
        shape.append((str(cartridge.root), stamp, tuple(g.key for g in cartridge.playable_games)))
    return tuple(shape), tuple(sorted(switches.items()))


def sync_once(exporters, only=None, previous=None):
    cartridges = scan()
    switches = {e.frontend_id: install.frontend_on(e.frontend_id) for e in exporters}
    if only:
        switches = {k: (v or k in only) for k, v in switches.items()}
    current = signature(cartridges, switches)
    if current == previous:
        return current

    launcher = install.launcher_path()
    if launcher is None:
        log("PC GamePak's launcher is not installed; nothing can be played, so nothing is synced")
        return current

    found = shared.entries(cartridges)
    for exporter in exporters:
        if not exporter.available():
            continue
        wanted = found if switches.get(exporter.frontend_id) else []
        try:
            if exporter.apply(wanted, launcher):
                log("%s: %d game%s" % (exporter.name, len(wanted), "" if len(wanted) == 1 else "s"))
        except Exception as error:  # one front-end's bad file must not stop the rest
            log("%s: %s" % (exporter.name, error))
    return current


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pc-gamepak-sync", description=__doc__.split("\n\n")[0])
    parser.add_argument("--once", action="store_true", help="sync once and exit")
    parser.add_argument("--list", action="store_true", help="show cartridges and front-ends, change nothing")
    parser.add_argument("--frontend", action="append", choices=[e.frontend_id for e in EXPORTERS],
                        help="sync this front-end even if PC GamePak's settings have not switched it on")
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between looks (default 2)")
    args = parser.parse_args(argv)

    exporters = [make() for make in EXPORTERS]

    if args.list:
        for cartridge in scan():
            print("cartridge %s: %s" % (cartridge.root, ", ".join(g.title for g in cartridge.playable_games)))
        print("launcher: %s" % (install.launcher_path() or "not installed"))
        for exporter in exporters:
            print("%-24s %-9s %s" % (
                exporter.name,
                "on" if install.frontend_on(exporter.frontend_id) else "off",
                "found" if exporter.available() else "not installed",
            ))
        return 0

    previous = None
    while True:
        previous = sync_once(exporters, only=args.frontend, previous=previous)
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
