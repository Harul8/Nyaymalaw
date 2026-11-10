<#
Start NM's pilot copy (plan AN.48, owner decisions D170 and D172, 10 Nov 2026).

The pilot is this checkout served in one process that does NOT follow code changes, on a port and a store of its own, behind
the owner's Cloudflare tunnel at https://nyaymalaw.in. It is apart from the development server (port 8071), which restarts
whenever code changes. Settings set here win over the checkout's .env (the app's .env loader never replaces a setting that
is already set); the rest - the AI account, the seal key, mail - come from .env as for the development server.

    powershell -NoProfile -File operations\pilot.ps1                 # in the foreground
    (a scheduled task at sign-in runs the same, hidden)

If the server stops, it is started again after 10 seconds. What it prints goes to .nm\pilot-server.log. To update the pilot
to new code: stop the scheduled task (or this window) and start it again.
#>
param(
    [int]$Port = 8000,
    [string]$PublicUrl = 'https://nyaymalaw.in'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv-arrive\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "The project's Python is not at $python." }

# The pilot's own store: its accounts, conversations, papers and usage, apart from the development store (.nm\matters).
$env:NM_MATTER_STORE = Join-Path $root '.nm\pilot'
# Reset links are built from the public address; changes are accepted from the public page and from this machine's own.
$env:NM_PUBLIC_URL = $PublicUrl
$env:NM_TRUSTED_ORIGINS = "$PublicUrl,http://localhost:$Port,http://127.0.0.1:$Port"
New-Item -ItemType Directory -Force -Path $env:NM_MATTER_STORE | Out-Null

# What the server prints is written as UTF-8 whatever the console's code page.
$env:PYTHONUTF8 = '1'

$log = Join-Path $root '.nm\pilot-server.log'
if ("$python$log" -match ' ') { throw 'The checkout path has a space in it; this launcher expects one without.' }
Set-Location $root
while ($true) {
    Add-Content -Path $log -Value "---- $(Get-Date -Format s) starting the pilot on port $Port" -Encoding utf8
    # cmd appends both of the server's streams to the log: Windows PowerShell 5.1 would turn each line the server writes to its
    # error stream into an error record, and stop this script at the first one.
    & cmd.exe /d /c "$python -m nm.app.main --no-follow-code --host 127.0.0.1 --port $Port >> $log 2>&1"
    $code = $LASTEXITCODE
    Add-Content -Path $log -Value "---- $(Get-Date -Format s) the pilot stopped (exit $code); starting again in 10 s" -Encoding utf8
    Start-Sleep -Seconds 10
}
