# pc-gamepak-sync — Heroic, Pegasus and ES-DE

![Status](https://img.shields.io/badge/status-tested%20against%20file%20formats-yellow)
[![Release](https://img.shields.io/github/v/release/HarryBMa/pc-gamepak-plugins?filter=sync-v*&display_name=tag&label=release)](https://github.com/HarryBMa/pc-gamepak-plugins/releases?q=sync-v)

Three front-ends that read files instead of loading plugins, kept in step with
the PC GamePak cartridges plugged in. One small program watches the drives and
writes each front-end's own files while a cartridge is in, then takes its
entries out again when the cartridge goes.

| Front-end | What a cartridge becomes | Where it writes |
|---|---|---|
| **Heroic Games Launcher** | Sideloaded games | `heroic/sideload_apps/library.json` — only entries whose `app_name` starts `pcgamepak-` |
| **Pegasus Frontend** | A "PC GamePak" collection | `pegasus-frontend/pc-gamepak/metadata.pegasus.txt`, plus that folder added to `game_dirs.txt` once |
| **ES-DE** | A "PC GamePak" system | `ES-DE/custom_systems/es_systems.xml` (its own `<system>` only), `gamelists/pcgamepak/`, `downloaded_media/pcgamepak/` |

Every game is started through the launcher — `pc-gamepak --drive <root> --play <n>`
— by a small launch script per game, so saves, hours and shader caches travel
with the cartridge exactly as they do from the launcher's window. That needs a
PC GamePak new enough to have `--play`.

> **Status:** tested against each front-end's documented file format, with
> fixtures, on Windows and Linux in CI. **Not yet run against the real
> applications.** Heroic, Pegasus and ES-DE all read these files at start, so a
> cartridge plugged in while one is running shows up on its next start.

## Switching front-ends on

PC GamePak's rule: installed is not on. Each front-end is synced only when PC
GamePak's `settings.json` says so:

```json
{ "frontends": { "heroic": true, "pegasus": true, "esde": true } }
```

`--frontend heroic` syncs one regardless, for trying it out. Switching one off
takes its entries out on the next look.

## Run it

```sh
python pc-gamepak-sync-0.1.0.pyz --list    # what is plugged in, what is on, what is installed
python pc-gamepak-sync-0.1.0.pyz --once    # sync once
python pc-gamepak-sync-0.1.0.pyz           # keep watching, every two seconds
```

From a checkout: `python -m pc_gamepak_sync` inside `sync/`. Python 3.8 or later,
standard library only.

### In the background

**Linux** — a user service, `pc-gamepak-sync.service` in this folder:

```sh
install -Dm644 pc-gamepak-sync.service ~/.config/systemd/user/pc-gamepak-sync.service
install -Dm644 pc-gamepak-sync-0.1.0.pyz ~/.local/share/pc-gamepak/pc-gamepak-sync.pyz
systemctl --user enable --now pc-gamepak-sync
```

**Windows** — a task at logon:

```powershell
$pyz = "$env:LOCALAPPDATA\PC-GamePak\pc-gamepak-sync.pyz"
Register-ScheduledTask -TaskName "PC GamePak sync" -Trigger (New-ScheduledTaskTrigger -AtLogOn) `
  -Action (New-ScheduledTaskAction -Execute "pythonw.exe" -Argument "`"$pyz`"")
```

## Tests

```sh
python -m unittest discover -s sync/tests      # from the repository root
```
