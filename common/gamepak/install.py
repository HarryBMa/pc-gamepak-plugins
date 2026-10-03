"""What a front-end needs from an installed PC GamePak.

Two things: whether the user has switched this front-end on, and how to ask the
launcher to play or eject. The contract is PC GamePak's (`core/src/frontend.rs`
and `core/src/settings.rs`): one boolean per front-end in `settings.json`,
plugins off until switched on, and the launcher doing every launch so saves,
hours and shader caches travel with the cartridge.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional


def settings_dir() -> Path:
    """Where PC GamePak keeps settings.json. Mirrors `settings::settings_dir`."""
    override = os.environ.get("PC_GAMEPAK_CONFIG_DIR", "").strip()
    if override:
        return Path(override)
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "").strip()
        return Path(local) / "PC-GamePak" if local else Path(".")
    # Decky runs plugin backends with a HOME that is not the user's.
    home = os.environ.get("DECKY_USER_HOME") or os.environ.get("HOME") or "."
    return Path(home) / ".local" / "state" / "pc-gamepak"


def settings_path() -> Path:
    return settings_dir() / "settings.json"


def pc_gamepak_configured() -> bool:
    """Whether PC GamePak has ever written its settings on this machine."""
    return settings_path().is_file()


def frontend_on(frontend_id: str, text: Optional[str] = None) -> bool:
    """Whether `frontend_id` has been switched on.

    Only a real `true` counts: `"yes"` is not a boolean and a plugin being on is
    not something to infer. A file that cannot be read or parsed is the same as
    no file, as it is for the launcher.
    """
    if text is None:
        try:
            text = settings_path().read_text(encoding="utf-8")
        except OSError:
            return False
    try:
        settings = json.loads(text)
    except ValueError:
        return False
    frontends = settings.get("frontends") if isinstance(settings, dict) else None
    return isinstance(frontends, dict) and frontends.get(frontend_id) is True


def launcher_path() -> Optional[Path]:
    """The installed launcher, or None. `PC_GAMEPAK_LAUNCHER` overrides."""
    override = os.environ.get("PC_GAMEPAK_LAUNCHER", "").strip()
    if override and Path(override).is_file():
        return Path(override)

    candidates = []
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            candidates.append(Path(local) / "PC-GamePak" / "pc-gamepak.exe")
    else:
        home = os.environ.get("DECKY_USER_HOME") or os.environ.get("HOME") or ""
        if home:
            candidates.append(Path(home) / ".local" / "bin" / "pc-gamepak")
        candidates += [Path("/usr/local/bin/pc-gamepak"), Path("/usr/bin/pc-gamepak")]
        on_path = shutil.which("pc-gamepak")
        if on_path:
            candidates.append(Path(on_path))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def play_args(launcher: Path, root: Path, index: int) -> List[str]:
    """Play game `index` with no window; the launcher stays up while it runs."""
    return [str(launcher), "--drive", str(root), "--play", str(index)]


def show_args(launcher: Path, root: Path) -> List[str]:
    """The launcher's window on a drive, whatever on_cartridge_insert says."""
    return [str(launcher), "--drive", str(root), "--show"]


def eject_args(launcher: Path, root: Path, force: bool = False) -> List[str]:
    args = [str(launcher), "--drive", str(root), "--safe-eject"]
    return args + ["--force"] if force else args


def start_detached(args: List[str]) -> subprocess.Popen:
    """Start a launcher that outlives whatever asked for it."""
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(args, **kwargs)


def quote_windows(arg: str) -> str:
    """One argument for a .cmd line.

    A drive root is the trap: `"E:\\"` ends in a backslash that escapes the
    closing quote, so a root goes unquoted when it can be, and otherwise has its
    trailing backslash doubled.
    """
    if arg and not any(c in arg for c in ' \t"&|<>^'):
        return arg
    if arg.endswith("\\"):
        arg += "\\"
    return '"' + arg.replace('"', '""') + '"'


def quote_posix(arg: str) -> str:
    return "'" + arg.replace("'", "'\"'\"'") + "'"


def command_line(args: List[str], windows: Optional[bool] = None) -> str:
    windows = os.name == "nt" if windows is None else windows
    quote = quote_windows if windows else quote_posix
    return " ".join(quote(arg) for arg in args)
