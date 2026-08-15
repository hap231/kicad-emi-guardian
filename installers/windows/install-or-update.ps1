[CmdletBinding()]
param(
    [string]$KiCadVersion = "10.0",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PluginIdentifier = "com.openai.kicad.emi-guardian"
$PluginFolderName = "emi-guardian"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Payload = Join-Path $ScriptRoot "payload\emi-guardian"
$Manifest = Join-Path $Payload "plugin.json"

if (-not (Test-Path -LiteralPath $Manifest -PathType Leaf)) {
    throw "Installer payload is incomplete. Expected: $Manifest"
}

$running = @(Get-Process -Name "kicad", "pcbnew" -ErrorAction SilentlyContinue)
if ($running.Count -gt 0 -and -not $Force) {
    throw "Close KiCad and PCB Editor before installing. Re-run with -Force only when you have saved all boards."
}

$Documents = [Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)
if ([string]::IsNullOrWhiteSpace($Documents)) {
    $Documents = Join-Path $env:USERPROFILE "Documents"
}
$PluginsRoot = Join-Path $Documents "KiCad\$KiCadVersion\plugins"
$Destination = Join-Path $PluginsRoot $PluginFolderName
$LegacyBackupRoot = Join-Path $PluginsRoot "_emi-guardian-backups"
$Cache = Join-Path $env:LOCALAPPDATA "KiCad\$KiCadVersion\python-environments\$PluginIdentifier"
$TempRoot = Join-Path ([IO.Path]::GetTempPath()) ("emi-guardian-install-{0}-{1}" -f $PID, [Guid]::NewGuid().ToString("N"))
$NewPayload = Join-Path $TempRoot "new"

New-Item -ItemType Directory -Path $PluginsRoot -Force -ErrorAction Stop | Out-Null
# Remove directories left by legacy installers before replacement. KiCad
# may scan every direct child of the plugin root on its next launch.
Remove-Item -LiteralPath $LegacyBackupRoot -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath $PluginsRoot -Directory -Filter "emi-guardian.installing-*" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $TempRoot -Force -ErrorAction Stop | Out-Null
Copy-Item -LiteralPath $Payload -Destination $NewPayload -Recurse -Force -ErrorAction Stop

try {
    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }
    Copy-Item -LiteralPath $NewPayload -Destination $Destination -Recurse -Force -ErrorAction Stop
    Remove-Item -LiteralPath $Cache -Recurse -Force -ErrorAction SilentlyContinue
} catch {
    Remove-Item -LiteralPath $Destination -Recurse -Force -ErrorAction SilentlyContinue
    throw "Installation failed. No backup was created; correct the cause and run the installer again. $($_.Exception.Message)"
} finally {
    Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "EMI Guardian was installed or updated successfully without creating a backup copy." -ForegroundColor Green
Write-Host "Plugin: $Destination"
Write-Host "Start KiCad, enable Preferences > Plugins > Enable KiCad API, open a PCB, then use Tools > External Plugins > Open EMI Guardian."
