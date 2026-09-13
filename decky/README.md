# PC GamePak for Decky

Plug a cartridge into a Steam Deck and its games appear as a row on the home
screen. No launcher window, no desktop.

A cartridge is a removable drive with a `cartridge.conf` at its root — the
format from [PC GamePak](https://github.com/HarryBMa/pc-gamepak). This plugin
reads it; it does not need PC GamePak installed.

> **Status: tested on hardware, and the home row does not work.** Run against a
> real cartridge on SteamOS's gamescope session (Steam `steamdeck_stable`, build
> 1788652215, Decky 3.2.8). The Quick Access panel and the Deck Shelves source
> both work. The home-row patch this plugin ships does **not** land on that
> build — see [The home-row patch](#the-home-row-patch-is-the-fragile-part).

## What it does

- Watches `/run/media`, `/media` and `/mnt` for a mounted cartridge.
- Reads `cartridge.conf`, both the single-game and `[collection]` forms.
- Finds the artwork, including art the wizard copied into `.gamepak/`.
- Offers the cartridge's games to [Deck Shelves](https://github.com/santojon/Deck-Shelves)
  as a shelf source, so it can put them on the home screen. This is the route
  that works; add a shelf there and pick **PC GamePak cartridge** as its source.
- Lists the same games in the Quick Access menu, each with what the *cartridge*
  remembers: hours, launches, and when and where it was last played. Those
  numbers come off the drive, not out of Steam — see [Hours](#hours).
- Optionally, and off by default, gives games the cartridge *carries* a Steam
  shortcut so they can appear too — see [Carried games](#carried-games).
- Tries to put a row on `/library/home` itself, which currently does nothing —
  see below.
- Starts a game by handing its `steam://` URI to Steam.

## What it does not do

- **Launch anything that is not a URI.** A cartridge can name a path to an
  executable on the drive. Running that needs the host, which a Decky plugin
  should not be reaching for — the PC GamePak launcher does it properly. Such a
  game also has no appid, so it cannot appear in a Deck Shelves shelf; the Quick
  Access panel still lists it.
- **Write to Steam, unless asked.** No collections, no library registration.
  The one exception is the shortcut setting below, which is off until turned on.
- **Write anywhere on the host.** The only file this plugin writes is
  `.gamepak/stats.json` on the cartridge itself, and only because you started
  a game — see below.

## Hours

A cartridge counts its own launches, in `.gamepak/stats.json` on the drive. The
PC GamePak launcher writes it on a desktop; this plugin reads it, and adds to
it, so the number follows the cartridge rather than staying on whichever machine
happened to play it. That is the whole point of keeping it on the drive, and it
only works if both ends keep it — so plugging a cartridge into a Deck shows the
hours the desktop recorded, and playing it here shows up on the desktop next
time.

**Launches, not hours, are counted here.** Steam is handed a `steam://` URI and
tells this plugin nothing about what happens next — not when the game starts,
and not when it stops — so a duration recorded from here would be invented. The
launcher is a window that stays open for the session and records those properly.
A cartridge played on a Deck gains a launch, a last-played date, and `steamdeck`
as the machine, which is the part anyone actually looks for.

It is not behind a setting, and the case for that is the same as the launcher's:
it happens because you pressed a game, it goes to the drive that game is on, and
it is that drive's own bookkeeping. A cartridge mounted read-only keeps playing
without a count.

## Carried games

A game the cartridge points at (`steam://rungameid/...`) already has an appid.
A game the cartridge *carries* (`Games/Something/Game.exe`) does not: Steam has
never heard of it, and a shelf source can only return appids. So a carried game
appears in the Quick Access panel and nowhere else.

**Add carried games to Steam** in the panel changes that. It hands each carried
game to Steam as a shortcut, which gives it an appid, and removes the shortcut
again when the cartridge goes. Only shortcuts this plugin made are ever removed.

It is off by default and that default is the point. Nothing else here touches
Steam's library or the host at all: the only thing this plugin ever writes is
the cartridge's own launch count, on the cartridge, when you start a game. It
reads a drive and draws a row, which is what makes it safe to plug in a
cartridge somebody handed you.

## Windows games and exFAT

Measured on the hardware above: a Windows game will not start from an exFAT
cartridge, and the error Steam shows — "Disk write error", `AppError_11` — says
nothing about why.

**Steam installs a compatibility tool into the library the game lives in.** So
launching a cartridge game whose Proton the host does not have makes Steam try
to unpack Proton *onto the cartridge*. Proton contains 1892 symlinks, exFAT has
none, and the first one ends it — `files/bin/msidb -> wine`, the exact path in
the error. Steam's own `compat_log.txt` names the syscall:
`os.symlink(...)` → `PermissionError: [Errno 1] Operation not permitted`.

**Naming a Proton the host already has is the whole fix.** With the
compatibility tool set to an installed Proton, Steam has no tool to install, the
prefix lands beside that Proton rather than on the cartridge, and the game runs
from the cartridge unchanged. A `STEAM_COMPAT_DATA_PATH` override is *not*
needed — tested with launch options cleared, and it still works.

That is what the shortcut setting does for carried games. For games the
cartridge only points at, it is one field in Steam's per-game properties.

### The better answer: do not use exFAT

The cartridge filesystem is the real cause, and NTFS removes it. Tested with the
kernel `ntfs3` driver on a volume automounted by udisks exactly as a cartridge
would be — `/run/media/$USER/...`, `uid=1000`, no root:

| | exFAT | NTFS (`ntfs3`) |
|---|---|---|
| Symlinks | **no** | yes |
| `chmod` persists | no | yes |
| Executable bit | no | yes |
| Hardlinks | no | yes |
| Holds a Proton install | **no** | yes — all 1892 symlinks |
| Readable on Windows | yes | yes, natively |

An NTFS cartridge needs no per-game settings at all: Steam can install Proton
onto it like any other drive. Native Linux games and btrfs cartridges were never
affected.
- **Eject.** Same reason.

## What is verified

| | |
|---|---|
| `cartridges.py` — parsing, art resolution, mount scanning, the stats file | **30 tests, passing.** `python test/test_cartridges.py` |
| `main.py` — the Decky wrapper | **Runs.** Loads, and reports `cartridges changed` as a drive comes and goes |
| Deck Shelves source | **Works.** Resolves 9 appids from a ten-game cartridge, 0 after eject, 9 again on reinsert |
| Quick Access panel | **Works.** |
| The home-row patch in `src/CartridgeShelf.tsx` | **Does not land.** Registered, never applied — see below |

The split is deliberate: everything that could be tested without hardware was
put where it could be.

## The home-row patch is the fragile part

Steam's home page is not a public API. `CartridgeShelf.patch` reaches into its
React tree, and a client update can move what it reaches for.

Two rules in that code, both load-bearing:

1. **It never throws.** A patch that throws takes the home page down, and
   somebody whose library will not render cannot get to the menu to disable the
   plugin. Failure means the row is absent, not that Steam is broken.
2. **It never replaces.** The original children are always returned and the
   shelf is prepended.

**On the Deck client this was measured against, it does not land at all.** Decky
accepts the patch — `/library/home` is in its `_routePatches` — and then leaves
it sitting in `toReplace`, having never found a route to apply it to. No
`[pc-gamepak]` line appears anywhere, because the patch function is never
called. Deck Shelves injects fine on the same build, which is why the shelf
source above is the supported route and this is kept only as a fallback for
builds where it does work.

If the row does not appear, the Quick Access panel still works, and
`console` in CEF debugging will have a `[pc-gamepak]` line if the patch ran and
found nothing to attach to.

## Switching it off from PC GamePak

If [PC GamePak](https://github.com/HarryBMa/pc-gamepak) is also installed, its
settings decide which front-ends handle a cartridge — its own launcher window,
this row, or both. Turn **Steam Deck row** off there and this plugin offers
nothing: no row, no shelf source, no panel entries. Turn it on and the launcher
stops opening a window over the top of it.

That is one boolean in one file, `~/.local/state/pc-gamepak/settings.json`:

```json
{ "frontends": { "launcher": false, "decky": true } }
```

Read on every scan, so a change takes effect without restarting Decky. **Absent,
unreadable, or silent about this plugin all mean on** — the plugin does not need
PC GamePak installed, and refusing to work until a program you do not have says
it may would be absurd. The file can only ever switch it off, and only by saying
so outright.

## Install

Not in the Decky store. Build it and copy it over, from this `decky/` folder:

```bash
pnpm install
pnpm run build
```

Then put this folder on the Deck as `~/homebrew/plugins/pc-gamepak-decky` —
that name, not `decky`, because it is where PC GamePak's settings look to tell
whether the plugin is installed — and restart Decky.

## Tests

From this `decky/` folder:

```bash
python test/test_cartridges.py     # 30 tests, no dependencies
pnpm run typecheck                 # needs node_modules
```

## Why a plugin rather than the launcher

The PC GamePak launcher is a window: it opens on insert, shows the cover art,
and waits for Play. That is right on a desktop and wrong on a console, where
anything that is not the Steam UI is a mode you have to escape from.

Same cartridges, same format, same artwork. A row instead of a window.

## Licence

MIT, matching PC GamePak.
