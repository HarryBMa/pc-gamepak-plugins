using System;
using System.Collections.Generic;
using System.IO;
using System.Windows;
using System.Windows.Threading;

using GamePakShelf.Core;
using GamePakShelf.Services;

using Playnite.SDK;
using Playnite.SDK.Events;
using Playnite.SDK.Models;
using Playnite.SDK.Plugins;

namespace GamePakShelf
{
    /// <summary>
    /// PC GamePak's Playnite front-end: a cartridge slot as the first tile of the
    /// library. Empty with no cartridge in; the cartridge's own art with one.
    /// Play starts a single game directly and opens PC GamePak to choose from a
    /// collection; the tile's menu can eject.
    /// </summary>
    public class GamePakShelfPlugin : GenericPlugin
    {
        private const string SwitchedOffNotificationId = "pcgamepak-switched-off";

        private static readonly ILogger logger = LogManager.GetLogger();

        private CartridgeWatcher watcher;

        private SlotManager slot;

        /// <summary>
        /// A change that arrived while the slot's game was running. Replacing the
        /// entry under a running game would leave Playnite recording play time
        /// against a game that no longer exists, so it waits for the stop.
        /// </summary>
        private bool changePending;

        private Cartridge pendingCartridge;

        /// <summary>What the watcher last found in the drives, shown yet or not. What Eject ejects.</summary>
        private Cartridge inserted;

        /// <summary>One eject at a time: the second press of a slow one is not a second eject.</summary>
        private bool ejecting;


        public override Guid Id => Guid.Parse("5f0b6a8e-2c47-4d1e-9a3b-7e6c1d2f8a40");


        public GamePakShelfPlugin(IPlayniteAPI api)
            : base(api)
        {
        }


        public override void OnApplicationStarted(OnApplicationStartedEventArgs args)
        {
            try
            {
                string emptyCover = Path.Combine(
                    Path.GetDirectoryName(typeof(GamePakShelfPlugin).Assembly.Location),
                    "Assets",
                    "empty_slot.png");

                slot = new SlotManager(PlayniteApi, Id, emptyCover);
                PlayniteApi.UriHandler.RegisterSource(SlotManager.UriSource, OnUri);

                watcher = new CartridgeWatcher(cartridge => OnUiThread(() => OnCartridgeChanged(cartridge)));
                watcher.Start();
            }
            catch (Exception ex)
            {
                logger.Error(ex, "GamePakShelf: could not start.");
            }
        }


        public override void OnApplicationStopped(OnApplicationStoppedEventArgs args)
        {
            watcher?.Dispose();
            watcher = null;
        }


        public override void OnGameStopped(OnGameStoppedEventArgs args)
        {
            if (changePending && IsSlot(args.Game))
            {
                changePending = false;
                Apply(pendingCartridge);
            }
        }


        public override IEnumerable<MainMenuItem> GetMainMenuItems(GetMainMenuItemsArgs args)
        {
            if (inserted != null)
            {
                yield return new MainMenuItem
                {
                    MenuSection = "@PC GamePak",
                    Description = $"Eject {inserted.Title}",
                    Action = _ => Eject(force: false)
                };
            }

            yield return new MainMenuItem
            {
                MenuSection = "@PC GamePak",
                Description = "Look for a cartridge again",
                Action = _ => watcher?.Refresh()
            };
        }


        public override IEnumerable<GameMenuItem> GetGameMenuItems(GetGameMenuItemsArgs args)
        {
            if (inserted == null || args.Games.Count != 1 || !IsSlot(args.Games[0]))
            {
                yield break;
            }

            yield return new GameMenuItem
            {
                Description = "Eject cartridge",
                Action = _ => Eject(force: false)
            };
        }


        /// <summary>
        /// Eject the cartridge through the launcher, off the UI thread, and say
        /// what came of it. When something is still running from the drive, name
        /// it and offer to close it -- the same choice the launcher's window gives.
        /// </summary>
        private void Eject(bool force)
        {
            Cartridge cartridge = inserted;
            string launcher = GamePakInstall.LauncherPath();
            if (cartridge == null || ejecting)
            {
                return;
            }

            if (launcher == null)
            {
                ShowNoLauncher();
                return;
            }

            ejecting = true;
            // From before the eject starts, not after it succeeds: a poll landing
            // between the dismount and the result would mount the volume again.
            watcher?.Leave(cartridge.Root);
            System.Threading.Tasks.Task.Run(() => Ejector.Run(launcher, cartridge.Root, force)).ContinueWith(task =>
            {
                OnUiThread(() =>
                {
                    ejecting = false;
                    Ejector.Result result = task.Result;
                    string lines = string.Join("\n", result.Lines);

                    switch (result.Outcome)
                    {
                        case Ejector.Outcome.Ejected:
                            PlayniteApi.Notifications.Add(new NotificationMessage(
                                "pcgamepak-ejected-" + Guid.NewGuid().ToString("N"),
                                $"{cartridge.Title}: {lines}",
                                NotificationType.Info));
                            break;

                        case Ejector.Outcome.Busy:
                            watcher?.Return(cartridge.Root);
                            MessageBoxResult choice = PlayniteApi.Dialogs.ShowMessage(
                                $"{lines}\n\nClosing it first lets the game write its save to the cartridge. Forcing it may lose whatever was part-way through being written.\n\nForce quit and eject?",
                                $"{cartridge.Title} is still in use",
                                MessageBoxButton.YesNo);
                            if (choice == MessageBoxResult.Yes)
                            {
                                Eject(force: true);
                            }

                            break;

                        default:
                            watcher?.Return(cartridge.Root);
                            PlayniteApi.Dialogs.ShowErrorMessage(lines, $"Could not eject {cartridge.Title}");
                            break;
                    }
                });
            });
        }


        private void OnCartridgeChanged(Cartridge cartridge)
        {
            inserted = watcher != null && watcher.FrontEndOn ? cartridge : null;

            Game current = slot.Current;
            if (current != null && (current.IsRunning || current.IsLaunching))
            {
                changePending = true;
                pendingCartridge = cartridge;
                logger.Info("GamePakShelf: slot is in use; the change waits for it to stop.");
                return;
            }

            Apply(cartridge);
        }


        private void Apply(Cartridge cartridge)
        {
            try
            {
                if (!watcher.FrontEndOn)
                {
                    // PC GamePak's register says plugins are off until switched
                    // on, and this one is no exception. Said once, visibly, since
                    // a slot that never appears is otherwise indistinguishable from
                    // a broken extension.
                    slot.Remove();
                    PlayniteApi.Notifications.Add(new NotificationMessage(
                        SwitchedOffNotificationId,
                        "PC GamePak: the cartridge slot is off. Turn on \"Playnite library\" under Front-ends in PC GamePak's settings.",
                        NotificationType.Info));
                    return;
                }

                PlayniteApi.Notifications.Remove(SwitchedOffNotificationId);

                if (cartridge == null)
                {
                    slot.ShowEmpty();
                }
                else
                {
                    slot.ShowCartridge(cartridge, GamePakInstall.LauncherPath());
                }
            }
            catch (Exception ex)
            {
                logger.Error(ex, "GamePakShelf: could not update the slot.");
            }
        }


        private void OnUri(PlayniteUriEventArgs args)
        {
            string what = args.Arguments.Length > 0 ? args.Arguments[0] : string.Empty;

            OnUiThread(() =>
            {
                if (what == "no-launcher")
                {
                    ShowNoLauncher();
                }
                else
                {
                    PlayniteApi.Dialogs.ShowMessage("No cartridge is plugged in.", "PC GamePak");
                }
            });
        }


        private void ShowNoLauncher()
        {
            PlayniteApi.Dialogs.ShowErrorMessage(
                $"PC GamePak's launcher was not found at {Path.Combine(GamePakInstall.Folder, "pc-gamepak.exe")}.\n\nInstall PC GamePak, then plug the cartridge in again.",
                "PC GamePak");
        }


        private bool IsSlot(Game game)
        {
            return game != null && game.PluginId == Id && game.GameId == SlotManager.SlotGameId;
        }


        /// <summary>The database and dialogs belong to the UI thread; the watcher's poll does not.</summary>
        private static void OnUiThread(Action action)
        {
            Dispatcher dispatcher = Application.Current?.Dispatcher;
            if (dispatcher == null || dispatcher.CheckAccess())
            {
                action();
            }
            else
            {
                dispatcher.BeginInvoke(action);
            }
        }
    }
}
