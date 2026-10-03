using System;

namespace GamePakShelf.Services
{
    /// <summary>
    /// Where the shared code logs. Each front-end points these at its own log
    /// at startup -- Playnite's logger, LaunchBox's log file -- because the code
    /// in Core and Services is shared between both and can depend on neither.
    /// </summary>
    public static class GamePakLog
    {
        public static Action<string> Info { get; set; } = _ => { };

        public static Action<Exception, string> Error { get; set; } = (_, __) => { };
    }
}
