using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;

using Playnite.SDK;

namespace GamePakShelf.Services
{
    /// <summary>
    /// Eject, by asking the launcher to do it with no window.
    ///
    /// Not done here, because ejecting is not only unmounting: the launcher first
    /// checks what is still running from the drive, then takes the saves and
    /// shader caches back to it and closes the play session. Doing the unmount
    /// alone would leave a save on the host that belongs on the cartridge.
    /// </summary>
    public static class Ejector
    {
        public enum Outcome
        {
            Ejected,
            /// <summary>Something is still running from the drive. Nothing was done.</summary>
            Busy,
            Error
        }


        public class Result
        {
            public Outcome Outcome { get; set; }

            /// <summary>For a person: the result, or one line per program in the way.</summary>
            public List<string> Lines { get; set; } = new List<string>();
        }


        private static readonly ILogger logger = LogManager.GetLogger();


        /// <summary>
        /// Run the eject and wait for it. Blocks for as long as the launcher takes,
        /// which includes a UAC prompt on a drive Windows will not eject without
        /// one -- so never call this on the UI thread.
        /// </summary>
        public static Result Run(string launcherPath, string root, bool force)
        {
            var start = new ProcessStartInfo
            {
                FileName = launcherPath,
                Arguments = GamePakInstall.EjectArguments(root, force),
                WorkingDirectory = Path.GetDirectoryName(launcherPath),
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            try
            {
                using (Process process = Process.Start(start))
                {
                    string output = process.StandardOutput.ReadToEnd();
                    string errors = process.StandardError.ReadToEnd();
                    process.WaitForExit();

                    Result result = Parse(output, process.ExitCode);
                    if (result.Outcome == Outcome.Error && result.Lines.Count == 0 && !string.IsNullOrWhiteSpace(errors))
                    {
                        result.Lines.Add(errors.Trim());
                    }

                    logger.Info($"GamePakShelf: eject {root} (force {force}) -> {result.Outcome}: {string.Join(" / ", result.Lines)}");
                    return result;
                }
            }
            catch (Exception ex)
            {
                logger.Error(ex, "GamePakShelf: could not run the launcher to eject.");
                return new Result { Outcome = Outcome.Error, Lines = { ex.Message } };
            }
        }


        /// <summary>
        /// Read what <c>pc-gamepak --safe-eject</c> printed. The first line is the
        /// word; the exit code stands in when there is no output at all, as there
        /// is from a launcher too old to know the flag.
        /// </summary>
        public static Result Parse(string output, int exitCode)
        {
            List<string> lines = (output ?? string.Empty)
                .Split('\n')
                .Select(line => line.Trim())
                .Where(line => line.Length > 0)
                .ToList();

            string word = lines.FirstOrDefault() ?? string.Empty;
            var result = new Result { Lines = lines.Skip(1).ToList() };

            switch (word)
            {
                case "ejected":
                    result.Outcome = Outcome.Ejected;
                    break;
                case "busy":
                    result.Outcome = Outcome.Busy;
                    break;
                case "error":
                    result.Outcome = Outcome.Error;
                    break;
                default:
                    result.Outcome = Outcome.Error;
                    result.Lines = lines;
                    if (result.Lines.Count == 0)
                    {
                        result.Lines.Add(exitCode == 0
                            ? "The launcher did not say whether it ejected. It may be older than this extension; update PC GamePak."
                            : $"The launcher stopped with code {exitCode}.");
                    }

                    break;
            }

            return result;
        }
    }
}
