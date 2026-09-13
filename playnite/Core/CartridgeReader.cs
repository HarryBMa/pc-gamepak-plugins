using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace GamePakShelf.Core
{
    /// <summary>
    /// Reads <c>cartridge.conf</c> the way PC GamePak's launcher does
    /// (<c>core/src/cartridge.rs</c>), so a cartridge looks the same in the slot
    /// as it does in the launcher's window.
    ///
    /// Two shapes, both from the wizard:
    /// <code>
    /// title=Stardew Valley
    /// executable=steam://rungameid/413150
    /// cover=.gamepak/cover.jpg
    /// </code>
    /// or a collection:
    /// <code>
    /// [collection]
    /// title=God of War Collection
    /// cover=.gamepak/collection.jpg
    ///
    /// [game]
    /// title=God of War (2018)
    /// executable=steam://rungameid/310970
    /// </code>
    ///
    /// Only <c>cartridge.conf</c> makes a drive a cartridge here. The watcher
    /// also accepts a bare <c>autorun.inf</c>, but plenty of ordinary drives
    /// carry one, and a slot that filled with any of them would be wrong more
    /// often than right.
    /// </summary>
    public static class CartridgeReader
    {
        public const string ConfName = "cartridge.conf";

        /// <summary>Where the wizard puts a cartridge's own files.</summary>
        public const string AssetDir = ".gamepak";

        /// <summary>
        /// The launcher refuses a larger "cover", and so does this: a cartridge is
        /// not a trusted input, and the file is copied into Playnite's library.
        /// </summary>
        public const long MaxArtBytes = 8 * 1024 * 1024;

        /// <summary>What the launcher falls back to when <c>cover=</c> is absent.</summary>
        private static readonly string[] DefaultCovers =
        {
            "cover.png", "cover.jpg", "cover.jpeg", "cover.webp",
            "poster.png", "poster.jpg", "box.png", "box.jpg"
        };


        /// <summary>Whether <paramref name="root"/> holds a cartridge at all. Cheap: one stat.</summary>
        public static bool IsCartridge(string root)
        {
            try
            {
                return File.Exists(Path.Combine(root, ConfName));
            }
            catch
            {
                return false;
            }
        }


        /// <summary>Read the cartridge at <paramref name="root"/>, or null if there is not one.</summary>
        public static Cartridge Read(string root)
        {
            string confPath = Path.Combine(root, ConfName);

            FileInfo conf;
            string text;
            try
            {
                conf = new FileInfo(confPath);
                if (!conf.Exists)
                {
                    return null;
                }

                text = File.ReadAllText(confPath);
            }
            catch
            {
                return null;
            }

            Cartridge cartridge = Parse(text, root);
            cartridge.Signature = $"{root}|{conf.LastWriteTimeUtc.Ticks}|{conf.Length}";
            return cartridge;
        }


        /// <summary>Turn the text of a <c>cartridge.conf</c> into a cartridge rooted at <paramref name="root"/>.</summary>
        public static Cartridge Parse(string text, string root)
        {
            var sections = new Dictionary<string, Dictionary<string, string>>(StringComparer.Ordinal);
            var games = new List<Dictionary<string, string>>();
            Dictionary<string, string> current = Section(sections, "general");

            foreach (string raw in text.Split('\n'))
            {
                string line = raw.Trim();
                if (line.Length == 0 || line[0] == ';' || line[0] == '#')
                {
                    continue;
                }

                if (line[0] == '[')
                {
                    int end = line.IndexOf(']');
                    if (end < 0)
                    {
                        continue;
                    }

                    string name = line.Substring(1, end - 1).Trim().ToLowerInvariant();
                    if (name == "game")
                    {
                        // Repeated sections are the point of a collection, so
                        // each [game] is its own map rather than a merge.
                        current = new Dictionary<string, string>(StringComparer.Ordinal);
                        games.Add(current);
                    }
                    else
                    {
                        current = Section(sections, name);
                    }

                    continue;
                }

                int eq = line.IndexOf('=');
                if (eq < 0)
                {
                    continue;
                }

                current[line.Substring(0, eq).Trim().ToLowerInvariant()] = line.Substring(eq + 1).Trim();
            }

            // A [game] with nothing in it is not a game; the launcher drops those too.
            games.RemoveAll(g => g.Count == 0);

            bool isBundle = games.Count > 0;
            Dictionary<string, string> head = isBundle ? Section(sections, "collection") : Section(sections, "general");

            var cartridge = new Cartridge
            {
                Root = root,
                Title = Value(head, "title") ?? (isBundle ? "Game Collection" : "Unknown Game"),
                IsBundle = isBundle,
                Games = isBundle
                    ? games.Select(g => new CartridgeGame
                    {
                        Title = Value(g, "title") ?? "Unknown Game",
                        Playable = Value(g, "executable") != null
                    }).ToList()
                    : new List<CartridgeGame>
                    {
                        new CartridgeGame
                        {
                            Title = Value(head, "title") ?? "Unknown Game",
                            Playable = Value(head, "executable") != null
                        }
                    },
                CoverPath = ResolveArt(root, Value(head, "cover")) ?? DefaultCover(root),
                // Unlike the cover, an absent hero stays absent. Guessing at some
                // image on the drive is right for the one picture a tile must
                // have and wrong for the ones it may not.
                BackgroundPath = ResolveArt(root, Value(head, "background")),
                // The icon is the exception: the drive's own icon picture is
                // there whether or not the conf names it, and without one
                // Playnite's list shows a generic pad beside the slot.
                IconPath = ResolveArt(root, Value(head, "icon")) ?? ResolveArt(root, "icon.png")
            };

            // A collection with no picture of its own borrows its first game's,
            // which is better than the empty-slot art for a slot that is not empty.
            if (cartridge.CoverPath == null && isBundle)
            {
                cartridge.CoverPath = games
                    .Select(g => ResolveArt(root, Value(g, "cover")))
                    .FirstOrDefault(p => p != null);
            }

            return cartridge;
        }


        /// <summary>
        /// Resolve a path the cartridge supplied, refusing anything that leaves the drive.
        ///
        /// <c>cover=</c> comes out of a file on a volume someone else may have
        /// written, so <c>..\..\Users\me\secrets</c> is rejected rather than read
        /// and copied into Playnite's library. A bare filename is also looked
        /// for in <c>.gamepak\</c>, where the wizard keeps artwork.
        /// </summary>
        public static string ResolveArt(string root, string relative)
        {
            if (string.IsNullOrWhiteSpace(relative))
            {
                return null;
            }

            // Absolute and drive-qualified paths are never relative to this cartridge.
            if (relative.IndexOf(':') >= 0 || relative.StartsWith("/") || relative.StartsWith("\\"))
            {
                return null;
            }

            string[] parts = relative.Split(new[] { '/', '\\' }, StringSplitOptions.RemoveEmptyEntries)
                .Where(p => p != ".")
                .ToArray();
            if (parts.Length == 0 || parts.Any(p => p == ".."))
            {
                return null;
            }

            var candidates = new List<string> { Path.Combine(new[] { root }.Concat(parts).ToArray()) };
            if (parts.Length == 1)
            {
                candidates.Add(Path.Combine(root, AssetDir, parts[0]));
            }

            return candidates.FirstOrDefault(IsUsableArt);
        }


        private static string DefaultCover(string root)
        {
            return DefaultCovers.Select(name => Path.Combine(root, name)).FirstOrDefault(IsUsableArt);
        }


        private static bool IsUsableArt(string path)
        {
            try
            {
                var file = new FileInfo(path);
                return file.Exists && file.Length > 0 && file.Length <= MaxArtBytes;
            }
            catch
            {
                // Illegal characters in a hand-written path cost the picture, not the cartridge.
                return false;
            }
        }


        private static Dictionary<string, string> Section(Dictionary<string, Dictionary<string, string>> sections, string name)
        {
            if (!sections.TryGetValue(name, out Dictionary<string, string> section))
            {
                section = new Dictionary<string, string>(StringComparer.Ordinal);
                sections[name] = section;
            }

            return section;
        }


        private static string Value(Dictionary<string, string> section, string key)
        {
            return section.TryGetValue(key, out string value) && !string.IsNullOrWhiteSpace(value) ? value : null;
        }
    }
}
