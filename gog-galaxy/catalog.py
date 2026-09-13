"""What the GOG Galaxy integration knows, without Galaxy.

Galaxy's model is a library of owned games, some of which are installed. A
cartridge maps onto it naturally: every game ever seen on a cartridge stays
owned — remembered in the integration's persistent cache — and is installed
exactly while a cartridge carrying it is plugged in. Pull the drive and the
game greys out rather than vanishing, which is what a shelf of cartridges looks
like.

Kept apart from `plugin.py` so it can be tested without Galaxy's API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from gamepak.cartridge import Cartridge

FRONTEND_ID = "gog_galaxy"


class Changes:
    def __init__(self):
        self.added = []  # type: List[Tuple[str, str]]
        self.installed = []  # type: List[str]
        self.uninstalled = []  # type: List[str]

    def __bool__(self) -> bool:
        return bool(self.added or self.installed or self.uninstalled)


class Catalog:
    def __init__(self, owned: Optional[Dict[str, str]] = None):
        # game id -> title, for every game ever seen on a cartridge.
        self.owned = dict(owned or {})
        # game id -> (cartridge root, launcher game number), for what is in now.
        self.present = {}  # type: Dict[str, Tuple[Path, int]]

    @classmethod
    def from_cache(cls, text: Optional[str]) -> "Catalog":
        try:
            owned = json.loads(text) if text else {}
        except ValueError:
            owned = {}
        if not isinstance(owned, dict):
            owned = {}
        return cls({str(k): str(v) for k, v in owned.items()})

    def to_cache(self) -> str:
        return json.dumps(self.owned, sort_keys=True)

    def refresh(self, cartridges: List[Cartridge]) -> Changes:
        """Take in what is plugged in now, and say what Galaxy must be told."""
        changes = Changes()
        present = {}  # type: Dict[str, Tuple[Path, int]]
        for cartridge in cartridges:
            for game in cartridge.playable_games:
                # The first cartridge found wins a game carried on two at once.
                present.setdefault(game.key, (cartridge.root, game.index))
                if game.key not in self.owned or self.owned[game.key] != game.title:
                    if game.key not in self.owned:
                        changes.added.append((game.key, game.title))
                    self.owned[game.key] = game.title

        before = set(self.present)  # type: Set[str]
        after = set(present)
        changes.installed = sorted(after - before)
        changes.uninstalled = sorted(before - after)
        self.present = present
        return changes

    def location(self, game_id: str) -> Optional[Tuple[Path, int]]:
        return self.present.get(game_id)

    def is_installed(self, game_id: str) -> bool:
        return game_id in self.present
