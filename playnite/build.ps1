<#
    Build the Playnite extension, and optionally install or package it.

      .\build.ps1             build into _build\
      .\build.ps1 -Install    ...and copy into Playnite's extensions folder
      .\build.ps1 -Pack       ...and make _build\PCGamePak-<version>.pext

    A .pext is a zip with extension.yaml at its root, which is all Playnite's
    Toolbox produces too — so packing needs no Playnite, and runs on CI.
    Install needs Playnite: close it first, as it holds the DLL open.
#>
param(
    [switch]$Install,
    [switch]$Pack
)

$ErrorActionPreference = "Stop"

$here   = $PSScriptRoot
$out    = Join-Path $here "_build"
$target = Join-Path $env:APPDATA "Playnite\Extensions\PCGamePak"

if (Test-Path $out) { Remove-Item $out -Recurse -Force }

dotnet build (Join-Path $here "GamePakShelf.csproj") -c Release -o $out
if ($LASTEXITCODE -ne 0) { throw "build failed" }

# Only what Playnite loads. The .pdb stays in _build for debugging.
$ship = @("extension.yaml", "icon.png", "GamePakShelf.dll", "Assets\empty_slot.png")

if ($Install) {
    if (Get-Process Playnite.DesktopApp, Playnite.FullscreenApp -ErrorAction SilentlyContinue) {
        throw "Playnite is running. Close it first."
    }
    New-Item -ItemType Directory -Force (Join-Path $target "Assets") | Out-Null
    foreach ($file in $ship) { Copy-Item (Join-Path $out $file) (Join-Path $target $file) -Force }
    Write-Host "Installed to $target"
}

if ($Pack) {
    $version = (Select-String -Path (Join-Path $here "extension.yaml") -Pattern '^\s*Version\s*:\s*(.+)$').Matches[0].Groups[1].Value.Trim()
    $pext = Join-Path $out "PCGamePak-$version.pext"

    Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::Open($pext, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($file in $ship) {
            # Forward slashes: the zip standard, and what every unzip expects.
            [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, (Join-Path $out $file), $file.Replace('\', '/'))
        }
    } finally {
        $zip.Dispose()
    }
    Write-Host "Packed $pext"
}
