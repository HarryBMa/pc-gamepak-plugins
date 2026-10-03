# PC GamePak for LaunchBox

A cartridge slot in LaunchBox and Big Box, as in Playnite: one game in a
**PC GamePak** platform, empty with no cartridge in and the cartridge itself
with one.

## What it does

- Checks every drive except the system drive for `cartridge.conf`, every two
  seconds, and keeps one game in the PC GamePak platform in step with what it
  finds. A cartridge plugged in or pulled while LaunchBox is open shows up, or
  goes, within two seconds.
- **The slot carries the cartridge**: its title, cover (`Box - Front`),
  background (`Fanart - Background`) and logo (`Clear Logo`), copied into
  LaunchBox's image folders so pulling the drive does not pull the pictures out
  from under it; and the **hours the cartridge has counted** — play time, play
  count and last played — which follow the drive between machines.
- **A single game**: Play runs `pc-gamepak.exe --drive X:\ --play 0`. The
  launcher has no window, carries the saves, hours and shader caches as its
  window would, and stays running until the game ends, which is what LaunchBox
  times. *Open in PC GamePak* is an additional app.
- **A collection**: Play opens the launcher's window, which is the picker with
  each game's art, and every game is also an additional app — *Play XCOM 2*,
  *Play Chimera Squad* — for starting it directly.
- **A combo drive** has a *Memory card* additional app, which opens the
  launcher on the drive's saves.
- **Eject cartridge** on the slot's menu, in LaunchBox and Big Box, runs
  `pc-gamepak.exe --drive X:\ --safe-eject`. Something still running from the
  drive is named, with the offer to force quit and eject.
- **Empty**, the slot shows the empty-slot picture, and Play opens the
  cartridge wizard.
- A cartridge change while any game is running waits until it stops, so
  LaunchBox never records play time against a slot that has been replaced.
- *Tools → PC GamePak: look for a cartridge again* re-reads an ejected drive
  that was plugged back in.

## What it does not do

- **More than one cartridge.** One slot; with two in, the lower drive letter wins.
- **The cartridge's platform.** The slot lives in the PC GamePak platform so it
  can be found; LaunchBox gives a game one platform, so `platform=SNES` is not
  shown here. (Playnite's extension does use it.)

## Switching it on

PC GamePak's rule for every plugin: off until switched on. In PC GamePak's
Settings, under **Where a cartridge opens**, switch on **LaunchBox**. Until then
the plugin keeps no slot at all. The switch is one line in
`%LOCALAPPDATA%\PC-GamePak\settings.json`:

```json
{ "frontends": { "launchbox": true } }
```

## Install

LaunchBox 13.20 or later (it runs on .NET 10). Close LaunchBox and Big Box,
then unzip the release into `LaunchBox\Plugins\`, so it ends up as
`LaunchBox\Plugins\PCGamePak\GamePakLaunchBox.dll`. Or from a checkout:

```powershell
.\build.ps1 -Install
```

## Build

Needs the .NET 10 SDK and a LaunchBox install: the plugin SDK,
`Unbroken.LaunchBox.Plugins.dll`, ships only inside LaunchBox (`Core\`) and is
not on NuGet. The project finds it under `%USERPROFILE%\LaunchBox`, or wherever
`LAUNCHBOX_DIR` says. That is also why CI does not build this one.

```powershell
.\build.ps1           # _build\
.\build.ps1 -Pack     # _build\pc-gamepak-launchbox-<version>.zip
```

Reading a cartridge, finding the launcher, watching drives and ejecting are the
Playnite extension's code, compiled in from `..\playnite\` rather than copied:
none of it knows which front-end it is in. The plugin logs to
`pc-gamepak.log` beside itself.

Tested on LaunchBox 14 against a real two-game collection cartridge: the slot
appeared with its art, hours and additional apps.
