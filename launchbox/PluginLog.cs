using System;
using System.IO;

namespace GamePakLaunchBox
{
    /// <summary>
    /// A log beside the plugin. LaunchBox has no logging API for plugins, and a
    /// slot that never appears needs somewhere to say why.
    /// </summary>
    internal static class PluginLog
    {
        private static readonly object Gate = new object();

        private static string LogPath => Path.Combine(Shelf.PluginFolder, "pc-gamepak.log");

        public static void Info(string message)
        {
            Write(message);
        }

        public static void Error(Exception ex, string message)
        {
            Write($"{message} {ex.GetType().Name}: {ex.Message}");
        }

        private static void Write(string line)
        {
            try
            {
                lock (Gate)
                {
                    File.AppendAllText(LogPath, $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {line}{Environment.NewLine}");
                }
            }
            catch
            {
                // Logging never takes the plugin down with it.
            }
        }
    }
}
