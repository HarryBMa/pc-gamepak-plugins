# PC GamePak plugins

Front-ends for [PC GamePak](https://github.com/HarryBMa/pc-gamepak) cartridges
that live inside somebody else's program. The launcher that ships with PC
GamePak is one front-end; these put the same cartridge where people already
look.

| Folder | Front-end | What a cartridge becomes | Status |
|---|---|---|---|
| [`decky/`](decky/) | Steam Deck, through Decky Loader | A Deck Shelves shelf source and a Quick Access list; its own home-row patch does not land on current Steam | Run on a Deck: shelf source and panel work |
| [`playnite/`](playnite/) | Playnite, on Windows | The first tile in the library; Play starts the game through the launcher with no window, Eject on its menu | Run end to end against a real cartridge |

Each folder is a complete project with its own build, tests and README. They
share no code: one is Python and TypeScript inside Steam, the other C# inside
Playnite.

## What they share

**The cartridge format.** A drive with a `cartridge.conf` at its root, single
game or `[collection]` + `[game]`, with artwork beside it or in `.gamepak/`.
Both read it the way the launcher does, including refusing any art path that
leaves the drive.

**The switch.** PC GamePak's settings file holds one boolean per front-end:

```json
{ "frontends": { "launcher": false, "playnite": true } }
```

`%LOCALAPPDATA%\PC-GamePak\settings.json` on Windows,
`~/.local/state/pc-gamepak/settings.json` elsewhere. The launcher's settings
dialog writes it; a plugin reads it — the Playnite extension does, the Decky
plugin does not yet and draws its row whatever the file says. The rule is PC GamePak's
(`core/src/frontend.rs`): the launcher is on unless switched off, every plugin
is off unless switched on, and more than one may be on at once.

| Id | Plugin | Where PC GamePak looks for it |
|---|---|---|
| `decky` | `decky/` | `~/homebrew/plugins/pc-gamepak-decky` |
| `playnite` | `playnite/` | `%APPDATA%\Playnite\Extensions\PCGamePak` |

That path is how the settings dialog knows a plugin is installed, so install
each under that name.

## Adding one

A new front-end is a new folder here and a new entry in PC GamePak's
`frontend.rs` register: an id, a name, and where it installs. Keep the contract
that small — read the file, read the drive, hand anything that needs the host
to the launcher.

## Licence

MIT, matching PC GamePak.
