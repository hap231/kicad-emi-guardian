[CmdletBinding()]
param(
    [string]$KiCadVersion = "10.0",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PluginIdentifier = "com.openai.kicad.emi-guardian"
$PluginFolderName = "emi-guardian"
$running = @(Get-Process -Name "kicad", "pcbnew" -ErrorAction SilentlyContinue)
if ($running.Count -gt 0 -and -not $Force) {
    throw "Close KiCad and PCB Editor before uninstalling. Re-run with -Force only when you have saved all boards."
}

$Documents = [Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)
if ([string]::IsNullOrWhiteSpace($Documents)) {
    $Documents = Join-Path $env:USERPROFILE "Documents"
}
$PluginsRoot = Join-Path $Documents "KiCad\$KiCadVersion\plugins"
$Destination = Join-Path $PluginsRoot $PluginFolderName
$LegacyBackupRoot = Join-Path $PluginsRoot "_emi-guardian-backups"
$Cache = Join-Path $env:LOCALAPPDATA "KiCad\$KiCadVersion\python-environments\$PluginIdentifier"

Remove-Item -LiteralPath $Destination -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $Cache -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $LegacyBackupRoot -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath $PluginsRoot -Directory -Filter "emi-guardian.installing-*" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "EMI Guardian was uninstalled." -ForegroundColor Green
Write-Host "Persistent settings and exported reports were not removed."
