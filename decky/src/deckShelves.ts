import { callable } from "@decky/api";
import { register } from "@deck-shelves/api";

import { ownedAppIds } from "./shortcuts";

/**
 * Offer the cartridge's games to Deck Shelves as a shelf source.
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
 */

/** Appids on the cartridges. Cheap: no artwork crosses the bridge. */
const getAppIds = callable<[], number[]>("get_app_ids");

export function offerCartridgesToDeckShelves(): () => void {
  return register({
    name: "pc-gamepak",
    version: "0.1.0",
    onMount(api) {
      api.registerShelfSource({
        id: "pc-gamepak/cartridge",
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
      console.debug("[pc-gamepak] registered a shelf source with Deck Shelves");
    },
  });
}
