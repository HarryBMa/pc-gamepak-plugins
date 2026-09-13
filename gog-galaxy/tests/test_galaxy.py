"""Tests for the GOG Galaxy integration.

    python -m unittest discover -s gog-galaxy/tests

The catalog tests need nothing. The plugin tests drive the real
`galaxy.plugin.api` (pip install -r gog-galaxy/requirements.txt) and are
skipped without it.
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "common"))
sys.path.insert(0, str(HERE.parents[1]))

import catalog  # noqa: E402
from gamepak.cartridge import read_cartridge  # noqa: E402

try:
    import galaxy.api.plugin  # noqa: F401
    HAVE_GALAXY = True
except ImportError:
    HAVE_GALAXY = False


def make_cartridge(base, name, conf):
    root = Path(base) / name
    root.mkdir(parents=True)
    (root / "cartridge.conf").write_text(conf, encoding="utf-8")
    return read_cartridge(root)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ftl = make_cartridge(self._tmp.name, "FTL", "title=FTL\nexecutable=steam://rungameid/212680\n")
        self.pack = make_cartridge(self._tmp.name, "PACK",
                                   "[game]\ntitle=A\nexecutable=a.exe\n[game]\ntitle=Broken\n[game]\ntitle=C\nexecutable=c.exe\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_game_is_owned_once_seen_and_installed_while_plugged_in(self):
        library = catalog.Catalog()
        first = library.refresh([self.ftl])
        ftl_id = self.ftl.games[0].key
        self.assertEqual(first.added, [(ftl_id, "FTL")])
        self.assertEqual(first.installed, [ftl_id])
        self.assertTrue(library.is_installed(ftl_id))

        pulled = library.refresh([])
        self.assertEqual(pulled.added, [])
        self.assertEqual(pulled.uninstalled, [ftl_id])
        self.assertIn(ftl_id, library.owned, "still owned after the drive goes")
        self.assertFalse(library.is_installed(ftl_id))

        self.assertFalse(library.refresh([]), "nothing changed, nothing to say")

    def test_a_collection_keeps_launcher_numbers(self):
        library = catalog.Catalog()
        library.refresh([self.pack])
        c = self.pack.games[2]
        self.assertEqual(library.location(c.key), (self.pack.root, 2))
        self.assertEqual(len(library.owned), 2, "a game with nothing to run is not offered")

    def test_the_cache_round_trips_and_survives_junk(self):
        library = catalog.Catalog()
        library.refresh([self.ftl])
        again = catalog.Catalog.from_cache(library.to_cache())
        self.assertEqual(again.owned, library.owned)
        self.assertEqual(again.present, {}, "nothing is plugged in until a scan says so")
        for junk in (None, "", "not json", "[1,2]"):
            self.assertEqual(catalog.Catalog.from_cache(junk).owned, {})


class FakeProcess:
    def __init__(self):
        self.exited = False

    def poll(self):
        return 0 if self.exited else None


@unittest.skipUnless(HAVE_GALAXY, "galaxy.plugin.api is not installed")
class PluginTests(unittest.TestCase):
    def setUp(self):
        import plugin as plugin_module
        self.module = plugin_module
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self._env = dict(os.environ)
        os.environ["PC_GAMEPAK_CONFIG_DIR"] = str(base / "settings")
        launcher = base / "pc-gamepak.exe"
        launcher.write_text("", encoding="utf-8")
        os.environ["PC_GAMEPAK_LAUNCHER"] = str(launcher)
        (base / "settings").mkdir()
        (base / "settings" / "settings.json").write_text(json.dumps({"frontends": {"gog_galaxy": True}}), encoding="utf-8")

        self.ftl = make_cartridge(base, "FTL", "title=FTL\nexecutable=steam://rungameid/212680\n")
        self.plugged = [self.ftl]
        self._scan = plugin_module.scan
        plugin_module.scan = lambda: list(self.plugged)

        self.started = []
        self._start = plugin_module.install.start_detached

        def fake_start(args):
            self.started.append(args)
            self.process = FakeProcess()
            return self.process

        plugin_module.install.start_detached = fake_start
        self.loop = asyncio.new_event_loop()

    def tearDown(self):
        self.module.scan = self._scan
        self.module.install.start_detached = self._start
        os.environ.clear()
        os.environ.update(self._env)
        self.loop.close()
        self._tmp.cleanup()

    def run_async(self, coroutine):
        return self.loop.run_until_complete(coroutine)

    def make_plugin(self):
        sent = []

        async def build():
            plugin = self.module.PcGamePakPlugin(asyncio.StreamReader(), FakeWriter(), "token")
            plugin._connection.send_notification = lambda method, params=None, sensitive_params=False: sent.append((method, params))
            plugin._persistent_cache = {}
            return plugin

        return self.run_async(build()), sent

    def test_plays_through_the_launcher_and_reports_running_until_it_exits(self):
        from galaxy.api.consts import LocalGameState
        plugin, sent = self.make_plugin()
        plugin.handshake_complete()
        game_id = self.ftl.games[0].key

        owned = self.run_async(plugin.get_owned_games())
        self.assertEqual([(g.game_id, g.game_title) for g in owned], [(game_id, "FTL")])
        local = self.run_async(plugin.get_local_games())
        self.assertEqual(local[0].local_game_state, LocalGameState.Installed)

        self.run_async(plugin.launch_game(game_id))
        self.assertEqual(self.started[0][1:], ["--drive", str(self.ftl.root), "--play", "0"])
        self.assertEqual(sent[-1][0], "local_game_status_changed")
        self.assertEqual(sent[-1][1]["local_game"].local_game_state, LocalGameState.Installed | LocalGameState.Running)

        self.process.exited = True
        plugin.tick()
        self.assertEqual(sent[-1][1]["local_game"].local_game_state, LocalGameState.Installed)

    def test_pulling_the_cartridge_greys_the_game_out(self):
        from galaxy.api.consts import LocalGameState
        plugin, sent = self.make_plugin()
        plugin.handshake_complete()
        self.plugged = []
        plugin._last_scan = 0
        plugin.tick()
        self.assertEqual(sent[-1][0], "local_game_status_changed")
        self.assertEqual(sent[-1][1]["local_game"].local_game_state, LocalGameState.None_)
        self.assertEqual(len(self.run_async(plugin.get_owned_games())), 1, "still owned")

    def test_switched_off_offers_nothing_to_play(self):
        (Path(os.environ["PC_GAMEPAK_CONFIG_DIR"]) / "settings.json").write_text("{}", encoding="utf-8")
        plugin, _ = self.make_plugin()
        plugin.handshake_complete()
        self.assertEqual(self.run_async(plugin.get_owned_games()), [])
        self.run_async(plugin.launch_game(self.ftl.games[0].key))
        self.assertEqual(self.started, [])


class FakeWriter:
    def write(self, data):
        pass

    async def drain(self):
        pass

    def close(self):
        pass


if __name__ == "__main__":
    unittest.main()
