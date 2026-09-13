# PC GamePak for GOG Galaxy

![Status](https://img.shields.io/badge/status-tested%20against%20the%20Galaxy%20API-yellow)
[![Release](https://img.shields.io/github/v/release/HarryBMa/pc-gamepak-plugins?filter=galaxy-v*&display_name=tag&label=release)](https://github.com/HarryBMa/pc-gamepak-plugins/releases?q=galaxy-v)

PC GamePak cartridges as a GOG Galaxy 2.0 integration.

- A game is **owned** from the first time a cartridge carrying it is plugged in,
  and stays in the library after.
- It is **installed** exactly while that cartridge is in. Pull the drive and the
  game greys out; plug it back in and it lights up again.
- **Play** runs `pc-gamepak --drive <root> --play <n>`, so saves, hours and
  shader caches travel with the cartridge, and Galaxy shows the game as running
  until the launcher exits — which is when the game does.
- Nothing to log in to: the integration connects with a local account.

It uses Galaxy's `generic` platform, and needs PC GamePak installed, new enough
to have `--play`.

> **Status:** tested with the real `galaxy.plugin.api` 0.71 — owned and local
> games, launch, running-until-exit and unplugging — and the packaged release
> loads under GOG Galaxy's own embedded Python and finds a real cartridge.
> **Not yet connected inside the Galaxy client.**

## Switching it on

Off until PC GamePak's settings say otherwise:

```json
{ "frontends": { "gog_galaxy": true } }
```

Switched off, every game stays owned but none is installed.

## Install

1. Download `pc-gamepak-galaxy-<version>.zip` from the releases.
2. Unzip it into `%LOCALAPPDATA%\GOG.com\Galaxy\plugins\installed\`, so that
   `pc-gamepak-galaxy\manifest.json` is inside that folder.
3. Restart Galaxy, then **Settings → Add games & friends → Connect gaming
   accounts → PC GamePak → Connect**.

The release carries `galaxy.plugin.api` and its dependencies, built for Galaxy's
64-bit Python 3.13 (`python tools/package.py galaxy`).

## Tests

```sh
pip install -r gog-galaxy/requirements.txt
python -m unittest discover -s gog-galaxy/tests
```

The catalog tests need nothing; the plugin tests are skipped without the API.
