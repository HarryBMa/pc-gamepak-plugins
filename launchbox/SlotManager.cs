using System;
using System.IO;
using System.Linq;

using GamePakShelf.Core;
using GamePakShelf.Services;

using Unbroken.LaunchBox.Plugins;
using Unbroken.LaunchBox.Plugins.Data;

namespace GamePakLaunchBox
{
    /// <summary>
    /// The one game that is the cartridge slot, in a "PC GamePak" platform.
    ///
    /// Empty, it shows the empty-slot picture. With a cartridge in, it carries
    /// the cartridge's title, art and hours, and Play runs PC GamePak's launcher
    /// on that drive -- saves, hours and which game of a collection stay the
    /// launcher's business. Must be called on LaunchBox's UI thread, which owns
    /// its data.
    /// </summary>
    public static class SlotManager
    {
        public const string PlatformName = "PC GamePak";

        /// <summary>Marks the slot among whatever else the user puts in the platform.</summary>
        private const string SlotSource = "PC GamePak cartridge slot";

        private static IDataManager Data => PluginHelper.DataManager;


        /// <summary>The slot as it is now, or null.</summary>
        public static IGame Current =>
            Data.GetAllGames().FirstOrDefault(g => g.Platform == PlatformName && g.Source == SlotSource);


        public static bool IsSlot(IGame game)
        {
            return game != null && game.Platform == PlatformName && game.Source == SlotSource;
        }


        /// <summary>Take the slot out, for when LaunchBox is not a front-end.</summary>
        public static void Remove()
        {
            IGame existing = Current;
            if (existing == null)
            {
                return;
            }

            RemoveImages(existing);
            Data.TryRemoveGame(existing);
            Commit();
            GamePakLog.Info("slot removed.");
        }


        public static void ShowEmpty(string launcherPath, string emptyCover)
        {
            IGame game = NewSlot("No cartridge");
            game.Notes = "Plug in a PC GamePak cartridge and it appears here. Play opens the cartridge wizard.";
            // Never left without something to run: Play on an empty slot opens the
            // wizard, the one useful thing PC GamePak can do with no cartridge in.
            game.ApplicationPath = launcherPath ?? string.Empty;
            game.CommandLine = launcherPath == null ? string.Empty : "--create";
            AddImage(game, emptyCover, "Box - Front");
            Commit();
            GamePakLog.Info("slot is empty.");
        }


        public static void ShowCartridge(Cartridge cartridge, string launcherPath)
        {
            IGame game = NewSlot(cartridge.Title);
            game.Notes = cartridge.IsBundle
                ? $"{cartridge.GameCount} games on the cartridge in {cartridge.Root}. Play opens PC GamePak to choose one; each game can also be started on its own from Additional Apps."
                : $"On the cartridge in {cartridge.Root}.";

            // The cartridge's own count, which follows it between machines.
            // LaunchBox's would start again at every insert, because the slot is
            // a new game each time.
            game.PlayTime = (int)Math.Min(cartridge.PlaytimeSeconds, int.MaxValue);
            game.PlayCount = (int)Math.Min(cartridge.Launches, int.MaxValue);
            game.LastPlayedDate = cartridge.LastPlayed;

            if (launcherPath == null)
            {
                game.Notes += " PC GamePak's launcher is not installed, so there is nothing to play it with.";
            }
            else
            {
                SetActions(game, cartridge, launcherPath);
            }

            AddImage(game, cartridge.CoverPath, "Box - Front");
            AddImage(game, cartridge.BackgroundPath, "Fanart - Background");
            AddImage(game, cartridge.LogoPath, "Clear Logo");
            Commit();
            GamePakLog.Info($"slot shows \"{cartridge.Title}\" (game {game.Id}).");
        }


        /// <summary>
        /// What Play does, and the additional apps beside it.
        ///
        /// A single game plays straight away: the launcher runs with no window and
        /// stays up until the game ends, which is what LaunchBox times. A
        /// collection opens the launcher's window, which is the picker with each
        /// game's art; every game is also an additional app for starting it
        /// directly.
        /// </summary>
        private static void SetActions(IGame game, Cartridge cartridge, string launcherPath)
        {
            game.ApplicationPath = launcherPath;
            bool single = !cartridge.IsBundle && cartridge.Games.Count == 1 && cartridge.Games[0].Playable;

            if (single)
            {
                game.CommandLine = GamePakInstall.PlayArguments(cartridge.Root, 0);
                AddApp(game, "Open in PC GamePak", launcherPath, GamePakInstall.ShowArguments(cartridge.Root));
            }
            else
            {
                game.CommandLine = GamePakInstall.ShowArguments(cartridge.Root);
                for (int index = 0; index < cartridge.Games.Count; index++)
                {
                    CartridgeGame entry = cartridge.Games[index];
                    if (entry.Playable)
                    {
                        AddApp(game, $"Play {entry.Title}", launcherPath, GamePakInstall.PlayArguments(cartridge.Root, index));
                    }
                }
            }

            if (cartridge.MemoryCard)
            {
                AddApp(game, "Memory card", launcherPath, GamePakInstall.MemoryCardArguments(cartridge.Root));
            }
        }


        private static void AddApp(IGame game, string name, string path, string arguments)
        {
            IAdditionalApplication app = game.AddNewAdditionalApplication();
            app.Name = name;
            app.ApplicationPath = path;
            app.CommandLine = arguments;
            app.WaitForExit = true;
        }


        /// <summary>
        /// A fresh game, replacing the old one rather than editing it. LaunchBox
        /// caches pictures by game, so a slot that kept its game would go on
        /// showing the last cartridge's cover.
        /// </summary>
        private static IGame NewSlot(string title)
        {
            IGame old = Current;
            if (old != null)
            {
                RemoveImages(old);
                Data.TryRemoveGame(old);
            }

            if (Data.GetPlatformByName(PlatformName) == null)
            {
                Data.AddNewPlatform(PlatformName);
            }

            IGame game = Data.AddNewGame(title);
            game.Platform = PlatformName;
            game.Source = SlotSource;
            game.Installed = true;
            return game;
        }


        /// <summary>
        /// Copy a picture into LaunchBox's images folder for this game. LaunchBox
        /// finds a game's pictures by where they are, under its own folder named
        /// for the platform and the kind of image, so the art is copied there
        /// rather than pointed at -- and a cartridge can leave without its art
        /// disappearing from under LaunchBox mid-frame.
        /// </summary>
        private static void AddImage(IGame game, string source, string imageType)
        {
            if (string.IsNullOrEmpty(source) || !File.Exists(source))
            {
                return;
            }

            try
            {
                string target = game.GetNextAvailableImageFilePath(Path.GetExtension(source), imageType, null);
                Directory.CreateDirectory(Path.GetDirectoryName(target));
                File.Copy(source, target, overwrite: true);
            }
            catch (Exception ex)
            {
                // A picture that cannot be read -- the drive just left, say --
                // costs the picture, not the slot.
                GamePakLog.Error(ex, $"could not copy {source}.");
            }
        }


        private static void RemoveImages(IGame game)
        {
            foreach (ImageDetails image in game.GetAllImagesWithDetails() ?? Array.Empty<ImageDetails>())
            {
                try
                {
                    File.Delete(image.FilePath);
                }
                catch (Exception ex)
                {
                    GamePakLog.Error(ex, "could not remove an old slot picture.");
                }
            }
        }


        private static void Commit()
        {
            Data.Save(true);
            // LaunchBox keeps its own view of the data; Big Box rebuilds on the
            // next screen it shows.
            if (!PluginHelper.StateManager.IsBigBox)
            {
                PluginHelper.LaunchBoxMainViewModel?.RefreshData();
            }
        }
    }
}
