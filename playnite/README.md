# PC GamePak for Playnite

[![Release](https://img.shields.io/github/v/release/HarryBMa/pc-gamepak-plugins?filter=playnite-v*&display_name=tag&label=release)](https://github.com/HarryBMa/pc-gamepak-plugins/releases?q=playnite-v)
[![CI](https://img.shields.io/github/actions/workflow/status/HarryBMa/pc-gamepak-plugins/ci.yml?branch=main&label=CI)](https://github.com/HarryBMa/pc-gamepak-plugins/actions/workflows/ci.yml)

A cartridge slot as the first tile in Playnite's library. With no cartridge in,
it shows an empty slot. Plug one in and the tile becomes that cartridge — its
title, cover, background and icon. Play starts the game; right-click ejects.

A cartridge is a drive with a `cartridge.conf` at its root, the format from
[PC GamePak](https://github.com/HarryBMa/pc-gamepak). Unlike the Decky plugin,
this one needs PC GamePak installed — a launcher new enough to have `--play`
and `--safe-eject` — because the launcher does every launch and every eject.

## What it does

- Checks every drive except the system drive for `cartridge.conf`, every two
  seconds. A rewritten `cartridge.conf` on a drive that never left counts as a
  change too.
- Keeps one library entry, sorted as `!` so it comes before every title under
  name ordering. A theme sorted by something else decides for itself.
- **A single-game cartridge:** Play runs `pc-gamepak.exe --drive X:\ --play 0`.
  No window appears, but the launcher still does what its window would — brings
  the saves and shader caches off the cartridge, counts the launch — and stays
  running until the game has ended, then takes them back. Playnite times that
  process, so its play time is right. **Open in PC GamePak** is on the tile's
  menu for the window.
- **A collection:** Play opens the launcher's window (`--show`), which is the
  picker with each game's art. Each game is also on the tile's menu as
  **Play *title***, which starts it directly the same way.
- **Eject cartridge** on the tile's menu, and under **Extensions → PC GamePak**,
  runs `pc-gamepak.exe --drive X:\ --safe-eject`. If a program is still running
  from the drive it is named, with the offer to force quit and eject. Saves and
  shader caches go back to the cartridge first, as they do from the window, and
  a Play still running on that drive closes its session before the drive goes.
  A drive Windows will only eject as administrator asks through UAC.
- **Leaves an ejected drive alone.** On a USB NVMe enclosure Windows cannot
  power the device down, so eject dismounts the volume and the drive letter
  stays. Any read would mount it again, so the slot stops looking at that drive
  from the moment Eject is chosen until the letter disappears — the cartridge
  being unplugged. **Look for a cartridge again** looks at it anyway.
- `PC_GAMEPAK_LAUNCHER` overrides where the launcher is looked for.

## What it does not do

- **Show more than one cartridge.** One slot. With two in, the lower drive
  letter wins.
- **Treat an `autorun.inf` as a cartridge.** PC GamePak's watcher accepts one,
  but plenty of ordinary drives carry it.
- **Swap the tile while it is running.** A cartridge change waits until the
  launcher Playnite started has closed, so play time is not recorded against an
  entry that has gone.
- **Time a game that is not on the cartridge.** A cartridge that points at a game
  installed elsewhere has nothing on the drive to watch, so `--play` starts it
  and exits, and Playnite sees a launch of a few seconds. The cartridge's own
  hours are closed at once rather than left open, as auto-launch does.
- **List a collection's games as separate library entries.** One slot is the
  design. The tile is recreated on every insert, so per-game Playnite entries
  would lose their play time and metadata each time anyway; the cartridge's
  `stats.json` keeps the real hours.

## Switching it on

PC GamePak's rule for every front-end plugin is that installing it does not
switch it on. In PC GamePak's settings, under **Front-ends**, turn on
**Playnite library**. That writes

```json
{ "frontends": { "playnite": true } }
```

to `%LOCALAPPDATA%\PC-GamePak\settings.json`, which is all this reads. While it
is off the slot stays out of the library and Playnite shows a notification
saying how to turn it on.

Turn the **launcher** off as well if plugging a cartridge in should only fill
the slot, rather than also open the launcher's window.

## Install

Close Playnite, then from this folder:

```powershell
.\build.ps1 -Install    # build, copy to %APPDATA%\Playnite\Extensions\PCGamePak
.\build.ps1 -Pack       # or build a .pext to drag onto Playnite
```

Needs the .NET SDK (any recent one; the .NET Framework reference assemblies come
from NuGet). No Visual Studio.

**Main menu → Extensions → PC GamePak → Look for a cartridge again** forces a
check.

## Tests

```powershell
.\build.ps1
powershell -ExecutionPolicy Bypass -File test\test_reader.ps1
```

Windows PowerShell rather than `pwsh`, because the extension is .NET Framework.
They cover reading `cartridge.conf`, art resolution and refusing paths off the
drive, the front-end switch, and the launcher's command line. The slot itself
needs Playnite and is checked by hand.

## Credit

The slot technique — one entry replaced rather than edited so Fullscreen mode
redraws it, a new file name per cover so WPF's image cache lets go, and never
leaving the entry without a play action — was worked out by PenPen in
[Playnite physical cartridge & disc](https://github.com/penpenlovesrei-dotcom/Playnite-physical-cartridge-disc).
