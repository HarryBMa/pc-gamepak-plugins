<#
    Tests for the parts of the extension that do not need Playnite running:
    reading cartridge.conf, resolving art, the front-end switch, and the
    launcher's command line.

    Windows PowerShell, not pwsh: the extension targets .NET Framework 4.8.

      ..\build.ps1
      powershell -ExecutionPolicy Bypass -File test\test_reader.ps1
#>
$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent
[void][Reflection.Assembly]::LoadFrom((Join-Path $env:LOCALAPPDATA "Playnite\Playnite.SDK.dll"))
[void][Reflection.Assembly]::LoadFrom((Join-Path $root "_build\GamePakShelf.dll"))

$base = Join-Path ([IO.Path]::GetTempPath()) ("gamepak-test-" + [Guid]::NewGuid().ToString("N"))
$script:fails = 0
function Check($name, $cond) { if ($cond) { "ok   $name" } else { "FAIL $name"; $script:fails++ } }
$R = [GamePakShelf.Core.CartridgeReader]
$S = [GamePakShelf.Services.GamePakInstall]

try {
    # Single game, art in .gamepak
    $single = Join-Path $base "single\"
    New-Item -ItemType Directory -Force (Join-Path $single ".gamepak") | Out-Null
    Set-Content (Join-Path $single ".gamepak\cover.png") "x"
    Set-Content (Join-Path $single ".gamepak\background.jpg") "x"
    Set-Content (Join-Path $single "icon.png") "x"
    Set-Content (Join-Path $single "cartridge.conf") "title=Hollow Knight`nexecutable=steam://rungameid/367520`ncover=.gamepak/cover.png`nbackground=.gamepak/background.jpg`nlogo=missing.png"
    $c = $R::Read($single)
    Check "single: title" ($c.Title -eq "Hollow Knight")
    Check "single: cover" ($c.CoverPath -like "*\.gamepak\cover.png")
    Check "single: background" ($c.BackgroundPath -like "*background.jpg")
    Check "single: unnamed icon.png still found" ($c.IconPath -like "*single\icon.png")
    Check "single: one game, not a bundle" (-not $c.IsBundle -and $c.GameCount -eq 1)
    Check "single: signature names the drive" ($c.Signature -like "$single|*")

    # Collection, CRLF, a bare filename found in .gamepak, cover borrowed from the first game
    $bundle = Join-Path $base "bundle\"
    New-Item -ItemType Directory -Force (Join-Path $bundle ".gamepak") | Out-Null
    Set-Content (Join-Path $bundle ".gamepak\gow.jpg") "x"
    Set-Content (Join-Path $bundle "cartridge.conf") "[collection]`r`ntitle=God of War Collection`r`n`r`n[game]`r`ntitle=GoW 2018`r`nexecutable=steam://rungameid/1`r`ncover=gow.jpg`r`n[game]`r`n[game]`r`ntitle=Two`r`nexecutable=x.exe"
    $b = $R::Read($bundle)
    Check "bundle: collection title" ($b.Title -eq "God of War Collection")
    Check "bundle: an empty [game] is not a game" ($b.IsBundle -and $b.GameCount -eq 2)
    Check "bundle: borrows the first game's cover" ($b.CoverPath -like "*\.gamepak\gow.jpg")
    Check "bundle: games numbered as the launcher numbers them" ($b.Games[0].Title -eq "GoW 2018" -and $b.Games[1].Title -eq "Two")

    $half = Join-Path $base "half\"
    New-Item -ItemType Directory -Force $half | Out-Null
    Set-Content (Join-Path $half "cartridge.conf") "[game]`ntitle=Runs`nexecutable=a.exe`n[game]`ntitle=Does not"
    $h = $R::Read($half)
    Check "bundle: a game with no executable is listed, not playable" ($h.Games[0].Playable -and -not $h.Games[1].Playable)
    Check "single: playable when it names an executable" ($c.Games[0].Playable -and $c.Games[0].Title -eq "Hollow Knight")

    # Paths off the drive are refused; the default cover is still found
    $evil = Join-Path $base "evil\"
    New-Item -ItemType Directory -Force $evil | Out-Null
    Set-Content (Join-Path $base "secret.png") "x"
    Set-Content (Join-Path $evil "poster.jpg") "x"
    Set-Content (Join-Path $evil "cartridge.conf") "title=Evil`ncover=../secret.png`nbackground=C:\Windows\win.ini`nicon=\secret.png"
    $e = $R::Read($evil)
    Check "escape: .. refused, poster.jpg used" ($e.CoverPath -like "*evil\poster.jpg")
    Check "escape: absolute refused" ($null -eq $e.BackgroundPath)
    Check "escape: rooted refused" ($null -eq $e.IconPath)

    $none = Join-Path $base "none\"
    New-Item -ItemType Directory -Force $none | Out-Null
    Check "no cartridge.conf, no cartridge" (-not $R::IsCartridge($none) -and $null -eq $R::Read($none))

    # The front-end switch
    Check "switch: on" ($S::IsFrontEndOn('{"frontends":{"launcher":false,"playnite":true}}'))
    Check "switch: absent is off" (-not $S::IsFrontEndOn('{"frontends":{"launcher":true}}'))
    Check "switch: no frontends is off" (-not $S::IsFrontEndOn('{"steamgriddbEnabled":true}'))
    Check "switch: a string is not a boolean" (-not $S::IsFrontEndOn('{"frontends":{"playnite":"yes"}}'))
    Check "switch: an array is off" (-not $S::IsFrontEndOn('{"frontends":["playnite"]}'))
    Check "switch: junk is off" (-not $S::IsFrontEndOn('not json {'))
    Check "switch: empty is off" (-not $S::IsFrontEndOn(''))

    # The launcher's command line
    Check "args: plain root unquoted" ($S::ShowArguments('E:\') -eq '--drive E:\ --show')
    Check "args: spaced root quoted, trailing backslash doubled" ($S::ShowArguments('C:\My Cart\') -eq '--drive "C:\My Cart\\" --show')
    Check "args: play takes the game number" ($S::PlayArguments('D:\', 1) -eq '--drive D:\ --play 1')
    Check "args: eject" ($S::EjectArguments('D:\', $false) -eq '--drive D:\ --safe-eject')
    Check "args: forced eject" ($S::EjectArguments('D:\', $true) -eq '--drive D:\ --safe-eject --force')

    # What the launcher's --safe-eject prints
    $E = [GamePakShelf.Services.Ejector]
    $ok = $E::Parse("ejected`r`nSafe to remove.`r`n", 0)
    Check "eject: ejected" ($ok.Outcome -eq 'Ejected' -and $ok.Lines[0] -eq 'Safe to remove.')
    $busy = $E::Parse("busy`nFTL.exe is running from it`nsteam.exe has a file open`n", 2)
    Check "eject: busy names every holder" ($busy.Outcome -eq 'Busy' -and $busy.Lines.Count -eq 2)
    Check "eject: an error keeps its reason" (($E::Parse("error`nNot removable`n", 1)).Lines[0] -eq 'Not removable')
    Check "eject: silence from an old launcher is an error" (($E::Parse("", 0)).Outcome -eq 'Error')
}
finally {
    Remove-Item $base -Recurse -Force -ErrorAction SilentlyContinue
}

"$script:fails failed"
exit $script:fails
