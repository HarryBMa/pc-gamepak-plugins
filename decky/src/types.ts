/** Artwork, already inlined as data URIs by the backend. */
export interface Art {
  cover?: string;
  background?: string;
  logo?: string;
  icon?: string;
}

/**
 * What the cartridge itself remembers, summed over every machine that has
 * played it — read from `.gamepak/stats.json` on the drive, not from this
 * Deck. Empty for a game nobody has started yet.
 */
export interface GameStats {
  title?: string;
  launches?: number;
  seconds?: number;
  firstPlayed?: number;
  lastPlayed?: number;
  lastHost?: string;
}

export interface Game {
  title: string;
  executable: string;
  art: Art;
  stats?: GameStats;
}

export interface Cartridge {
  /** Filesystem UUID where one is available, otherwise the mount's basename. */
  id: string;
  title: string;
  mount: string;
  art: Art;
  games: Game[];
}
