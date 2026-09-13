"""PC GamePak for GOG Galaxy 2.0.

Cartridge games in Galaxy's library: owned once seen, installed while the
cartridge is in. Play runs `pc-gamepak --play`, so saves, hours and shader
caches go with the cartridge, and the game shows as running for as long as
the launcher does — which is as long as the game does.

Nothing to log in to. Galaxy asks every integration to authenticate, and this
one answers at once with a local account.
"""

import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# A release carries gamepak/ beside this file; a checkout has it in ../common.
for _candidate in (_HERE, _HERE.parent / "common"):
    if (_candidate / "gamepak").is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from galaxy.api.consts import LicenseType, LocalGameState, Platform  # noqa: E402
from galaxy.api.plugin import Plugin, create_and_run_plugin  # noqa: E402
from galaxy.api.types import Authentication, Game, LicenseInfo, LocalGame  # noqa: E402

import catalog  # noqa: E402
from gamepak import install, scan  # noqa: E402

__version__ = "0.1.0"

CACHE_KEY = "games"
SCAN_SECONDS = 2.0


class PcGamePakPlugin(Plugin):
    def __init__(self, reader, writer, token):
        super().__init__(Platform.Generic, __version__, reader, writer, token)
        self.catalog = catalog.Catalog()
        self.running = {}  # game id -> the launcher playing it
        self._last_scan = 0.0

    # ------------------------------------------------------------------ Galaxy asks

    async def authenticate(self, stored_credentials=None):
        return Authentication("pc-gamepak", "PC GamePak")

    def handshake_complete(self):
        self.catalog = catalog.Catalog.from_cache(self.persistent_cache.get(CACHE_KEY))
        self._scan()

    async def get_owned_games(self):
        self._scan()
        return [
            Game(game_id, title, None, LicenseInfo(LicenseType.SinglePurchase))
            for game_id, title in sorted(self.catalog.owned.items(), key=lambda item: item[1].lower())
        ]

    async def get_local_games(self):
        self._scan()
        return [LocalGame(game_id, self._state(game_id)) for game_id in self.catalog.owned]

    async def launch_game(self, game_id):
        location = self.catalog.location(game_id)
        launcher = install.launcher_path()
        if location is None or launcher is None:
            return  # not plugged in, or no PC GamePak: nothing Play could do
        root, index = location
        self.running[game_id] = install.start_detached(install.play_args(launcher, root, index))
        self.update_local_game_status(LocalGame(game_id, self._state(game_id)))

    async def install_game(self, game_id):
        # There is nothing to download: installing a cartridge game is plugging
        # the cartridge in. Showing the launcher's window for it would need the
        # drive, which by definition is not here.
        return

    async def uninstall_game(self, game_id):
        return

    def tick(self):
        finished = [game_id for game_id, process in self.running.items() if process.poll() is not None]
        for game_id in finished:
            del self.running[game_id]
            self.update_local_game_status(LocalGame(game_id, self._state(game_id)))

        if time.monotonic() - self._last_scan >= SCAN_SECONDS:
            self._scan(notify=True)

    async def shutdown(self):
        self.push_cache()

    # ------------------------------------------------------------------ internals

    def _state(self, game_id):
        state = LocalGameState.None_
        if self.catalog.is_installed(game_id):
            state |= LocalGameState.Installed
        if game_id in self.running:
            state |= LocalGameState.Running
        return state

    def _scan(self, notify=False):
        self._last_scan = time.monotonic()
        # PC GamePak's rule for every plugin: off until switched on. Off looks
        # like nothing plugged in, so the library stays but every game greys out.
        cartridges = scan() if install.frontend_on(catalog.FRONTEND_ID) else []
        changes = self.catalog.refresh(cartridges)
        if not changes:
            return
        if changes.added:
            self.persistent_cache[CACHE_KEY] = self.catalog.to_cache()
            self.push_cache()
        if not notify:
            return
        for game_id, title in changes.added:
            self.add_game(Game(game_id, title, None, LicenseInfo(LicenseType.SinglePurchase)))
        for game_id in changes.installed + changes.uninstalled:
            self.update_local_game_status(LocalGame(game_id, self._state(game_id)))


def main():
    create_and_run_plugin(PcGamePakPlugin, sys.argv)


if __name__ == "__main__":
    main()
