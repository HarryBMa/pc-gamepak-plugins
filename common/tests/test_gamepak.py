"""Tests for the shared cartridge reader and install contract.

    python -m unittest discover -s common/tests
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gamepak import install  # noqa: E402
from gamepak.cartridge import read_cartridge, resolve_art, scan, _linux_roots  # noqa: E402


class Scratch:
    def __init__(self):
        self._dir = tempfile.TemporaryDirectory()
        self.root = Path(self._dir.name)

    def write(self, rel, text="x"):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def close(self):
        self._dir.cleanup()


class CartridgeTests(unittest.TestCase):
    def setUp(self):
        self.s = Scratch()

    def tearDown(self):
        self.s.close()

    def test_single_game(self):
        self.s.write(".gamepak/cover.png")
        self.s.write("icon.png")
        self.s.write("cartridge.conf", "title=FTL\nexecutable=steam://rungameid/212680\ncover=.gamepak/cover.png\n")
        cart = read_cartridge(self.s.root)
        self.assertEqual(cart.title, "FTL")
        self.assertFalse(cart.is_bundle)
        self.assertEqual([(g.index, g.title) for g in cart.games], [(0, "FTL")])
        self.assertTrue(cart.games[0].art["cover"].endswith("cover.png"))
        self.assertIn("icon", cart.art, "the drive's icon.png is found unnamed")

    def test_collection_numbers_games_as_the_launcher_does(self):
        # An empty [game] is dropped; one with no executable still takes a number.
        self.s.write("cartridge.conf", "[collection]\r\ntitle=Pack\r\n[game]\r\ntitle=A\r\nexecutable=a.exe\r\n"
                                       "[game]\r\n[game]\r\ntitle=No exe\r\n[game]\r\ntitle=C\r\nexecutable=c.exe\r\n")
        cart = read_cartridge(self.s.root)
        self.assertTrue(cart.is_bundle)
        self.assertEqual([(g.index, g.title, g.playable) for g in cart.games],
                         [(0, "A", True), (1, "No exe", False), (2, "C", True)])
        self.assertEqual([g.index for g in cart.playable_games], [0, 2])

    def test_keys_are_stable_and_distinct(self):
        self.s.write("cartridge.conf", "[game]\ntitle=A\nexecutable=steam://rungameid/1\n[game]\ntitle=B\nexecutable=steam://rungameid/2\n")
        first = [g.key for g in read_cartridge(self.s.root).games]
        second = [g.key for g in read_cartridge(self.s.root).games]
        self.assertEqual(first, second)
        self.assertNotEqual(first[0], first[1])

    def test_art_that_leaves_the_drive_is_refused(self):
        self.s.write("poster.jpg")
        for bad in ("../secret.png", "C:\\Windows\\win.ini", "/etc/passwd", "\\x.png", "a/../../b.png"):
            self.assertIsNone(resolve_art(self.s.root, bad), bad)
        self.s.write("cartridge.conf", "title=E\ncover=../secret.png\n")
        self.assertTrue(read_cartridge(self.s.root).art["cover"].endswith("poster.jpg"))

    def test_oversized_art_is_refused(self):
        big = self.s.root / "cover.png"
        with open(big, "wb") as handle:
            handle.truncate(8 * 1024 * 1024 + 1)
        self.assertIsNone(resolve_art(self.s.root, "cover.png"))

    def test_no_conf_is_no_cartridge(self):
        self.assertIsNone(read_cartridge(self.s.root))

    def test_linux_mounts_one_or_two_levels_deep(self):
        self.s.write("run/media/deck/CART/cartridge.conf", "title=Deep\n")
        self.s.write("run/media/SHALLOW/cartridge.conf", "title=Shallow\n")
        self.s.write("run/media/deck/USB/nothing.txt")
        roots = _linux_roots([str(self.s.root / "run" / "media")])
        titles = sorted(c.title for c in scan(roots))
        self.assertEqual(titles, ["Deep", "Shallow"])


class InstallTests(unittest.TestCase):
    def test_only_a_real_true_switches_a_frontend_on(self):
        on = install.frontend_on
        self.assertTrue(on("heroic", '{"frontends": {"heroic": true}}'))
        self.assertFalse(on("heroic", '{"frontends": {"heroic": "yes"}}'))
        self.assertFalse(on("heroic", '{"frontends": {"launcher": true}}'))
        self.assertFalse(on("heroic", '{"frontends": ["heroic"]}'))
        self.assertFalse(on("heroic", "not json"))
        self.assertFalse(on("heroic", "[]"))

    def test_settings_dir_override(self):
        old = os.environ.get("PC_GAMEPAK_CONFIG_DIR")
        os.environ["PC_GAMEPAK_CONFIG_DIR"] = "/tmp/pcg"
        try:
            self.assertEqual(install.settings_path(), Path("/tmp/pcg") / "settings.json")
        finally:
            if old is None:
                del os.environ["PC_GAMEPAK_CONFIG_DIR"]
            else:
                os.environ["PC_GAMEPAK_CONFIG_DIR"] = old

    def test_launcher_arguments(self):
        launcher, root = Path("pc-gamepak"), Path("D:\\")
        self.assertEqual(install.play_args(launcher, root, 2)[1:], ["--drive", str(root), "--play", "2"])
        self.assertEqual(install.eject_args(launcher, root, force=True)[-2:], ["--safe-eject", "--force"])

    def test_a_drive_root_survives_windows_quoting(self):
        self.assertEqual(install.quote_windows("E:\\"), "E:\\")
        self.assertEqual(install.quote_windows("C:\\My Cart\\"), '"C:\\My Cart\\\\"')
        self.assertEqual(
            install.command_line(["C:\\PC GamePak\\pc-gamepak.exe", "--drive", "E:\\", "--play", "0"], windows=True),
            '"C:\\PC GamePak\\pc-gamepak.exe" --drive E:\\ --play 0',
        )

    def test_posix_quoting(self):
        self.assertEqual(install.command_line(["/run/media/deck/It's/x"], windows=False), "'/run/media/deck/It'\"'\"'s/x'")


if __name__ == "__main__":
    unittest.main()
