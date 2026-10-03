<#
    Build the LaunchBox plugin, and optionally install or package it.

      .\build.ps1             build into _build\
      .\build.ps1 -Install    ...and copy into LaunchBox\Plugins\PCGamePak
      .\build.ps1 -Pack       ...and make _build\pc-gamepak-launchbox-<version>.zip

    Needs the .NET 10 SDK and a LaunchBox install, whose Core folder holds the
    plugin SDK this builds against: %USERPROFILE%\LaunchBox, or LAUNCHBOX_DIR.
    Install needs LaunchBox and Big Box closed: they hold the DLL open.
#>
param(
    [switch]$Install,
    [switch]$Pack
)

$ErrorActionPreference = "Stop"

$here = $PSScriptRoot
$out  = Join-Path $here "_build"
$launchbox = if ($env:LAUNCHBOX_DIR) { $env:LAUNCHBOX_DIR } else { Join-Path $env:USERPROFILE "LaunchBox" }
$target = Join-Path $launchbox "Plugins\PCGamePak"

if (Test-Path $out) { Remove-Item $out -Recurse -Force }

dotnet build (Join-Path $here "GamePakLaunchBox.csproj") -c Release -o $out
if ($LASTEXITCODE -ne 0) { throw "build failed" }

# Only what LaunchBox loads. The SDK itself is LaunchBox's and stays there.
$ship = @("GamePakLaunchBox.dll", "GamePakLaunchBox.deps.json", "Assets\empty_slot.png")

if ($Install) {
    if (Get-Process LaunchBox, BigBox -ErrorAction SilentlyContinue) {
        throw "LaunchBox or Big Box is running. Close it first."
    }
    New-Item -ItemType Directory -Force (Join-Path $target "Assets") | Out-Null
    foreach ($file in $ship) { Copy-Item (Join-Path $out $file) (Join-Path $target $file) -Force }
    Write-Host "Installed to $target"
}

if ($Pack) {
    [xml]$project = Get-Content (Join-Path $here "GamePakLaunchBox.csproj")
    $version = $project.Project.PropertyGroup.Version | Where-Object { $_ } | Select-Object -First 1
    $stage = Join-Path $out "PCGamePak"
    New-Item -ItemType Directory -Force (Join-Path $stage "Assets") | Out-Null
    foreach ($file in $ship) { Copy-Item (Join-Path $out $file) (Join-Path $stage $file) -Force }
    $zip = Join-Path $out "pc-gamepak-launchbox-$version.zip"
    Compress-Archive -Path $stage -DestinationPath $zip -Force
    Write-Host "Packed $zip"
}
