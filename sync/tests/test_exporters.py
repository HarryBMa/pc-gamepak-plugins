"""Tests for pc-gamepak-sync's exporters, against each front-end's file format.

    python -m unittest discover -s sync/tests
"""

import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "common"))
sys.path.insert(0, str(HERE.parents[1]))

from gamepak.cartridge import read_cartridge  # noqa: E402
from pc_gamepak_sync import __main__ as cli  # noqa: E402
from pc_gamepak_sync import esde, heroic, pegasus, shared  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.cart = self.base / "CART"
        self.write(self.cart / ".gamepak" / "cover.png", "png")
        self.write(self.cart / ".gamepak" / "background.png", "bg")
        self.write(self.cart / "cartridge.conf",
                   "[collection]\ntitle=Pack\ncover=.gamepak/cover.png\n"
                   "[game]\ntitle=Alpha\nexecutable=steam://rungameid/1\nbackground=.gamepak/background.png\n"
                   "[game]\ntitle=No exe\n"
                   "[game]\ntitle=Gamma\nexecutable=Games/g.exe\n")
        self.launcher = self.write(self.base / "bin" / "pc-gamepak.exe", "")
        self.entries = shared.entries([read_cartridge(self.cart)])

    def tearDown(self):
        self._tmp.cleanup()

    @staticmethod
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class SharedTests(Fixture):
    def test_only_playable_games_become_entries_and_keep_their_numbers(self):
        self.assertEqual([(e.title, e.game.index) for e in self.entries], [("Alpha", 0), ("Gamma", 2)])

    def test_a_script_plays_the_game_by_its_launcher_number(self):
        gamma = self.entries[1]
        windows = shared.script_text(self.launcher, gamma, windows=True)
        self.assertIn("--play 2", windows)
        self.assertTrue(windows.startswith("@echo off"))
        posix = shared.script_text(self.launcher, gamma, windows=False)
        self.assertTrue(posix.startswith("#!/bin/sh"))
        self.assertIn("exec ", posix)
        self.assertIn("'--play' '2'", posix)

    def test_a_title_cannot_run_a_command_from_a_script_comment(self):
        evil = shared.Entry(read_cartridge(self.cart), self.entries[0].game)
        evil.game.title = 'FTL & calc.exe | del /q C:\\ ^ > x'
        windows = shared.script_text(self.launcher, evil, windows=True)
        comment = [line for line in windows.split("\r\n") if line.startswith("rem ")][0]
        for bad in "&|^<>\\":
            self.assertNotIn(bad, comment)
        self.assertIn("FTL", comment)

    def test_a_script_checks_the_cartridge_is_there_first(self):
        alpha = self.entries[0]
        windows = shared.script_text(self.launcher, alpha, windows=True)
        self.assertLess(windows.index("if not exist"), windows.index("--play"))
        self.assertIn("exit /b 1", windows)
        posix = shared.script_text(self.launcher, alpha, windows=False)
        self.assertLess(posix.index("if [ ! -f"), posix.index("exec "))

    def test_scripts_for_games_that_left_are_removed(self):
        directory = self.base / "scripts"
        shared.write_scripts(directory, self.launcher, self.entries)
        self.assertEqual(len(list(directory.iterdir())), 2)
        shared.write_scripts(directory, self.launcher, self.entries[:1])
        self.assertEqual(len(list(directory.iterdir())), 1)


class HeroicTests(Fixture):
    def test_merges_into_the_library_and_leaves_other_games_alone(self):
        config = self.base / "heroic"
        library = config / "sideload_apps" / "library.json"
        self.write(library, json.dumps({"games": [{"app_name": "someone-else", "title": "Theirs"}], "other": 1}))
        exporter = heroic.Exporter(config_dir=config, owned=self.base / "owned")

        self.assertTrue(exporter.apply(self.entries, self.launcher))
        data = json.loads(library.read_text(encoding="utf-8"))
        self.assertEqual(data["other"], 1)
        names = [g["app_name"] for g in data["games"]]
        self.assertEqual(names[0], "someone-else")
        ours = [g for g in data["games"] if g["app_name"].startswith("pcgamepak-")]
        self.assertEqual([g["title"] for g in ours], ["Alpha", "Gamma"])
        alpha = ours[0]
        self.assertEqual(alpha["runner"], "sideload")
        self.assertTrue(Path(alpha["install"]["executable"]).is_file())
        self.assertTrue(alpha["art_cover"].startswith("file:"))
        self.assertIn("art_background", alpha)

        self.assertFalse(exporter.apply(self.entries, self.launcher), "nothing changed, nothing written")

        script = Path(alpha["install"]["executable"])
        exporter.apply([], self.launcher)
        data = json.loads(library.read_text(encoding="utf-8"))
        self.assertEqual([g["app_name"] for g in data["games"]], ["someone-else"])
        self.assertEqual(list((self.base / "owned" / "art").iterdir()), [])
        # Heroic keeps showing the game until its library is refreshed, and Play
        # runs this script: it must still be there to say "plug it in".
        self.assertTrue(script.is_file(), "the script outlives the cartridge")

    def test_a_missing_or_broken_library_is_started_fresh(self):
        config = self.base / "heroic"
        self.write(config / "sideload_apps" / "library.json", "{not json")
        heroic.Exporter(config_dir=config, owned=self.base / "owned").apply(self.entries, self.launcher)
        data = json.loads((config / "sideload_apps" / "library.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["games"]), 2)


class PegasusTests(Fixture):
    def test_writes_a_collection_and_lists_its_folder_once(self):
        config = self.base / "pegasus-frontend"
        self.write(config / "game_dirs.txt", "/games/snes")
        exporter = pegasus.Exporter(config_dir=config)

        exporter.apply(self.entries, self.launcher)
        exporter.apply(self.entries, self.launcher)

        dirs = (config / "game_dirs.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(dirs, ["/games/snes", str(exporter.games_dir)])

        meta = (exporter.games_dir / "metadata.pegasus.txt").read_text(encoding="utf-8")
        self.assertIn("collection: PC GamePak", meta)
        self.assertIn("game: Alpha", meta)
        self.assertIn("game: Gamma", meta)
        self.assertIn("assets.boxFront: media/", meta)
        self.assertIn("assets.background: media/", meta)
        for line in meta.splitlines():
            if line.startswith("file: "):
                self.assertTrue((exporter.games_dir / line[6:]).is_file(), line)

        exporter.apply([], self.launcher)
        meta = (exporter.games_dir / "metadata.pegasus.txt").read_text(encoding="utf-8")
        self.assertNotIn("game:", meta)
        self.assertEqual(len(list((exporter.games_dir / "scripts").iterdir())), 2,
                         "Pegasus runs only what metadata names, so gone scripts can stay to explain")

    def test_a_title_cannot_start_a_new_key(self):
        self.assertEqual(pegasus.one_line("Evil\nlaunch: rm -rf /"), "Evil launch: rm -rf /")

    def test_launch_line_per_platform(self):
        self.assertIn('launch: cmd /c "{file.path}"', pegasus.metadata_text([], {}, {}, windows=True))
        self.assertIn('launch: sh "{file.path}"', pegasus.metadata_text([], {}, {}, windows=False))


class EsdeTests(Fixture):
    def test_adds_its_system_and_keeps_everyone_elses(self):
        data = self.base / "ES-DE"
        systems = data / "custom_systems" / "es_systems.xml"
        self.write(systems, "<systemList><system><name>mine</name><fullname>Mine</fullname></system></systemList>")
        exporter = esde.Exporter(data_dir=data)

        exporter.apply(self.entries, self.launcher)
        exporter.apply(self.entries, self.launcher)

        root = ET.fromstring(systems.read_text(encoding="utf-8"))
        self.assertEqual([s.findtext("name") for s in root.findall("system")], ["mine", "pcgamepak"])
        ours = root.findall("system")[1]
        roms = Path(ours.findtext("path"))
        self.assertIn("%ROM%", ours.findtext("command"))

        gamelist = ET.fromstring((data / "gamelists" / "pcgamepak" / "gamelist.xml").read_text(encoding="utf-8"))
        games = gamelist.findall("game")
        self.assertEqual([g.findtext("name") for g in games], ["Alpha", "Gamma"])
        for game in games:
            script = roms / game.findtext("path")[2:]
            self.assertTrue(script.is_file())
            cover = data / "downloaded_media" / "pcgamepak" / "covers" / (script.stem + ".png")
            self.assertTrue(cover.is_file(), "media is named after the script")
        fanart = list((data / "downloaded_media" / "pcgamepak" / "fanart").iterdir())
        self.assertEqual(len(fanart), 1, "only Alpha has a background")

        exporter.apply([], self.launcher)
        self.assertEqual(list(roms.iterdir()), [])
        self.assertEqual(list((data / "downloaded_media" / "pcgamepak" / "covers").iterdir()), [])

    def test_a_systems_file_that_does_not_parse_is_left_alone(self):
        data = self.base / "ES-DE"
        systems = self.write(data / "custom_systems" / "es_systems.xml", "<systemList><system>")
        with self.assertRaises(ET.ParseError):
            esde.Exporter(data_dir=data).apply(self.entries, self.launcher)
        self.assertEqual(systems.read_text(encoding="utf-8"), "<systemList><system>")


class SyncLoopTests(Fixture):
    def setUp(self):
        super().setUp()
        self._env = dict(os.environ)
        os.environ["PC_GAMEPAK_CONFIG_DIR"] = str(self.base / "settings")
        os.environ["PC_GAMEPAK_LAUNCHER"] = str(self.launcher)
        self._scan = cli.scan
        self.plugged = [read_cartridge(self.cart)]
        cli.scan = lambda: list(self.plugged)

    def tearDown(self):
        cli.scan = self._scan
        os.environ.clear()
        os.environ.update(self._env)
        super().tearDown()

    def settings(self, frontends):
        self.write(self.base / "settings" / "settings.json", json.dumps({"frontends": frontends}))

    def exporter(self):
        return pegasus.Exporter(config_dir=self.base / "pegasus-frontend")

    def meta(self, exporter):
        path = exporter.games_dir / "metadata.pegasus.txt"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def test_only_a_switched_on_frontend_is_filled(self):
        exporter = self.exporter()
        self.settings({"pegasus": False})
        cli.sync_once([exporter])
        self.assertNotIn("game:", self.meta(exporter))

        self.settings({"pegasus": True})
        cli.sync_once([exporter])
        self.assertIn("game: Alpha", self.meta(exporter))

    def test_pulling_the_cartridge_empties_it_and_nothing_repeats(self):
        exporter = self.exporter()
        self.settings({"pegasus": True})
        first = cli.sync_once([exporter])
        self.assertEqual(cli.sync_once([exporter], previous=first), first)

        self.plugged = []
        cli.sync_once([exporter], previous=first)
        self.assertNotIn("game:", self.meta(exporter))


if __name__ == "__main__":
    unittest.main()
