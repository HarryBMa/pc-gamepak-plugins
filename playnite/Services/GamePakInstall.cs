using System;
using System.Collections.Generic;
using System.IO;

using System.Web.Script.Serialization;

namespace GamePakShelf.Services
{
    /// <summary>
    /// What this extension needs from an installed PC GamePak: where the
    /// launcher is, and whether Playnite has been made a front-end.
    ///
    /// The contract is PC GamePak's <c>core/src/frontend.rs</c>: one boolean per
    /// front-end in <c>settings.json</c>, and nothing more. The launcher's own
    /// settings dialog writes it; this only reads.
    /// <code>
    /// { "frontends": { "launcher": false, "playnite": true } }
    /// </code>
    /// </summary>
    public static class GamePakInstall
    {
        /// <summary>This extension's name in the register.</summary>
        public const string FrontEndId = "playnite";


        /// <summary><c>%LOCALAPPDATA%\PC-GamePak</c>: settings, and the installed binaries.</summary>
        public static string Folder =>
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PC-GamePak");


        /// <summary>
        /// The launcher, or null when it is not installed.
        ///
        /// <c>PC_GAMEPAK_LAUNCHER</c> overrides the install folder, as it does for
        /// the watcher, so a development build can be pointed at.
        /// </summary>
        public static string LauncherPath()
        {
            string fromEnv = Environment.GetEnvironmentVariable("PC_GAMEPAK_LAUNCHER");
            if (!string.IsNullOrWhiteSpace(fromEnv) && File.Exists(fromEnv))
            {
                return fromEnv;
            }

            string installed = Path.Combine(Folder, "pc-gamepak.exe");
            return File.Exists(installed) ? installed : null;
        }


        /// <summary>
        /// Whether the user has switched Playnite on as a front-end.
        ///
        /// Off when nothing has been said, which is the register's rule for every
        /// plugin: installing one does not switch it on. A file that cannot be
        /// read or parsed is the same as no file, as it is for the launcher.
        /// </summary>
        public static bool IsFrontEndOn()
        {
            return IsFrontEndOn(ReadSettingsText());
        }


        public static bool IsFrontEndOn(string settingsJson)
        {
            if (string.IsNullOrWhiteSpace(settingsJson))
            {
                return false;
            }

            try
            {
                // Only a real true counts. "yes" is not a boolean, and a plugin
                // being on is not something to infer -- the launcher drops it too.
                return new JavaScriptSerializer().DeserializeObject(settingsJson) is IDictionary<string, object> settings
                    && settings.TryGetValue("frontends", out object frontends)
                    && frontends is IDictionary<string, object> map
                    && map.TryGetValue(FrontEndId, out object on)
                    && on is bool b
                    && b;
            }
            catch (ArgumentException)
            {
                return false;
            }
            catch (InvalidOperationException)
            {
                return false;
            }
        }


        /// <summary>Last write of <c>settings.json</c>, so a poll only re-reads it when it changed.</summary>
        public static DateTime SettingsStamp()
        {
            try
            {
                var file = new FileInfo(Path.Combine(Folder, "settings.json"));
                return file.Exists ? file.LastWriteTimeUtc : DateTime.MinValue;
            }
            catch
            {
                return DateTime.MinValue;
            }
        }


        private static string ReadSettingsText()
        {
            try
            {
                string path = Path.Combine(Folder, "settings.json");
                return File.Exists(path) ? File.ReadAllText(path) : null;
            }
            catch
            {
                return null;
            }
        }


        /// <summary>
        /// Open the launcher's window on a drive.
        ///
        /// <c>--show</c> because somebody selected the slot: they asked for the
        /// window in so many words, and must get it whatever
        /// <c>on_cartridge_insert</c> says -- the same flag the tray passes.
        /// </summary>
        public static string ShowArguments(string root)
        {
            return $"--drive {Drive(root)} --show";
        }


        /// <summary>
        /// Play game <paramref name="index"/> with no window. The launcher does
        /// what its window would -- saves, hours, shader caches -- and stays
        /// running until the game ends, which is what Playnite times.
        /// </summary>
        public static string PlayArguments(string root, int index)
        {
            return $"--drive {Drive(root)} --play {index}";
        }


        /// <summary>
        /// Eject with no window. Prints <c>ejected</c>, <c>busy</c> or
        /// <c>error</c> on the first line, and lines for a person after it.
        /// </summary>
        public static string EjectArguments(string root, bool force)
        {
            return $"--drive {Drive(root)} --safe-eject" + (force ? " --force" : string.Empty);
        }


        /// <summary>
        /// The root, unquoted when it can be. <c>"E:\"</c> is the classic
        /// Windows trap: the backslash escapes the closing quote and the
        /// launcher receives <c>E:"</c>.
        /// </summary>
        private static string Drive(string root)
        {
            return root.IndexOf(' ') < 0
                ? root
                : "\"" + (root.EndsWith("\\") ? root + "\\" : root) + "\"";
        }
    }
}
