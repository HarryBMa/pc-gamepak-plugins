using System;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;

using GamePakShelf.Core;
using GamePakShelf.Services;

using Unbroken.LaunchBox.Plugins;
using Unbroken.LaunchBox.Plugins.Data;

namespace GamePakLaunchBox
{
    /// <summary>
    /// What the plugin knows between LaunchBox's calls. Static, because LaunchBox
    /// makes its own instance of each plugin class it finds, one per interface.
    /// </summary>
    internal static class Shelf
    {
        public static CartridgeWatcher Watcher;

        /// <summary>What the watcher last found, shown yet or not. What Eject ejects.</summary>
        public static Cartridge Inserted;

        /// <summary>A change that arrived while a game was running, applied when it stops.</summary>
        public static bool ChangePending;

        public static Cartridge PendingCartridge;

        public static bool GameRunning;

        public static bool Ejecting;

        public static string PluginFolder =>
            Path.GetDirectoryName(typeof(Shelf).Assembly.Location);

        public static string EmptyCover => Path.Combine(PluginFolder, "Assets", "empty_slot.png");


        /// <summary>LaunchBox's data and windows belong to its UI thread; the watcher's poll does not.</summary>
        public static void OnUiThread(Action action)
        {
            var dispatcher = Application.Current?.Dispatcher;
            if (dispatcher == null || dispatcher.CheckAccess())
            {
                action();
            }
            else
            {
                dispatcher.BeginInvoke(action);
            }
        }


        public static void Apply(Cartridge cartridge)
        {
            try
            {
                if (Watcher == null || !Watcher.FrontEndOn)
                {
                    // PC GamePak's register says plugins are off until switched
                    // on, and this one is no exception: no slot until it is.
                    SlotManager.Remove();
                    return;
                }

                if (cartridge == null)
                {
                    SlotManager.ShowEmpty(GamePakInstall.LauncherPath(), EmptyCover);
                }
                else
                {
                    SlotManager.ShowCartridge(cartridge, GamePakInstall.LauncherPath());
                }
            }
            catch (Exception ex)
            {
                GamePakLog.Error(ex, "could not update the slot.");
            }
        }


        public static void OnCartridgeChanged(Cartridge cartridge)
        {
            Inserted = Watcher != null && Watcher.FrontEndOn ? cartridge : null;

            // Replacing the slot under a running game would leave LaunchBox
            // recording play time against a game that no longer exists.
            if (GameRunning)
            {
                ChangePending = true;
                PendingCartridge = cartridge;
                GamePakLog.Info("a game is running; the slot changes when it stops.");
                return;
            }

            Apply(cartridge);
        }
    }


    /// <summary>Starts the watcher once LaunchBox or Big Box is up, and holds slot changes while a game runs.</summary>
    public class GamePakEvents : ISystemEventsPlugin
    {
        public void OnEventRaised(string eventType)
        {
            switch (eventType)
            {
                case SystemEventTypes.LaunchBoxStartupCompleted:
                case SystemEventTypes.BigBoxStartupCompleted:
                    Start();
                    break;

                case SystemEventTypes.GameStarting:
                    Shelf.GameRunning = true;
                    break;

                case SystemEventTypes.GameExited:
                    Shelf.GameRunning = false;
                    if (Shelf.ChangePending)
                    {
                        Shelf.ChangePending = false;
                        Shelf.OnUiThread(() => Shelf.Apply(Shelf.PendingCartridge));
                    }

                    break;

                case SystemEventTypes.LaunchBoxShutdownBeginning:
                case SystemEventTypes.BigBoxShutdownBeginning:
                    Shelf.Watcher?.Dispose();
                    Shelf.Watcher = null;
                    break;
            }
        }


        private static void Start()
        {
            if (Shelf.Watcher != null)
            {
                return;
            }

            GamePakInstall.FrontEndId = "launchbox";
            GamePakLog.Info = PluginLog.Info;
            GamePakLog.Error = PluginLog.Error;

            try
            {
                Shelf.Watcher = new CartridgeWatcher(cartridge => Shelf.OnUiThread(() => Shelf.OnCartridgeChanged(cartridge)));
                Shelf.Watcher.Start();
                GamePakLog.Info("started.");
            }
            catch (Exception ex)
            {
                GamePakLog.Error(ex, "could not start.");
            }
        }
    }


    /// <summary>Eject cartridge, on the slot's menu in LaunchBox and Big Box.</summary>
    public class EjectMenuItem : IGameMenuItemPlugin
    {
        public bool SupportsMultipleGames => false;

        public string Caption => "Eject cartridge";

        public Image IconImage => null;

        public bool ShowInLaunchBox => true;

        public bool ShowInBigBox => true;

        public bool GetIsValidForGame(IGame selectedGame)
        {
            return Shelf.Inserted != null && SlotManager.IsSlot(selectedGame);
        }

        public bool GetIsValidForGames(IGame[] selectedGames)
        {
            return false;
        }

        public void OnSelected(IGame selectedGame)
        {
            Eject(force: false);
        }

        public void OnSelected(IGame[] selectedGames)
        {
        }


        /// <summary>
        /// Eject through the launcher, off the UI thread, and say what came of it.
        /// When something is still running from the drive, name it and offer to
        /// close it -- the same choice the launcher's own window gives.
        /// </summary>
        private static void Eject(bool force)
        {
            Cartridge cartridge = Shelf.Inserted;
            string launcher = GamePakInstall.LauncherPath();
            if (cartridge == null || Shelf.Ejecting)
            {
                return;
            }

            if (launcher == null)
            {
                MessageBox.Show("PC GamePak's launcher is not installed.", "PC GamePak");
                return;
            }

            Shelf.Ejecting = true;
            // From before the eject starts: a poll landing between the dismount
            // and the result would mount the volume again.
            Shelf.Watcher?.Leave(cartridge.Root);
            Task.Run(() => Ejector.Run(launcher, cartridge.Root, force)).ContinueWith(task => Shelf.OnUiThread(() =>
            {
                Shelf.Ejecting = false;
                Ejector.Result result = task.Result;
                string lines = string.Join("\n", result.Lines);

                switch (result.Outcome)
                {
                    case Ejector.Outcome.Ejected:
                        MessageBox.Show($"{cartridge.Title}: {lines}", "PC GamePak");
                        break;

                    case Ejector.Outcome.Busy:
                        Shelf.Watcher?.Return(cartridge.Root);
                        MessageBoxResult choice = MessageBox.Show(
                            $"{lines}\n\nClosing it first lets the game write its save to the cartridge. Forcing it may lose whatever was part-way through being written.\n\nForce quit and eject?",
                            $"{cartridge.Title} is still in use",
                            MessageBoxButton.YesNo);
                        if (choice == MessageBoxResult.Yes)
                        {
                            Eject(force: true);
                        }

                        break;

                    default:
                        Shelf.Watcher?.Return(cartridge.Root);
                        MessageBox.Show(lines, $"Could not eject {cartridge.Title}");
                        break;
                }
            }));
        }
    }


    /// <summary>Tools → "PC GamePak: look for a cartridge again", for an ejected drive plugged back in.</summary>
    public class RescanMenuItem : ISystemMenuItemPlugin
    {
        public string Caption => "PC GamePak: look for a cartridge again";

        public Image IconImage => null;

        public bool ShowInLaunchBox => true;

        public bool ShowInBigBox => false;

        public bool AllowInBigBoxWhenLocked => false;

        public void OnSelected()
        {
            Shelf.Watcher?.Refresh();
        }
    }
}
