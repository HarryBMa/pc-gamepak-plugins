import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { definePlugin, routerHook } from "@decky/api";
import { useEffect, useState, type FC } from "react";

import { CartridgeShelf } from "./CartridgeShelf";
import { offerCartridgesToDeckShelves } from "./deckShelves";
import * as shortcuts from "./shortcuts";
import { useCartridges, launch } from "./api";

/**
 * The one setting: whether games the cartridge carries get a Steam shortcut.
 *
 * Separate component so toggling it does not re-render the cartridge list, and
 * so the list still renders if the setting cannot be read.
 */
const ShortcutSetting: FC<{ cartridgeCount: number }> = ({ cartridgeCount }) => {
  const [on, setOn] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    shortcuts.isEnabled().then(setOn).catch(() => {});
  }, []);

  // Cartridges coming and going is what shortcuts have to follow.
  useEffect(() => {
    if (on) void shortcuts.sync();
  }, [on, cartridgeCount]);

  return (
    <PanelSection title="Settings">
      <PanelSectionRow>
        <ToggleField
          label="Add carried games to Steam"
          description="Games stored on the cartridge have no Steam appid, so they cannot appear on the home screen. This adds them as shortcuts, and removes them again on eject."
          checked={on}
          disabled={busy}
          onChange={(next: boolean) => {
            setBusy(true);
            setOn(next);
            shortcuts
              .setEnabled(next)
              .catch((error) => console.error("[pc-gamepak] setting failed", error))
              .finally(() => setBusy(false));
          }}
        />
      </PanelSectionRow>
    </PanelSection>
  );
};

const QuickAccess: FC = () => {
  const { cartridges, loading, refresh } = useCartridges();

  if (loading) {
    return (
      <PanelSection title="Cartridges">
        <PanelSectionRow>Looking…</PanelSectionRow>
      </PanelSection>
    );
  }

  if (cartridges.length === 0) {
    return (
      <PanelSection title="Cartridges">
        <PanelSectionRow>Nothing plugged in.</PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={refresh}>
            Scan again
          </ButtonItem>
        </PanelSectionRow>
        <ShortcutSetting cartridgeCount={0} />
      </PanelSection>
    );
  }

  return (
    <>
      {cartridges.map((cart) => (
        <PanelSection key={cart.id} title={cart.title}>
          {cart.games.map((game) => (
            <PanelSectionRow key={game.executable}>
              <ButtonItem layout="below" onClick={() => launch(game.executable)}>
                {game.title}
              </ButtonItem>
            </PanelSectionRow>
          ))}
        </PanelSection>
      ))}
      <ShortcutSetting cartridgeCount={cartridges.length} />
      <PanelSection>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={refresh}>
            Scan again
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
};

export default definePlugin(() => {
  // The home row. Patching Steam's own React tree is the only way in on its
  // own, and it is the part most likely to need adjusting against a given
  // Steam build — see README. The Quick Access panel above works regardless.
  routerHook.addPatch("/library/home", CartridgeShelf.patch);

  // The other way onto the home screen, and the one that actually lands on the
  // Deck client this was tested against: hand the games to Deck Shelves and let
  // it place them. Costs nothing when Deck Shelves is not installed — the API
  // queues the registration and never fires.
  const unregisterShelfSource = offerCartridgesToDeckShelves();

  return {
    name: "PC GamePak",
    titleView: <div className={staticClasses.Title}>PC GamePak</div>,
    content: <QuickAccess />,
    icon: <CartridgeShelf.Icon />,
    onDismount() {
      routerHook.removePatch("/library/home", CartridgeShelf.patch);
      unregisterShelfSource();
    },
  };
});
