[CmdletBinding()]
param(
    [switch]$SkipSync,
    [switch]$SkipModelPull,
    [switch]$Check
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv was not found. Install it from https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
}

$LauncherArgs = @("run", "--no-project", "--python", "3.12", "python", "scripts/start.py")
if ($SkipSync) { $LauncherArgs += "--skip-sync" }
if ($SkipModelPull) { $LauncherArgs += "--skip-model-pull" }
if ($Check) { $LauncherArgs += "--check" }

& uv @LauncherArgs
exit $LASTEXITCODE
