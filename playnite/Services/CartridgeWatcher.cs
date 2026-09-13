using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;

using GamePakShelf.Core;

using Playnite.SDK;

namespace GamePakShelf.Services
{
    /// <summary>
    /// Notices a cartridge arriving and leaving, by polling.
    ///
    /// Polling rather than <c>WM_DEVICECHANGE</c>: the watcher PC GamePak ships
    /// already owns that job and a hidden window for it, and a plugin inside
    /// Playnite has no window of its own to receive it on. A stat per drive every
    /// two seconds is nothing, and it also catches the one thing an arrival
    /// message never says -- the wizard rewriting <c>cartridge.conf</c> on a drive
    /// that never left.
    /// </summary>
    public class CartridgeWatcher : IDisposable
    {
        private const int PollMs = 2000;

        private static readonly ILogger logger = LogManager.GetLogger();

        /// <summary>Called with the cartridge now in the slot (null for none), off the UI thread.</summary>
        private readonly Action<Cartridge> onChanged;

        private readonly object gate = new object();

        private Timer timer;

        /// <summary>Null until the first poll, so the first poll always reports.</summary>
        private string lastSignature;

        private DateTime settingsStamp = DateTime.MinValue.AddTicks(1);

        private bool frontEndOn;

        /// <summary>Drive roots not to be read. See <see cref="Leave"/>.</summary>
        private readonly HashSet<string> leftAlone = new HashSet<string>(StringComparer.OrdinalIgnoreCase);


        public CartridgeWatcher(Action<Cartridge> onChanged)
        {
            this.onChanged = onChanged;
        }


        /// <summary>Whether the last poll found Playnite switched on in PC GamePak's settings.</summary>
        public bool FrontEndOn
        {
            get { lock (gate) { return frontEndOn; } }
        }


        public void Start()
        {
            // One-shot and re-armed after each poll, so a slow drive cannot make
            // two polls overlap and report the same insert twice.
            timer = new Timer(_ => Poll(), null, 0, Timeout.Infinite);
        }


        public void Stop()
        {
            lock (gate)
            {
                timer?.Dispose();
                timer = null;
            }
        }


        public void Dispose()
        {
            Stop();
        }


        /// <summary>
        /// Stop looking at a drive, from just before it is ejected until it has
        /// been unplugged.
        ///
        /// On the enclosures PC GamePak is built around, Windows cannot power the
        /// device down: eject flushes and dismounts the volume and leaves the
        /// drive letter where it is. Any read after that mounts the volume again
        /// -- and this poll reads every drive every two seconds, so it undid every
        /// eject within two seconds and put the cartridge back in the slot.
        /// </summary>
        public void Leave(string root)
        {
            lock (gate)
            {
                leftAlone.Add(root);
            }
        }


        /// <summary>Look at a drive again: its eject did not happen.</summary>
        public void Return(string root)
        {
            lock (gate)
            {
                leftAlone.Remove(root);
                timer?.Change(0, Timeout.Infinite);
            }
        }


        /// <summary>Forget what was last reported, so the next poll reports again.</summary>
        public void Refresh()
        {
            lock (gate)
            {
                // Asked for by a person, who may have plugged an ejected
                // cartridge back in without Windows noticing it ever left.
                leftAlone.Clear();
                lastSignature = null;
                settingsStamp = DateTime.MinValue.AddTicks(1);
                timer?.Change(0, Timeout.Infinite);
            }
        }


        private void Poll()
        {
            try
            {
                DateTime stamp = GamePakInstall.SettingsStamp();
                bool on;
                lock (gate)
                {
                    if (stamp != settingsStamp)
                    {
                        settingsStamp = stamp;
                        frontEndOn = GamePakInstall.IsFrontEndOn();
                        logger.Info($"GamePakShelf: Playnite front-end is {(frontEndOn ? "on" : "off")} in PC GamePak's settings.");
                    }

                    on = frontEndOn;
                }

                Cartridge cartridge = FindCartridge();
                string signature = (on ? "on|" : "off|") + (cartridge?.Signature ?? "empty");

                lock (gate)
                {
                    if (signature == lastSignature)
                    {
                        return;
                    }

                    lastSignature = signature;
                }

                logger.Info(cartridge == null
                    ? "GamePakShelf: no cartridge."
                    : $"GamePakShelf: cartridge \"{cartridge.Title}\" in {cartridge.Root}.");

                onChanged(cartridge);
            }
            catch (Exception ex)
            {
                logger.Error(ex, "GamePakShelf: poll failed.");
            }
            finally
            {
                lock (gate)
                {
                    timer?.Change(PollMs, Timeout.Infinite);
                }
            }
        }


        /// <summary>
        /// The cartridge to show, or null.
        ///
        /// One slot, so with two cartridges in, the lower drive letter wins. The
        /// system drive is skipped: a stray <c>C:\cartridge.conf</c> would
        /// otherwise pin the slot full forever.
        /// </summary>
        private Cartridge FindCartridge()
        {
            string system = Path.GetPathRoot(Environment.SystemDirectory);

            // The letters alone, which Windows answers without touching a volume.
            // A drive left alone is forgotten once its letter goes, which is the
            // cartridge actually leaving.
            string[] letters = Environment.GetLogicalDrives();
            string[] skip;
            lock (gate)
            {
                leftAlone.RemoveWhere(root => !letters.Contains(root, StringComparer.OrdinalIgnoreCase));
                skip = leftAlone.ToArray();
            }

            foreach (DriveInfo drive in DriveInfo.GetDrives().OrderBy(d => d.Name, StringComparer.OrdinalIgnoreCase))
            {
                if (skip.Contains(drive.Name, StringComparer.OrdinalIgnoreCase))
                {
                    continue;
                }

                try
                {
                    // Removable and Fixed both: a USB SSD enclosure reports itself
                    // as a fixed disk, and that is exactly what a cartridge is.
                    if ((drive.DriveType != DriveType.Removable && drive.DriveType != DriveType.Fixed)
                        || string.Equals(drive.Name, system, StringComparison.OrdinalIgnoreCase)
                        || !drive.IsReady
                        || !CartridgeReader.IsCartridge(drive.Name))
                    {
                        continue;
                    }

                    Cartridge cartridge = CartridgeReader.Read(drive.Name);
                    if (cartridge != null)
                    {
                        return cartridge;
                    }
                }
                catch (Exception)
                {
                    // A drive pulled mid-read is a drive that is not there.
                }
            }

            return null;
        }
    }
}
