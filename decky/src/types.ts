/** Artwork, already inlined as data URIs by the backend. */
export interface Art {
  cover?: string;
  background?: string;
  logo?: string;
  icon?: string;
}

export interface Game {
  title: string;
  executable: string;
  art: Art;
}

export interface Cartridge {
  /** Filesystem UUID where one is available, otherwise the mount's basename. */
  id: string;
  title: string;
  mount: string;
  art: Art;
  games: Game[];
}
