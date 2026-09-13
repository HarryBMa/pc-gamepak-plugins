"""Tests for the cartridge reader.

Run with `python -m pytest test/` or `python test/test_cartridges.py`.
No Decky, no Deck, no Steam — this half is plain file parsing on purpose.
"""

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
