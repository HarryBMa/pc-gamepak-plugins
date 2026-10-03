"""Shared by every PC GamePak front-end that runs Python: reading cartridges,
and asking an installed PC GamePak to play and eject them."""

from .cartridge import Cartridge, Game, read_cartridge, resolve_art, scan  # noqa: F401
from . import install  # noqa: F401
