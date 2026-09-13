# PC GamePak for LaunchBox — design

![Status](https://img.shields.io/badge/status-design%20only-lightgrey)

Not built yet. This is the plan, and what is missing to build it.

## What it would do

The same thing the Playnite extension does, in LaunchBox and Big Box: a
cartridge slot as the first game of a "PC GamePak" platform, empty with no
cartridge in, the cartridge's art with one, Play through the launcher, and
Eject on the game's menu.

## How, in LaunchBox's plugin API

LaunchBox loads .NET plugins from `LaunchBox\Plugins\`, written against
`Unbroken.LaunchBox.Plugins.dll`.

| Need | API |
|---|---|
| Start watching once LaunchBox or Big Box is up | `ISystemEventsPlugin.OnEventRaised` — `LaunchBoxStartupCompleted` / `BigBoxStartupCompleted` |
| The slot entry | `PluginHelper.DataManager.AddNewGame(title)` in a platform added with `AddNewPlatform`, then `Save(true)` |
| Play | `IGame.ApplicationPath` = the launcher, `IGame.CommandLine` = `--drive X:\ --play 0` (or `--show` for a collection) |
| Cover and background | LaunchBox reads images from `Images\<Platform>\Box - Front\` and `Fanart - Background\`, named after the game's title — copied there, not set on the game |
| Eject | `IGameMenuItemPlugin` — a menu item on the slot game, running `pc-gamepak --safe-eject` |
| The switch | `{"frontends": {"launchbox": true}}` in PC GamePak's settings, as every plugin here |

The Playnite extension's `CartridgeReader`, `GamePakInstall` and `Ejector` are
plain C# with no Playnite types, and would be shared rather than rewritten.

## What is missing

**`Unbroken.LaunchBox.Plugins.dll`.** It ships only inside a LaunchBox install
(`LaunchBox\Core\`), is not on NuGet, and LaunchBox is not installed on the
machine this was written on. Code written against the documentation alone
could not be compiled or checked, so it has not been written.

To pick this up: install LaunchBox, reference the DLL the way
`playnite/GamePakShelf.csproj` references Playnite's SDK — from the local
install when present — and check the image-folder naming against a real
install before trusting the table above.
