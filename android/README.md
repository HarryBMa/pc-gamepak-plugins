# PC GamePak on Android — design

![Status](https://img.shields.io/badge/status-design%20only-lightgrey)

Not built yet. This is the plan for the four Android front-ends people asked
for, what each can and cannot do, and what has to be checked on a real device
before any of it is written.

| Front-end | Android app | Desktop counterpart here |
|---|---|---|
| **Daijishō** | Android only | — |
| **Pegasus Frontend** | Yes | [`sync/`](../sync/) |
| **ES-DE** | Yes (paid, Play Store / Patreon) | [`sync/`](../sync/) |
| **LaunchBox** | Yes (paid) | [`launchbox/`](../launchbox/) (Big Box, design only) |

## What a cartridge can be on Android

**Only an emulated one.** A cartridge for a PC game holds a Windows or Linux
program, and Android cannot run either. A cartridge that says
`platform=SNES` (or any other system in `cartridge.conf.example`) and carries
the ROM can be played by an Android emulator. That is the whole Android
audience, and every plugin below shows only those cartridges, skipping
`platform=PC`, which is also the default when `platform=` is absent.

Plugged in over USB-C (OTG), a cartridge is a removable volume. Android shows
it to apps through the Storage Access Framework (a `content://` URI the user
grants once per volume) and, on most devices, as `/storage/<UUID>/` for apps
with "All files access". The UUID is the filesystem's, so it stays the same for
the same cartridge across plugs, and changes when the wizard reformats it.

## What is missing on Android, whichever front-end

- **The launcher.** Every desktop plugin hands Play to
  `pc-gamepak --drive <root> --play <n>`, which moves saves and counts hours.
  There is no Android build of it, and the drive layer (`core/src/drives.rs`,
  `eject.rs`) has no Android backend. So on Android the front-end starts the
  emulator directly, and **saves and playtime do not travel** unless the
  emulator is pointed at a save folder on the cartridge itself (RetroArch:
  `savefile_directory`). That is the honest first version.
- **The switch.** PC GamePak's `settings.json` does not exist on a phone.
  Android plugins have no `frontends` entry to read and are on once installed.
  They do not need an entry in `core/src/frontend.rs`, because no desktop
  settings dialog can switch them.
- **Insert and removal.** No watcher. Each front-end below notices a cartridge
  only when it rescans its library.

## Per front-end

### Pegasus (Android)

The most promising, because Pegasus reads plain text from folders it is told
about and needs no program running beside it.

- **Plan:** the wizard writes a `metadata.pegasus.txt` at the cartridge's root
  for emulated cartridges, next to `cartridge.conf`. The user adds the drive as
  a game directory in Pegasus once; from then on Pegasus lists it whenever it
  is in.
- **Launch line:** Android Pegasus takes `am start` commands with
  `{file.uri}`/`{file.path}` placeholders. The emulator to use follows from
  `platform=`, so the wizard needs a small table of platform → `am start` line
  (RetroArch core per system, or a standalone emulator).
- **To check on a device:** whether Pegasus keeps a removable drive's game
  directory across unplug and replug; which placeholder the major emulators
  accept from a USB volume (`content://` vs a `/storage/<UUID>/` path).

### ES-DE (Android)

- **Plan:** a "PC GamePak" custom system, as `sync/esde.py` writes on the
  desktop, but written once by hand (or by the wizard as a file to copy) with
  its `<path>` on the cartridge, since there is no Python on the phone to run
  `pc-gamepak-sync`. A `gamelist.xml` on the cartridge gives titles and art.
- **To check:** whether ES-DE's Android build accepts an absolute
  removable-storage path in a custom system's `<path>`, rather than only paths
  under its ROM directory; and its Android launch syntax for custom systems
  (`%EMULATOR_…%` find rules versus a literal activity).

### Daijishō

- **Plan:** Daijishō builds its library by scanning one folder per platform,
  and a platform is a JSON file listing which emulators can play it and how to
  start each (an `am start` style intent with the ROM's URI). The wizard lays an
  emulated cartridge out as `<platform>/<rom>` and can export a matching
  platform JSON. The user points that platform's folder at the cartridge once.
- **Limits:** no plugin API, so no art from `.gamepak/` unless Daijishō's own
  scraper finds it, and no cartridge title beyond the ROM's file name.
- **To check:** whether a platform's sync folder on a removable volume
  survives unplugging, and the current platform JSON schema (it has changed
  between major versions).

### LaunchBox (Android)

- **Plan:** none beyond an import. LaunchBox for Android has no plugin API; it
  imports ROM folders. The `<platform>/<rom>` layout for Daijishō serves it too.
- **To check:** whether a re-scan picks up a cartridge plugged in after the
  import, or each cartridge has to be imported once.

## Order to build it in

1. **The cartridge side, in PC GamePak:** for `platform=` other than PC, the
   wizard writes the ROM under `<platform>/`, a `metadata.pegasus.txt`, and a
   `gamelist.xml`, with the art it already has. This serves Pegasus, ES-DE,
   Daijishō and LaunchBox at once and needs no app.
2. **Pegasus**, checked on a device, since it should need nothing else.
3. **ES-DE** and **Daijishō** once the device checks above are answered.
4. **Saves and hours** only if an Android build of the core becomes worth it;
   until then they are the emulator's.
