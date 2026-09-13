import { callable } from "@decky/api";
import { Navigation } from "@decky/ui";
import { useEffect, useState } from "react";

import type { Cartridge } from "./types";

const getCartridges = callable<[], Cartridge[]>("get_cartridges");
const recordLaunch = callable<[cartridge: string, executable: string, title: string], boolean>(
  "record_launch",
);
const getSerial = callable<[], number>("get_serial");
const rescan = callable<[], Cartridge[]>("rescan");

/** How often to ask the backend whether anything changed. */
const POLL_MS = 2000;

/**
 * Poll the backend's change counter, and only fetch the payload when it moves.
 *
 * The list carries a data URI per cover, so pulling it every two seconds to
 * discover nothing changed would be megabytes of base64 for no reason. The
 * counter is one integer.
 *
 * Lives here rather than beside either consumer: both the Quick Access panel
 * and the home-row shelf need it, and having one import the other made a cycle.
 */
export function useCartridges(): {
  cartridges: Cartridge[];
  loading: boolean;
  refresh: () => void;
} {
  const [cartridges, setCartridges] = useState<Cartridge[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    let seen = -1;

    const tick = async () => {
      try {
        const serial = await getSerial();
        if (!live || serial === seen) return;
        seen = serial;
        const next = await getCartridges();
        if (live) setCartridges(next);
      } catch (error) {
        console.error("[pc-gamepak] poll failed", error);
      } finally {
        if (live) setLoading(false);
      }
    };

    void tick();
    const timer = window.setInterval(tick, POLL_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, []);

  const refresh = () => {
    void rescan()
      .then(setCartridges)
      .catch((error) => console.error("[pc-gamepak] rescan failed", error));
  };

  return { cartridges, loading, refresh };
}

/**
 * Start a game.
 *
 * Steam is handed the URI and does the work; nothing is executed by the
 * plugin. A cartridge that names a path rather than a URI cannot be started
 * from here — that needs the host, which a Decky plugin has no business
 * reaching for, and the PC GamePak launcher already does it properly.
 */
export function launch(executable: string, cartridge?: string, title = ""): boolean {
  if (!executable) return false;
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(executable)) {
    console.warn("[pc-gamepak] not a URI, cannot launch from here:", executable);
    return false;
  }

  // Counted before Steam is handed anything, and never waited on. The count
  // going to the drive is worth having; a game that does not start because a
  // cartridge is mounted read-only is not.
  if (cartridge) {
    void recordLaunch(cartridge, executable, title).catch((error) =>
      console.warn("[pc-gamepak] could not count the launch", error),
    );
  }

  Navigation.NavigateToExternalWeb(executable);
  return true;
}
