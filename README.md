# PC GamePak plugins

[![CI](https://img.shields.io/github/actions/workflow/status/HarryBMa/pc-gamepak-plugins/ci.yml?branch=main&label=CI)](https://github.com/HarryBMa/pc-gamepak-plugins/actions/workflows/ci.yml)
[![Licence](https://img.shields.io/github/license/HarryBMa/pc-gamepak-plugins)](LICENSE)

[PC GamePak](https://github.com/HarryBMa/pc-gamepak) cartridges inside the
front-end you already use. Plug a cartridge in and its games show up there;
pull it out and they go.

| Plugin | For | Download | Installs to |
|---|---|---|---|
| [`decky/`](decky/) | Steam Deck (Decky Loader) | [decky](https://github.com/HarryBMa/pc-gamepak-plugins/releases?q=decky-v) | `~/homebrew/plugins/pc-gamepak-decky` |
| [`playnite/`](playnite/) | Playnite | [playnite](https://github.com/HarryBMa/pc-gamepak-plugins/releases?q=playnite-v) | open the `.pext` |
| [`launchbox/`](launchbox/) | LaunchBox / Big Box | [launchbox](https://github.com/HarryBMa/pc-gamepak-plugins/releases?q=launchbox-v) | `LaunchBox\Plugins\PCGamePak` |
| [`gog-galaxy/`](gog-galaxy/) | GOG Galaxy 2.0 | [galaxy](https://github.com/HarryBMa/pc-gamepak-plugins/releases?q=galaxy-v) | `%LOCALAPPDATA%\GOG.com\Galaxy\plugins\installed\pc-gamepak-galaxy` |
| [`sync/`](sync/) | Heroic, Pegasus, ES-DE | [sync](https://github.com/HarryBMa/pc-gamepak-plugins/releases?q=sync-v) | run `python pc-gamepak-sync.pyz` |

Each folder's README has the details.

## Steam Deck

The full set, as used on a Deck:

1. **PC GamePak** for Decky (this repo's `decky/`).
2. [**Deck Shelves**](https://github.com/santojon/Deck-Shelves), which shows
   the cartridge in the slot as a shelf on the home screen.
3. **Add Non Steam Games**, so the games a cartridge carries get a Steam
   shortcut Deck Shelves can show.

A script to add the Non-Steam Games shortcut to Deck Shelves automatically is
in progress.

## Turning one on

Every plugin except Decky is off until switched on in PC GamePak's settings
(**Front-ends**), which writes:

```json
{ "frontends": { "launcher": false, "playnite": true } }
```

`%LOCALAPPDATA%\PC-GamePak\settings.json` on Windows,
`~/.local/state/pc-gamepak/settings.json` elsewhere. Decky is on unless set to
`"decky": false`, so it works without PC GamePak installed.

## Building

```sh
python tools/package.py decky|galaxy|sync     # dist/  (decky: `pnpm run build` in decky/ first)
pwsh playnite/build.ps1 -Pack                 # playnite/_build/*.pext
pwsh launchbox/build.ps1 -Pack                # needs a LaunchBox install for its plugin SDK
```

Each plugin is released on its own tag (`decky-v0.2.0`, `playnite-v0.1`, …),
which must match the version the plugin declares.

## Licence

MIT, matching PC GamePak.
