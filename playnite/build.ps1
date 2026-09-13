<#
    Build the Playnite extension, and optionally install or package it.

      .\build.ps1             build into _build\
      .\build.ps1 -Install    ...and copy into Playnite's extensions folder
      .\build.ps1 -Pack       ...and make a .pext with Playnite's Toolbox

    Install and Pack both need Playnite installed. Close Playnite before
    installing: it holds the DLL open while it runs.
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
    $toolbox = Join-Path $env:LOCALAPPDATA "Playnite\Toolbox.exe"
    if (-not (Test-Path $toolbox)) { throw "Playnite's Toolbox.exe not found at $toolbox" }

    $staging = Join-Path $out "staging"
    New-Item -ItemType Directory -Force (Join-Path $staging "Assets") | Out-Null
    foreach ($file in $ship) { Copy-Item (Join-Path $out $file) (Join-Path $staging $file) }

    & $toolbox pack $staging $out
    Get-ChildItem $out -Filter *.pext | ForEach-Object { Write-Host "Packed $($_.FullName)" }
}
