import { Focusable, afterPatch } from "@decky/ui";
import { Fragment, type FC, type ReactElement } from "react";

import { useCartridges, launch } from "./api";
import type { Cartridge, Game } from "./types";

/**
 * The row itself.
 *
 * Deliberately plain: no Steam-internal card component, because those change
 * shape between client builds and a broken import takes the whole home page
 * with it. A focusable div with a background image survives more.
 */
const Card: FC<{ game: Game; cartridge: Cartridge }> = ({ game, cartridge }) => {
  const art = game.art.cover ?? cartridge.art.cover;
  return (
    <Focusable
      onActivate={() => launch(game.executable, cartridge.id, game.title)}
      style={{
        width: "150px",
        height: "225px",
        flex: "0 0 auto",
        borderRadius: "4px",
        backgroundColor: "#1a1d23",
        backgroundImage: art ? `url(${art})` : undefined,
        backgroundSize: "cover",
        backgroundPosition: "center",
        display: "flex",
        alignItems: "flex-end",
        overflow: "hidden",
      }}
    >
      {!art && (
        <div style={{ padding: "8px", fontSize: "14px", color: "#dfe3e8" }}>
          {game.title}
        </div>
      )}
    </Focusable>
  );
};

const Shelf: FC = () => {
  const { cartridges } = useCartridges();
  if (cartridges.length === 0) return null;

  return (
    <div style={{ marginBottom: "24px" }}>
      {cartridges.map((cart) => (
        <div key={cart.id} style={{ marginBottom: "16px" }}>
          <div
            style={{
              padding: "0 24px 8px",
              fontSize: "16px",
              fontWeight: 700,
              color: "#dfe3e8",
            }}
          >
            {cart.title}
          </div>
          <Focusable
            style={{
              display: "flex",
              gap: "12px",
              padding: "0 24px",
              overflowX: "auto",
            }}
          >
            {cart.games.map((game) => (
              <Card key={game.executable} game={game} cartridge={cart} />
            ))}
          </Focusable>
        </div>
      ))}
    </div>
  );
};

/**
 * Put the shelf on `/library/home`.
 *
 * This is the fragile half of the plugin and the only part that reaches into
 * Steam's own React tree. Steam's home page is not a public API: the shape
 * below is what it looks like on the builds this was written against, and a
 * client update can move it.
 *
 * Two rules follow from that, and both are load-bearing:
 *
 *   1. Never throw. A patch that throws takes the home page down with it, and
 *      a user whose library will not render cannot get to the menu to disable
 *      the plugin. Everything here is wrapped, and failure means the row is
 *      absent rather than the page being broken.
 *   2. Never replace. The original children are always returned; the shelf is
 *      prepended alongside them.
 */
function patch(route: any): any {
  try {
    if (!route?.children?.props) {
      // Said out loud because the alternative is a plugin that loads, reports
      // no error, and simply has no row — which is indistinguishable from the
      // backend finding no cartridge.
      console.warn(
        "[pc-gamepak] /library/home has no children.props to patch; " +
          "Steam's home page is not the shape this expects. Row disabled.",
      );
      return route;
    }

    afterPatch(route.children.props, "renderFunc", (_: unknown, ret: any) => {
      try {
        if (!ret?.props?.children) {
          // Same reasoning as above: this used to `return ret` in silence, and
          // when the shape did change there was nothing anywhere to say so.
          console.warn(
            "[pc-gamepak] renderFunc returned no children; nowhere to put the " +
              "row on this Steam build.",
          );
          return ret;
        }

        // Guard against double-patching when the route re-renders.
        if (ret.props.__pcGamePakPatched) return ret;
        ret.props.__pcGamePakPatched = true;
        console.debug("[pc-gamepak] shelf injected into /library/home");

        const original = ret.props.children;
        ret.props.children = (
          <Fragment>
            <Shelf />
            {original}
          </Fragment>
        ) as ReactElement;
      } catch (error) {
        console.error("[pc-gamepak] could not inject the shelf", error);
      }
      return ret;
    });
  } catch (error) {
    console.error("[pc-gamepak] could not patch /library/home", error);
  }
  return route;
}

const Icon: FC = () => (
  <svg viewBox="0 0 24 24" width="1em" height="1em" fill="currentColor">
    {/* A cartridge: a slab with a label and a connector. */}
    <path d="M6 2h9l3 3v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1zm1 3v6h9V5H7zm1 15h8v2H8v-2z" />
  </svg>
);

export const CartridgeShelf = { patch, Icon, Shelf };
