# PC GamePak plugins

[![CI](https://img.shields.io/github/actions/workflow/status/HarryBMa/pc-gamepak-plugins/ci.yml?branch=main&label=CI)](https://github.com/HarryBMa/pc-gamepak-plugins/actions/workflows/ci.yml)
[![Licence](https://img.shields.io/github/license/HarryBMa/pc-gamepak-plugins)](LICENSE)
[![Downloads](https://img.shields.io/github/downloads/HarryBMa/pc-gamepak-plugins/total)](https://github.com/HarryBMa/pc-gamepak-plugins/releases)
[![PC GamePak](https://img.shields.io/github/v/release/HarryBMa/pc-gamepak?label=PC%20GamePak)](https://github.com/HarryBMa/pc-gamepak/releases)

Front-ends for [PC GamePak](https://github.com/HarryBMa/pc-gamepak) cartridges
that live inside somebody else's program. The launcher that ships with PC
GamePak is one front-end; these put the same cartridge where people already
look.

| Folder | Front-end | What a cartridge becomes | Release | Status |
|---|---|---|---|---|
| [`decky/`](decky/) | Steam Deck, through Decky Loader | A Deck Shelves shelf source and a Quick Access list | [![Decky](https://img.shields.io/github/v/release/HarryBMa/pc-gamepak-plugins?filter=decky-v*&display_name=tag&label=decky)](https://github.com/HarryBMa/pc-gamepak-plugins/releases?q=decky-v) | ![Status](https://img.shields.io/badge/run%20on%20a%20Deck-shelf%20%26%20panel%20work-green) |
| [`playnite/`](playnite/) | Playnite, on Windows | The first tile in the library; Play through the launcher with no window, Eject on its menu | [![Playnite](https://img.shields.io/github/v/release/HarryBMa/pc-gamepak-plugins?filter=playnite-v*&display_name=tag&label=playnite)](https://github.com/HarryBMa/pc-gamepak-plugins/releases?q=playnite-v) | ![Status](https://img.shields.io/badge/run%20end%20to%20end-real%20cartridge-brightgreen) |
| [`gog-galaxy/`](gog-galaxy/) | GOG Galaxy 2.0 | Owned games, installed while the cartridge is in | [![Galaxy](https://img.shields.io/github/v/release/HarryBMa/pc-gamepak-plugins?filter=galaxy-v*&display_name=tag&label=galaxy)](https://github.com/HarryBMa/pc-gamepak-plugins/releases?q=galaxy-v) | ![Status](https://img.shields.io/badge/tested-in%20the%20Galaxy%20client-brightgreen) |
| [`sync/`](sync/) | Heroic, Pegasus, ES-DE | Sideloaded games / a collection / a system, while the cartridge is in | [![Sync](https://img.shields.io/github/v/release/HarryBMa/pc-gamepak-plugins?filter=sync-v*&display_name=tag&label=sync)](https://github.com/HarryBMa/pc-gamepak-plugins/releases?q=sync-v) | ![Status](https://img.shields.io/badge/tested-in%20all%20three%20apps-brightgreen) |
| [`launchbox/`](launchbox/) | LaunchBox / Big Box | A cartridge slot, as in Playnite | — | ![Status](https://img.shields.io/badge/status-design%20only-lightgrey) |

## What works

Tested against a real cartridge — FTL, a Steam game — in each application.

| Front-end | Plays a cartridge | Notices insert and removal while running | Eject from inside it | Reads cartridges |
|---|---|---|---|---|
| **Playnite** | ✅ through the launcher, timed by Playnite | ✅ within two seconds; the slot fills and empties | ✅ on the slot's menu | Live |
| **GOG Galaxy** | ✅ through the launcher; shows Running until the game exits | ✅ within two seconds; games grey out and come back | — | Live |
| **Decky** (Steam Deck) | ✅ handed to Steam as a URI | ✅ within two seconds | — | Live |
| **Heroic** | ✅ through the launcher | ⚠️ `pc-gamepak-sync` updates its library within two seconds; Heroic shows it on a manual library refresh. A pulled cartridge's games show as not installed until Heroic closes, then go | — | On refresh |
| **Pegasus** | ✅ through the launcher | ❌ updated live on disk, read at start | — | At start |
| **ES-DE** | ✅ through the launcher | ❌ updated live on disk, read at start | — | At start |
| **LaunchBox** | Not built | — | — | — |

"On refresh" and "at start" mean a cartridge plugged in or pulled while the
front-end is open shows up, or goes, when you refresh its library (Heroic) or
the next time it starts (Pegasus, ES-DE). Until then a pulled cartridge's game
stays on screen, and pressing Play on it puts up a message saying to plug the
cartridge in rather than doing nothing. Eject anywhere else is the launcher's
own, or Windows's.

Decky is the one that plays without the launcher: Steam starts the game, so
the cartridge counts the launch but not the hours.

Each folder has its own build, tests and README. The Python ones —
`gog-galaxy/` and `sync/` — share [`common/gamepak`](common/gamepak): one
cartridge reader, and one way of asking PC GamePak to play and eject. Decky keeps
its own reader, because it has to install as a single folder on a Deck; the
Playnite extension is C#.

## What they share

**The cartridge format.** A drive with a `cartridge.conf` at its root, single
game or `[collection]` + `[game]`, with artwork beside it or in `.gamepak/`.
Every plugin reads it the way the launcher does, numbers a collection's games
the way `pc-gamepak --play <n>` does, and refuses any art path that leaves the
drive.

**The launcher does the launching.** Wherever a plugin can run a program it
runs `pc-gamepak --drive <root> --play <n>`, which carries saves, hours and
shader caches with the cartridge and stays up while the game runs, so the
front-end can time it. Decky is the exception: it hands Steam a URI.

**The switch.** PC GamePak's settings file holds one boolean per front-end:

```json
{ "frontends": { "launcher": false, "playnite": true, "heroic": true } }
```

`%LOCALAPPDATA%\PC-GamePak\settings.json` on Windows,
`~/.local/state/pc-gamepak/settings.json` elsewhere. The launcher's settings
dialog writes it; plugins read it. The rule is PC GamePak's
(`core/src/frontend.rs`): the launcher is on unless switched off, every plugin
is off unless switched on, and more than one may be on at once. Decky bends it:
it is sold as needing nothing else installed, so a missing, unreadable or silent
settings file leaves it on, and only `"decky": false` switches it off.

| Id | Plugin | Where it installs |
|---|---|---|
| `decky` | `decky/` | `~/homebrew/plugins/pc-gamepak-decky` |
| `playnite` | `playnite/` | `%APPDATA%\Playnite\Extensions\PCGamePak` |
| `gog_galaxy` | `gog-galaxy/` | `%LOCALAPPDATA%\GOG.com\Galaxy\plugins\installed\pc-gamepak-galaxy` |
| `heroic`, `pegasus`, `esde` | `sync/` | wherever `pc-gamepak-sync` runs from |
| `launchbox` | `launchbox/` | `LaunchBox\Plugins\PCGamePak` (planned) |

Every id is in PC GamePak's register — `launchbox` marked not built — once
[HarryBMa/pc-gamepak#24](https://github.com/HarryBMa/pc-gamepak/pull/24) is in,
so each gets a switch under **Front-ends** in its settings dialog. Before that,
the new ones are switched on by hand in `settings.json`.

## Releases

Each plugin is released on its own tag — `playnite-v0.1`, `decky-v0.1.0`,
`galaxy-v0.1.0`, `sync-v0.1.0` — and the release workflow refuses a tag that
does not match the version the plugin declares. Every push builds and tests all
of them on Windows and Linux, and keeps the packages as workflow artifacts.

```sh
python tools/package.py decky|galaxy|sync     # dist/
pwsh playnite/build.ps1 -Pack                 # playnite/_build/*.pext
```

## Adding one

A new front-end is a new folder here and a new entry in PC GamePak's
`frontend.rs` register: an id, a name, and where it installs. Keep the contract
that small — read the switch, read the drive, and hand anything that needs the
host to the launcher.

## Licence

MIT, matching PC GamePak.
