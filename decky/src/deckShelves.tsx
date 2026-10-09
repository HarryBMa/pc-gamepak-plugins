import { callable } from "@decky/api";
import {
  register,
  type DeckShelvesPublicAPI,
  type PublicShelfSource,
  type StatisticsEntry,
} from "@deck-shelves/api";

import { ownedAppIds, ownedByExe } from "./shortcuts";

/**
 * Offer the cartridge's games to Deck Shelves: a shelf source, the cartridge's
 * own hours and estimates as metadata and statistics, and a widget.
 *
 * Why this exists alongside the home-row patch: the patch reaches into Steam's
 * own React tree, which is not a public API, and on the Steam Deck client it
 * was measured against (steamdeck_stable, build 1788652215) it does not land at
 * all — Decky registers the patch and then leaves `/library/home` sitting in
 * its `toReplace` map, never finding a route to apply it to. Deck Shelves is
 * injecting successfully on that same build, so the row it draws is a better
 * bet than the row we draw ourselves.
 *
 * This is also less code doing less: Deck Shelves owns placement, focus,
 * artwork and the context menu, and asks us only for a list of appids.
 *
 * A cartridge naming a path rather than a `steam://` URI has no appid of its
 * own. If the user has turned on "Add carried games to Steam", those games have
 * a shortcut, and a shortcut has an appid — so they are folded in here too.
 * Without that the setting would add shortcuts to the library and still leave
 * the shelf empty, which is most of the way to useless.
 *
 * Every number here is the cartridge's, summed over every machine that has
 * played it — not Steam's figure for this Deck. That is the point of showing
 * them: Steam already shows its own.
 */

/** Appids on the cartridges. Cheap: no artwork crosses the bridge. */
const getAppIds = callable<[], number[]>("get_app_ids");
const getSerial = callable<[], number>("get_serial");

interface Fact {
  cartridge: string;
  title: string;
  platform: string;
  appid: number | null;
  exe: string | null;
  seconds: number;
  launches: number;
  lastPlayed: number | null;
  howLong: { main?: number; extra?: number; complete?: number };
}
const getGameFacts = callable<[], Fact[]>("get_game_facts");

const SOURCE_ID = "pc-gamepak/cartridge";
/** How often to ask whether a cartridge went in or came out. */
const POLL_MS = 2000;
/** Hours change while a cartridge stays in; re-read them this often anyway. */
const FACTS_EVERY_TICKS = 15;

/** The cartridge's facts, by the appid Deck Shelves will ask about. */
let facts = new Map<number, Fact>();
/** Everything plugged in, including games with no appid, for the totals. */
let allFacts: Fact[] = [];

async function loadFacts(): Promise<void> {
  try {
    const [found, owned] = await Promise.all([getGameFacts(), ownedByExe()]);
    const next = new Map<number, Fact>();
    for (const fact of found) {
      const appid = fact.appid ?? (fact.exe ? owned[fact.exe] : undefined);
      if (typeof appid === "number" && appid > 0) next.set(appid, fact);
    }
    facts = next;
    allFacts = found;
  } catch (error) {
    console.error("[pc-gamepak] could not read the cartridges' facts", error);
  }
}

/** Whether a shelf draws from our source, directly or inside a composite. */
export function usesCartridgeSource(source: PublicShelfSource): boolean {
  if (source.type === "external") return source.sourceId === SOURCE_ID;
  if (source.type === "composite") return source.sources.some(usesCartridgeSource);
  return false;
}

/** "12.5 h", "40 min", "—". */
export function formatSeconds(seconds: number): string {
  if (!seconds) return "—";
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))} min`;
  return `${Math.round((seconds / 3600) * 10) / 10} h`;
}

/**
 * Re-resolve every shelf showing cartridge games when a cartridge goes in or
 * comes out, rather than leaving a pulled game on screen until the user
 * refreshes by hand. Returns the function that stops watching.
 */
function watchForChanges(api: DeckShelvesPublicAPI): () => void {
  let seen: number | null = null;
  let ticks = 0;
  let live = true;

  const tick = async () => {
    try {
      const serial = await getSerial();
      if (!live) return;
      ticks += 1;
      const changed = seen !== null && serial !== seen;
      if (seen === null || changed || ticks % FACTS_EVERY_TICKS === 0) {
        await loadFacts();
      }
      seen = serial;
      if (!changed) return;
      for (const shelf of api.getShelves()) {
        if (usesCartridgeSource(shelf.source)) api.refreshShelf(shelf.id);
      }
    } catch (error) {
      console.error("[pc-gamepak] could not check for cartridge changes", error);
    }
  };

  void tick();
  const timer = window.setInterval(tick, POLL_MS);
  return () => {
    live = false;
    window.clearInterval(timer);
  };
}

/** The widget: what is in the slot, and how long it has been played. */
function CartridgeWidget() {
  const first = allFacts[0];
  const cartridges = new Set(allFacts.map((fact) => fact.cartridge));
  const seconds = allFacts.reduce((sum, fact) => sum + fact.seconds, 0);
  const main = allFacts.length === 1 ? first?.howLong.main : undefined;

  let title = "No cartridge";
  let line = "Plug one in to play it here.";
  if (first) {
    title = cartridges.size === 1 ? first.cartridge : `${cartridges.size} cartridges`;
    const parts = [
      allFacts.length > 1 ? `${allFacts.length} games` : first.platform,
      `${formatSeconds(seconds)} played`,
    ];
    if (main) parts.push(`main story ${formatSeconds(main)}`);
    line = parts.join(" · ");
  }

  return (
    <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ fontSize: 11, letterSpacing: "0.08em", opacity: 0.6, textTransform: "uppercase" }}>
        PC GamePak
      </div>
      <div style={{ fontSize: 18, fontWeight: 600 }}>{title}</div>
      <div style={{ fontSize: 13, opacity: 0.8 }}>{line}</div>
    </div>
  );
}

export function offerCartridgesToDeckShelves(): () => void {
  let stopWatching: (() => void) | null = null;

  return register({
    name: "pc-gamepak",
    version: "0.2.0",
    onMount(api) {
      api.registerShelfSource({
        id: SOURCE_ID,
        label: "Cartridge",
        displayName: "PC GamePak cartridge",
        async resolve(limit: number): Promise<number[]> {
          try {
            const fromUris = await getAppIds();
            const fromShortcuts = await ownedAppIds();
            const all = [...fromUris, ...fromShortcuts.filter((id) => !fromUris.includes(id))];
            return all.slice(0, limit);
          } catch (error) {
            // Returning nothing empties the shelf, which is the honest answer
            // when the backend cannot say what is plugged in. Throwing here
            // would be Deck Shelves' problem rather than ours.
            console.error("[pc-gamepak] could not list appids for the shelf", error);
            return [];
          }
        },
      });

      // Per game, for whatever Deck Shelves chooses to show on a card, sort
      // by or filter on. Only games on a cartridge get an entry.
      api.registerMetadataProvider({
        id: "pc-gamepak/cartridge-facts",
        displayName: "PC GamePak cartridge",
        fields: [
          "cartridge",
          "platform",
          "playtimeSeconds",
          "launches",
          "lastPlayed",
          "hltbMainSeconds",
          "hltbExtraSeconds",
          "hltbCompleteSeconds",
        ],
        async resolve(appids) {
          const out: Record<number, Record<string, unknown>> = {};
          for (const appid of appids) {
            const fact = facts.get(appid);
            if (!fact) continue;
            out[appid] = {
              cartridge: fact.cartridge,
              platform: fact.platform,
              playtimeSeconds: fact.seconds,
              launches: fact.launches,
              lastPlayed: fact.lastPlayed,
              hltbMainSeconds: fact.howLong.main ?? null,
              hltbExtraSeconds: fact.howLong.extra ?? null,
              hltbCompleteSeconds: fact.howLong.complete ?? null,
            };
          }
          return out;
        },
      });

      api.registerStatisticsProvider({
        id: "pc-gamepak/cartridge-stats",
        displayName: "PC GamePak",
        category: "Playtime",
        resolve(): StatisticsEntry[] {
          const seconds = allFacts.reduce((sum, fact) => sum + fact.seconds, 0);
          return [
            {
              id: "cartridges",
              label: "Cartridges plugged in",
              value: new Set(allFacts.map((fact) => fact.cartridge)).size,
            },
            { id: "games", label: "Games on them", value: allFacts.length },
            {
              id: "hours",
              label: "Played on these cartridges",
              value: Math.round((seconds / 3600) * 10) / 10,
              unit: "h",
            },
            {
              id: "launches",
              label: "Launches",
              value: allFacts.reduce((sum, fact) => sum + fact.launches, 0),
            },
          ];
        },
      });

      api.registerWidgetProvider({
        id: "pc-gamepak/cartridge-slot",
        displayName: "Cartridge slot",
        render: () => <CartridgeWidget />,
        refreshPolicy: "focus",
      });

      stopWatching = watchForChanges(api);
      console.debug("[pc-gamepak] registered with Deck Shelves");
    },
    onUnmount() {
      stopWatching?.();
      stopWatching = null;
    },
  });
}
