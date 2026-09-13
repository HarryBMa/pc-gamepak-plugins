"""Tests for the cartridge reader.

Run with `python -m pytest test/` or `python test/test_cartridges.py`.
No Decky, no Deck, no Steam — this half is plain file parsing on purpose.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cartridges  # noqa: E402


class Parsing(unittest.TestCase):
    def test_a_single_game_becomes_a_collection_of_one(self):
        got = cartridges.parse_conf(
            "executable=steam://rungameid/413150\n"
            "title=Stardew Valley\n"
            "cover=cover.jpg\n"
        )
        self.assertEqual(got["title"], "Stardew Valley")
        self.assertEqual(len(got["games"]), 1)
        self.assertEqual(got["games"][0]["executable"], "steam://rungameid/413150")

    def test_a_bundle_keeps_every_game(self):
        got = cartridges.parse_conf(
            "[collection]\n"
            "title=God of War Collection\n"
            "cover=collection.jpg\n"
            "\n"
            "[game]\n"
            "title=God of War (2018)\n"
            "executable=steam://rungameid/310970\n"
            "cover=cover_0.jpg\n"
            "\n"
            "[game]\n"
            "title=God of War: Ragnarok\n"
            "executable=steam://rungameid/2322010\n"
        )
        self.assertEqual(got["title"], "God of War Collection")
        self.assertEqual(len(got["games"]), 2)
        self.assertEqual(got["games"][1]["title"], "God of War: Ragnarok")
        # The collection's own cover, not a game's.
        self.assertEqual(got["art"]["cover"], "collection.jpg")

    def test_comments_and_blank_lines_are_ignored(self):
        got = cartridges.parse_conf(
            "# a comment\n"
            "; another\n"
            "\n"
            "   title=Spaced Out   \n"
            "executable=steam://rungameid/1\n"
        )
        self.assertEqual(got["title"], "Spaced Out")

    def test_keys_are_case_insensitive(self):
        got = cartridges.parse_conf("TITLE=Shouty\nExecutable=steam://rungameid/1\n")
        self.assertEqual(got["title"], "Shouty")

    def test_a_value_containing_equals_survives(self):
        got = cartridges.parse_conf(
            "title=X\nexecutable=steam://run?a=1&b=2\n"
        )
        self.assertEqual(got["games"][0]["executable"], "steam://run?a=1&b=2")

    def test_an_empty_file_does_not_explode(self):
        got = cartridges.parse_conf("")
        self.assertEqual(got["title"], "Unknown game")
        self.assertEqual(got["games"][0]["executable"], "")


class OnDisk(unittest.TestCase):
    def cartridge(self, conf: str, files=()):
        root = Path(tempfile.mkdtemp())
        (root / cartridges.CONF_NAME).write_text(conf, encoding="utf-8")
        for name in files:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        return root

    def test_art_beside_the_conf_is_found(self):
        root = self.cartridge(
            "title=X\nexecutable=steam://rungameid/1\ncover=cover.jpg\n",
            ["cover.jpg"],
        )
        got = cartridges.read_cartridge(root)
        self.assertTrue(got["art"]["cover"].endswith("cover.jpg"))

    def test_a_bare_name_is_also_looked_for_in_gamepak(self):
        # The wizard copies art into .gamepak/ but the conf may name it plainly.
        root = self.cartridge(
            "title=X\nexecutable=steam://rungameid/1\ncover=cover_0.png\n",
            [".gamepak/cover_0.png"],
        )
        got = cartridges.read_cartridge(root)
        self.assertIn(".gamepak", got["art"]["cover"])

    def test_art_outside_the_cartridge_is_refused(self):
        root = self.cartridge(
            "title=X\nexecutable=steam://rungameid/1\ncover=../escape.png\n"
        )
        (root.parent / "escape.png").write_bytes(b"\x89PNG")
        got = cartridges.read_cartridge(root)
        self.assertNotIn("cover", got["art"])

    def test_a_missing_cover_falls_back_to_a_conventional_name(self):
        root = self.cartridge(
            "title=X\nexecutable=steam://rungameid/1\n", ["cover.png"]
        )
        got = cartridges.read_cartridge(root)
        self.assertTrue(got["art"]["cover"].endswith("cover.png"))

    def test_a_game_with_no_executable_is_dropped(self):
        # The launcher shows these and explains. A home row cannot.
        root = self.cartridge(
            "[collection]\ntitle=C\n\n"
            "[game]\ntitle=Playable\nexecutable=steam://rungameid/1\n\n"
            "[game]\ntitle=Broken\n"
        )
        got = cartridges.read_cartridge(root)
        self.assertEqual([g["title"] for g in got["games"]], ["Playable"])

    def test_a_directory_with_no_conf_is_not_a_cartridge(self):
        self.assertIsNone(cartridges.read_cartridge(Path(tempfile.mkdtemp())))

    def test_a_game_without_its_own_art_inherits_the_cartridge_s(self):
        root = self.cartridge(
            "[collection]\ntitle=C\ncover=collection.png\n\n"
            "[game]\ntitle=G\nexecutable=steam://rungameid/1\n",
            ["collection.png"],
        )
        got = cartridges.read_cartridge(root)
        self.assertTrue(got["games"][0]["art"]["cover"].endswith("collection.png"))


class Scanning(unittest.TestCase):
    def test_both_mount_shapes_are_found(self):
        base = Path(tempfile.mkdtemp())
        # /run/media/<user>/<label> and SteamOS's /run/media/<label>
        deep = base / "harry" / "CART_A"
        flat = base / "CART_B"
        for d in (deep, flat):
            d.mkdir(parents=True)
            (d / cartridges.CONF_NAME).write_text(
                "title=T\nexecutable=steam://rungameid/1\n", encoding="utf-8"
            )
        found = {c["mount"] for c in cartridges.scan((str(base),))}
        self.assertEqual(found, {str(deep), str(flat)})

    def test_a_missing_mount_root_is_not_an_error(self):
        self.assertEqual(cartridges.scan(("/no/such/place",)), [])


class Stats(unittest.TestCase):
    """The count on the drive, which is the half that makes it cross-machine."""

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.root = Path(self.scratch.name)
        (self.root / cartridges.CONF_NAME).write_text(
            "title=Stardew Valley\nexecutable=steam://rungameid/413150\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.scratch.cleanup()

    def test_the_key_matches_the_launchers(self):
        # A row written on Windows has to be the row found here.
        self.assertEqual(
            cartridges.stats_key("Games\\Foo\\Foo.exe"),
            cartridges.stats_key("Games/Foo/Foo.exe"),
        )
        self.assertEqual(
            cartridges.stats_key("Steam://RunGameID/620"),
            cartridges.stats_key("steam://rungameid/620"),
        )
        # A path is left alone: two files can differ by case on ext4.
        self.assertNotEqual(cartridges.stats_key("a/x.sh"), cartridges.stats_key("a/X.sh"))
        # A drive letter is not a scheme.
        self.assertEqual(cartridges.stats_key("C://Games/Foo.exe"), "C://Games/Foo.exe")

    def test_a_cartridge_with_no_history_reads_as_empty(self):
        self.assertEqual(cartridges.read_stats(self.root), {})

    def test_a_corrupt_file_reads_as_empty_rather_than_raising(self):
        (self.root / cartridges.ASSET_DIR).mkdir()
        cartridges.stats_path(self.root).write_text("{ not json", encoding="utf-8")
        self.assertEqual(cartridges.read_stats(self.root), {})

    def test_the_desktops_hours_arrive_with_the_cartridge(self):
        (self.root / cartridges.ASSET_DIR).mkdir()
        cartridges.stats_path(self.root).write_text(
            '{"version": 1, "games": {"steam://rungameid/413150": '
            '{"launches": 9, "seconds": 36000, "lastHost": "workshop"}}}',
            encoding="utf-8",
        )
        cartridge = cartridges.read_cartridge(self.root)
        self.assertEqual(cartridge["games"][0]["stats"]["launches"], 9)
        self.assertEqual(cartridge["games"][0]["stats"]["seconds"], 36000)

    def test_a_game_nobody_has_played_has_an_empty_history(self):
        cartridge = cartridges.read_cartridge(self.root)
        self.assertEqual(cartridge["games"][0]["stats"], {})

    def test_a_launch_here_is_added_to_what_the_desktop_recorded(self):
        (self.root / cartridges.ASSET_DIR).mkdir()
        cartridges.stats_path(self.root).write_text(
            '{"version": 1, "games": {"steam://rungameid/413150": '
            '{"launches": 9, "seconds": 36000, "firstPlayed": 1700000000}}}',
            encoding="utf-8",
        )
        self.assertTrue(
            cartridges.record_launch(
                self.root, "steam://rungameid/413150", "Stardew Valley", host="steamdeck"
            )
        )
        entry = cartridges.read_stats(self.root)["steam://rungameid/413150"]
        self.assertEqual(entry["launches"], 10, "the desktop's nine are still there")
        self.assertEqual(entry["seconds"], 36000, "no duration is invented here")
        self.assertEqual(entry["firstPlayed"], 1700000000, "first play is not today")
        self.assertEqual(entry["lastHost"], "steamdeck")
        self.assertGreater(entry["lastPlayed"], 1700000000)

    def test_a_first_launch_starts_the_row(self):
        cartridges.record_launch(self.root, "steam://rungameid/1", "X", host="steamdeck")
        entry = cartridges.read_stats(self.root)["steam://rungameid/1"]
        self.assertEqual(entry["launches"], 1)
        self.assertEqual(entry["seconds"], 0)
        self.assertEqual(entry["firstPlayed"], entry["lastPlayed"])

    def test_a_write_that_cannot_land_is_reported_not_raised(self):
        # The parent is a file, so the .gamepak directory cannot be made.
        blocked = self.root / "blocked"
        blocked.write_text("not a directory", encoding="utf-8")
        self.assertFalse(cartridges.record_launch(blocked, "steam://rungameid/1"))

    def test_writing_leaves_no_temporary_file_behind(self):
        cartridges.record_launch(self.root, "steam://rungameid/1")
        leftovers = [
            p.name for p in (self.root / cartridges.ASSET_DIR).iterdir()
            if p.name.endswith(".tmp")
        ]
        self.assertEqual(leftovers, [])


class FrontEndSetting(unittest.TestCase):
    """Whether PC GamePak has made this plugin the front-end."""

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        os.environ["PC_GAMEPAK_CONFIG_DIR"] = self.scratch.name

    def tearDown(self):
        os.environ.pop("PC_GAMEPAK_CONFIG_DIR", None)
        self.scratch.cleanup()

    def write(self, text):
        Path(self.scratch.name, cartridges.SETTINGS_FILE).write_text(
            text, encoding="utf-8"
        )

    def test_no_settings_file_means_enabled(self):
        # The plugin is documented as needing PC GamePak not to be installed.
        # Refusing to work until a program the user does not have says it may
        # would be absurd.
        self.assertIsNone(cartridges.settings_path())
        self.assertTrue(cartridges.is_enabled())

    def test_switched_on_is_enabled(self):
        self.write('{"frontends": {"launcher": false, "decky": true}}')
        self.assertTrue(cartridges.is_enabled())

    def test_switched_off_is_disabled(self):
        # The one thing the file can do: take this plugin out of the picture.
        self.write('{"frontends": {"launcher": true, "decky": false}}')
        self.assertFalse(cartridges.is_enabled())

    def test_a_file_that_says_nothing_about_us_means_enabled(self):
        for text in [
            "{}",
            '{"frontends": {}}',
            '{"frontends": {"launcher": true}}',
            '{"frontends": "nonsense"}',
            '{"steamgriddbEnabled": true}',
        ]:
            self.write(text)
            self.assertTrue(cartridges.is_enabled(), text)

    def test_an_unreadable_file_means_enabled(self):
        # A half-written or corrupt settings file must not silently remove the
        # only front-end on a Deck.
        self.write("{ not json at all")
        self.assertTrue(cartridges.is_enabled())

    def test_a_non_boolean_is_not_read_as_one(self):
        self.write('{"frontends": {"decky": "no"}}')
        self.assertTrue(cartridges.is_enabled())


if __name__ == "__main__":
    unittest.main(verbosity=2)
