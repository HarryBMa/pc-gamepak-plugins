using System.Collections.Generic;

namespace GamePakShelf.Core
{
    /// <summary>
    /// What the slot needs to know about a plugged-in PC GamePak cartridge.
    ///
    /// Deliberately less than the launcher reads: the slot shows pictures and
    /// hands the drive to the launcher, which does the rest. Saves, hours and
    /// shaders stay the launcher's, so there is one place that decides them.
    /// </summary>
    public class Cartridge
    {
        /// <summary>Drive root as Windows names it, e.g. <c>E:\</c>.</summary>
        public string Root { get; set; }

        /// <summary>The game's title, or the collection's for a bundle.</summary>
        public string Title { get; set; }

        /// <summary>Absolute path to the cover on the drive, or null.</summary>
        public string CoverPath { get; set; }

        /// <summary>Absolute path to the hero / background on the drive, or null.</summary>
        public string BackgroundPath { get; set; }

        /// <summary>Absolute path to the icon source on the drive, or null.</summary>
        public string IconPath { get; set; }

        /// <summary>True for a <c>[collection]</c> + <c>[game]</c> cartridge.</summary>
        public bool IsBundle { get; set; }

        /// <summary>
        /// The games, in the order <c>cartridge.conf</c> lists them. A game's
        /// position here is the number <c>pc-gamepak --play</c> takes. A
        /// single-game cartridge has one.
        /// </summary>
        public List<CartridgeGame> Games { get; set; } = new List<CartridgeGame>();

        public int GameCount => Games.Count;

        /// <summary>
        /// Changes whenever the slot should be redrawn: another drive, or the
        /// same drive with its <c>cartridge.conf</c> rewritten by the wizard.
        /// </summary>
        public string Signature { get; set; }
    }


    /// <summary>One game on a cartridge.</summary>
    public class CartridgeGame
    {
        public string Title { get; set; }

        /// <summary>False for a game with no <c>executable=</c>, which the launcher refuses to play.</summary>
        public bool Playable { get; set; }
    }
}
