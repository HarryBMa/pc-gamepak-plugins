using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;

using GamePakShelf.Core;

using Playnite.SDK;
using Playnite.SDK.Models;

namespace GamePakShelf.Services
{
    /// <summary>
    /// The one library entry that is the cartridge slot.
    ///
    /// Empty, it shows the empty-slot picture. With a cartridge in, it carries
    /// the cartridge's own title and artwork, and Play opens PC GamePak's
    /// launcher on that drive -- which game of a collection, saves and hours all
    /// stay the launcher's business.
    /// </summary>
    public class SlotManager
    {
        public const string SlotGameId = "PCGAMEPAK_SLOT";

        public const string UriSource = "pcgamepak";

        /// <summary>
        /// Sorts ahead of every real title, and of the other shelves' slots
        /// (<c>!!</c>, <c>!0</c>, <c>!1</c>), so the slot is the first tile under
        /// Playnite's default name ordering. A theme sorted by something else
        /// decides for itself.
        /// </summary>
        private const string PinnedSortingName = "!";

        private static readonly ILogger logger = LogManager.GetLogger();

        private readonly IPlayniteAPI api;

        private readonly Guid pluginId;

        private readonly string emptySlotCoverPath;


        public SlotManager(IPlayniteAPI api, Guid pluginId, string emptySlotCoverPath)
        {
            this.api = api;
            this.pluginId = pluginId;
            this.emptySlotCoverPath = emptySlotCoverPath;
        }


        /// <summary>The slot as it is in the database right now, or null.</summary>
        public Game Current =>
            api.Database.Games.FirstOrDefault(g => g.PluginId == pluginId && g.GameId == SlotGameId);


        /// <summary>
        /// Take the slot out of the library, for when Playnite is not a front-end.
        /// </summary>
        public void Remove()
        {
            Game existing = Current;
            if (existing == null)
            {
                return;
            }

            RemoveFiles(existing);
            api.Database.Games.Remove(existing);
            logger.Info("GamePakShelf: slot removed.");
        }


        public void ShowEmpty()
        {
            Game game = NewSlot("No cartridge");
            game.Description = "Plug in a PC GamePak cartridge and it appears here.";

            // Never left without an action. A game with none is "not installed",
            // the theme then offers Install, and Playnite asks this plugin for an
            // install controller a generic plugin cannot provide -- a dead click.
            game.GameActions = new ObservableCollection<GameAction>
            {
                UriAction("Insert a cartridge", "empty")
            };

            SetCover(game, emptySlotCoverPath);
            Commit(game);
        }


        public void ShowCartridge(Cartridge cartridge, string launcherPath)
        {
            Game game = NewSlot(cartridge.Title);

            game.Description = cartridge.IsBundle
                ? $"{cartridge.GameCount} games on the cartridge in {cartridge.Root}. Play opens PC GamePak to choose one; each game can also be started on its own from this tile's menu."
                : $"On the cartridge in {cartridge.Root}.";

            game.GameActions = launcherPath == null
                ? new ObservableCollection<GameAction> { UriAction("Launcher not installed", "no-launcher") }
                : Actions(cartridge, launcherPath);

            SetCover(game, cartridge.CoverPath ?? emptySlotCoverPath);
            game.BackgroundImage = AddFile(game, cartridge.BackgroundPath);
            game.Icon = AddFile(game, cartridge.IconPath);

            Commit(game);
        }


        /// <summary>
        /// What Play does, and what else the tile's menu offers.
        ///
        /// A single game plays straight away: the launcher runs with no window,
        /// still carrying the saves and hours, and Playnite times it. A collection
        /// needs choosing, and the launcher's window is the picker with each
        /// game's art -- so that is Play, and every game is also its own action
        /// for starting it directly. Only one action is ever marked as Play, so
        /// Playnite never puts its own picker in front of the launcher's.
        /// </summary>
        private static ObservableCollection<GameAction> Actions(Cartridge cartridge, string launcherPath)
        {
            var actions = new ObservableCollection<GameAction>();
            GameAction window = LauncherAction("Open in PC GamePak", launcherPath, GamePakInstall.ShowArguments(cartridge.Root));

            if (!cartridge.IsBundle && cartridge.Games.Count == 1 && cartridge.Games[0].Playable)
            {
                GameAction play = LauncherAction("Play", launcherPath, GamePakInstall.PlayArguments(cartridge.Root, 0));
                play.IsPlayAction = true;
                actions.Add(play);
                actions.Add(window);
                return actions;
            }

            // A collection, or a single game with nothing to run -- which the
            // window explains better than a failed launch would.
            window.IsPlayAction = true;
            actions.Add(window);
            for (int index = 0; index < cartridge.Games.Count; index++)
            {
                CartridgeGame entry = cartridge.Games[index];
                if (cartridge.IsBundle && entry.Playable)
                {
                    actions.Add(LauncherAction($"Play {entry.Title}", launcherPath, GamePakInstall.PlayArguments(cartridge.Root, index)));
                }
            }

            return actions;
        }


        private static GameAction LauncherAction(string name, string launcherPath, string arguments)
        {
            return new GameAction
            {
                Name = name,
                Type = GameActionType.File,
                Path = launcherPath,
                Arguments = arguments,
                WorkingDir = Path.GetDirectoryName(launcherPath)
            };
        }


        /// <summary>
        /// A fresh entry, replacing the old one rather than editing it.
        ///
        /// Fullscreen mode's virtualised list does not always redraw an item
        /// whose name and cover change under it, even though the update lands --
        /// CartridgeShelf and DiscShelf found this out. A real remove and add
        /// makes it build the tile again.
        /// </summary>
        private Game NewSlot(string name)
        {
            Remove();

            Platform pc = api.Database.Platforms.FirstOrDefault(p => p.SpecificationId == "pc_windows");

            var game = new Game(name)
            {
                GameId = SlotGameId,
                PluginId = pluginId,
                SortingName = PinnedSortingName,
                Added = DateTime.Now,
                PlatformIds = pc == null ? new List<Guid>() : new List<Guid> { pc.Id },
                GameActions = new ObservableCollection<GameAction>(),
                // Always installed: the slot carries either Play or a message.
                IsInstalled = true
            };

            api.Database.Games.Add(game);
            return game;
        }


        private void Commit(Game game)
        {
            api.Database.Games.Update(game);
            logger.Info($"GamePakShelf: slot shows \"{game.Name}\" (game {game.Id}).");
        }


        private static GameAction UriAction(string name, string path)
        {
            return new GameAction
            {
                Name = name,
                Type = GameActionType.URL,
                Path = $"playnite://{UriSource}/{path}",
                IsPlayAction = true
            };
        }


        private void SetCover(Game game, string sourcePath)
        {
            game.CoverImage = AddFile(game, sourcePath);
        }


        /// <summary>
        /// Copy a picture into Playnite's library for this entry, or null.
        ///
        /// Under a new name every time: WPF caches images by path, so a slot
        /// that reused <c>cover.jpg</c> for a different cartridge could go on
        /// showing the last one.
        /// </summary>
        private string AddFile(Game game, string sourcePath)
        {
            if (string.IsNullOrEmpty(sourcePath))
            {
                return null;
            }

            string temp = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + Path.GetExtension(sourcePath));
            try
            {
                File.Copy(sourcePath, temp, overwrite: true);
                return api.Database.AddFile(temp, game.Id);
            }
            catch (Exception ex)
            {
                // A picture that cannot be read -- the drive just left, say -- costs
                // the picture, not the slot.
                logger.Warn(ex, $"GamePakShelf: could not copy {sourcePath}.");
                return null;
            }
            finally
            {
                try
                {
                    File.Delete(temp);
                }
                catch
                {
                    // Temp is temp.
                }
            }
        }


        private void RemoveFiles(Game game)
        {
            foreach (string file in new[] { game.CoverImage, game.BackgroundImage, game.Icon })
            {
                if (string.IsNullOrEmpty(file))
                {
                    continue;
                }

                try
                {
                    api.Database.RemoveFile(file);
                }
                catch (Exception ex)
                {
                    logger.Warn(ex, "GamePakShelf: could not remove an old slot picture.");
                }
            }
        }
    }
}
