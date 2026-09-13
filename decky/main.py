"""Decky backend: what is plugged in, and what is on it.

Thin on purpose. Everything that can be tested without a Deck lives in
`cartridges.py`; this file is the part that only exists inside Decky, so it
does as little as possible.
"""

import asyncio
import base64
import json
import mimetypes
import os
import re
import sys
from pathlib import Path
from typing import Any

import decky  # provided by Decky Loader at runtime

# Decky's plugin loader does not put the plugin's own directory on sys.path, so
# `import cartridges` raises ModuleNotFoundError at import time and the plugin
# process never finishes initialising. The failure is worse than it reads:
# nothing gets registered, so every RPC the UI makes answers "Route does not
# exist" rather than anything that points back here. Splice the directory in
# front of sys.path before importing anything of ours. The tests run from this
# directory already, so they neither need nor mind it.
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

import cartridges

# How often to re-scan. A mount appearing is not an event we get told about
# here, and inotify on three directories for a plugin that is usually idle is
# more machinery than it earns. Two seconds is under the time it takes someone
# to look up from plugging a drive in.
POLL_SECONDS = 2

# Art is handed to the UI as a data URI, because the browser Steam runs cannot
# read /run/media. Anything bigger than this is refused rather than inlined.
MAX_INLINE_BYTES = 4 * 1024 * 1024


def _data_uri(path: str) -> str | None:
    try:
        size = os.path.getsize(path)
        if size > MAX_INLINE_BYTES:
            return None
        raw = Path(path).read_bytes()
    except OSError:
        return None
    kind, _ = mimetypes.guess_type(path)
    return f"data:{kind or 'image/png'};base64," + base64.b64encode(raw).decode()


def _inline(cartridge: dict[str, Any]) -> dict[str, Any]:
    """Replace every art path with a data URI the UI can actually show."""

    def convert(art: dict[str, str]) -> dict[str, str]:
        out = {}
        for key, path in art.items():
            uri = _data_uri(path)
            if uri:
                out[key] = uri
        return out

    return {
        **cartridge,
        "art": convert(cartridge["art"]),
        "games": [{**g, "art": convert(g["art"])} for g in cartridge["games"]],
    }


class Plugin:
    _cartridges: list[dict[str, Any]] = []
    _serial: int = 0
    _task: asyncio.Task | None = None

    # ---------------------------------------------------------------- called by the UI

    async def get_cartridges(self) -> list[dict[str, Any]]:
        """Everything plugged in, with artwork inlined."""
        return [_inline(c) for c in self._cartridges]

    async def get_serial(self) -> int:
        """Bumped whenever the set of cartridges changes.

        The UI polls this rather than the whole list: it is one integer against
        a payload carrying every cover on the drive.
        """
        return self._serial

    async def get_app_ids(self) -> list[int]:
        """Just the Steam appids on the cartridges, for Deck Shelves.

        Deliberately not get_cartridges(): a shelf source only wants numbers,
        and that one inlines every cover as a data URI. Asking it for appids
        would ship megabytes of base64 to answer a question about integers.
        """
        found: list[int] = []
        for cartridge in self._cartridges:
            for game in cartridge["games"]:
                match = re.match(
                    r"steam://rungameid/(\d+)", game.get("executable", ""), re.I
                )
                if not match:
                    continue  # a path on the drive, or a heroic:// URI: no appid
                app_id = int(match.group(1))
                if app_id not in found:
                    found.append(app_id)
        return found

    async def get_shortcut_candidates(self) -> list[dict[str, str]]:
        """Games the cartridge carries itself, rather than points at.

        These name a path, not a URI, so Steam has never heard of them and they
        have no appid — which is why they cannot appear in a shelf. Handing one
        to Steam as a shortcut is the only way to give it one, and that is a
        write to the user's library, so it stays behind a setting.
        """
        out: list[dict[str, str]] = []
        for cartridge in self._cartridges:
            mount = os.path.realpath(cartridge["mount"])
            for game in cartridge["games"]:
                executable = game.get("executable", "")
                if not executable or re.match(r"[a-z][a-z0-9+.-]*://", executable, re.I):
                    continue  # a URI: Steam already knows how to open it
                # Cartridges are written on Windows too, so separators vary.
                relative = executable.replace("\\", "/")
                path = os.path.realpath(os.path.join(mount, relative))
                # A cartridge is a drive somebody handed you. `..` in the conf
                # must not become a shortcut pointing at the host.
                if not (path == mount or path.startswith(mount + os.sep)):
                    decky.logger.warning("refusing path outside the cartridge: %s", executable)
                    continue
                if not os.path.isfile(path):
                    continue
                out.append(
                    {
                        "title": game.get("title") or os.path.basename(path),
                        "exe": path,
                        "startDir": os.path.dirname(path),
                        "cartridge": cartridge["id"],
                    }
                )
        return out

    async def record_launch(self, cartridge: str, executable: str, title: str = "") -> bool:
        """Count a launch on the cartridge itself.

        The only write this plugin makes that is not behind a setting, and the
        case for it is the same as the launcher's: it happens because somebody
        pressed a game, it goes to the drive that game is on, and it is that
        drive's own bookkeeping. A cartridge that will not take the write keeps
        playing without a count.

        The count only — no hours. Steam is handed a URI and tells this plugin
        nothing about what happens next, so there is no duration here that
        would not be invented. The launcher, which stays open for the session,
        records those.
        """
        for known in self._cartridges:
            if known["id"] != cartridge:
                continue
            return await asyncio.to_thread(
                cartridges.record_launch, Path(known["mount"]), executable, title
            )
        decky.logger.warning("no cartridge called %s is mounted", cartridge)
        return False

    async def get_settings(self) -> dict[str, Any]:
        try:
            with open(self._settings_file(), encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return {}

    async def set_settings(self, data: dict[str, Any]) -> bool:
        try:
            with open(self._settings_file(), "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            return True
        except OSError:
            decky.logger.exception("could not save settings")
            return False

    @staticmethod
    def _settings_file() -> str:
        directory = getattr(decky, "DECKY_PLUGIN_SETTINGS_DIR", None) or os.path.dirname(
            os.path.abspath(__file__)
        )
        os.makedirs(directory, exist_ok=True)
        return os.path.join(directory, "settings.json")

    async def rescan(self) -> list[dict[str, Any]]:
        """Scan now rather than waiting for the next tick."""
        await self._refresh()
        return await self.get_cartridges()

    # ---------------------------------------------------------------- lifecycle

    async def _refresh(self) -> None:
        # Switched off in PC GamePak's settings means this plugin is not the
        # front-end on this machine, so it offers nothing: no row, no shelf, no
        # panel entries. Checked on every scan rather than at load, so turning it
        # on in the launcher takes effect without restarting Decky.
        if not await asyncio.to_thread(cartridges.is_enabled):
            if self._cartridges:
                decky.logger.info("switched off in PC GamePak settings; offering nothing")
                self._cartridges = []
                self._serial += 1
            return

        found = await asyncio.to_thread(cartridges.scan)

        # Compare on identity and contents, not on the inlined art — otherwise
        # every tick re-encodes megabytes of PNG to decide nothing changed.
        def shape(cs):
            return [
                (c["id"], c["mount"], tuple(g["executable"] for g in c["games"]))
                for c in cs
            ]

        if shape(found) != shape(self._cartridges):
            self._cartridges = found
            self._serial += 1
            decky.logger.info(
                "cartridges changed: %s",
                ", ".join(f"{c['title']} ({len(c['games'])})" for c in found) or "none",
            )

    async def _loop(self) -> None:
        while True:
            try:
                await self._refresh()
            except Exception:
                decky.logger.exception("scan failed")
            await asyncio.sleep(POLL_SECONDS)

    async def _main(self) -> None:
        decky.logger.info("pc-gamepak: watching %s", ", ".join(cartridges.MOUNT_ROOTS))
        self._task = asyncio.create_task(self._loop())
        await self._task

    async def _unload(self) -> None:
        if self._task:
            self._task.cancel()
        decky.logger.info("pc-gamepak: stopped")
