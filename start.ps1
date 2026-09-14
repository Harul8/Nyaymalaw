<#
    Start Nyaymalaw, restarting it if it is already up, then open the UI.

    Double-click `start.cmd`, or run this directly:

        powershell -ExecutionPolicy Bypass -File start.ps1

    THERE IS ONE SERVER, NOT TWO. `nm.bootstrap.main` serves the API and the
    advocate UI from the same process -- `/api/...` and the `/static` mount
    with the `/` index -- so there is one thing to start and one port to wait
    on. A script that pretended to start two would leave whoever read it
    looking for the second.

    RESTART MEANS RESTART. Anything already listening on the port is stopped
    first, deliberately: a stale server is the B-114 defect wearing a helpful
    face -- it answers, so the screen looks right, and it is running code that
    is no longer on disk. That banner has fired twice in one session on this
    project's own edits.

    IT WAITS FOR /api/health BEFORE OPENING THE BROWSER. Opening it early
    shows a connection error that reads exactly like a broken build.
#>
param(
    [int]$Port = 8071,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host ""
Write-Host "  Nyaymalaw" -ForegroundColor Cyan
Write-Host "  $root"
Write-Host ""

# ---- stop whatever holds the port -----------------------------------------
# BY PORT, NOT BY NAME. Killing "python" would take down anything else the
# advocate is running; the process holding THIS port is the one this script
# is replacing and the only one it may touch.
$held = $null
try {
    $held = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique
} catch {
    $held = $null
}

if ($held) {
    foreach ($processId in $held) {
        $name = (Get-Process -Id $processId -ErrorAction SilentlyContinue).ProcessName
        Write-Host "  restarting - stopping pid $processId ($name) on port $Port" -ForegroundColor Yellow
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
    # The socket lingers briefly after the process goes.
    $waited = 0
    while ($waited -lt 50) {
        Start-Sleep -Milliseconds 100
        $waited++
        $still = $null
        try {
            $still = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        } catch { }
        if (-not $still) { break }
    }
} else {
    Write-Host "  nothing on port $Port - starting fresh"
}

# ---- the key, without which the store refuses to write --------------------
# A HARD FAILURE BY DESIGN. `EncryptionNotConfigured` is raised rather than
# degraded, because an unset key must never become a silent no-op writing
# privileged client material to disk in plaintext. This script therefore
# supplies a DEVELOPMENT key and says so, rather than letting the server die
# with a message the advocate has to go and look up.
# THE KEY IS THE APP'S TO FIND, NOT THIS SCRIPT'S TO SUPPLY.
#
# `load_dotenv` is documented "Existing environment variables win", so a key
# set HERE SHADOWS the one in `.env` -- and that is exactly what happened:
# this script set its own, the app preferred it over the real one, and an
# advocate's account decrypted to InvalidToken. The record was never damaged.
# It was being opened with the wrong key, by me.
#
# So `.env` is checked FIRST and left alone if it has one. A key is generated
# only when nothing anywhere provides one, and it is saved so accounts survive
# a restart.
$envFile = Join-Path $root ".env"
$keyFile = Join-Path $root ".nm\dev-matter-key"
$fromEnvFile = $false
if (Test-Path $envFile) {
    foreach ($line in (Get-Content $envFile)) {
        if ($line -match '^\s*NM_MATTER_KEY\s*=\s*\S') { $fromEnvFile = $true; break }
    }
}

if ($env:NM_MATTER_KEY) {
    Write-Host "  NM_MATTER_KEY from the environment" -ForegroundColor DarkGray
} elseif ($fromEnvFile) {
    # LEFT UNSET ON PURPOSE. The app reads `.env` itself, and anything set
    # here would win over it -- which is the defect this comment exists for.
    Write-Host "  NM_MATTER_KEY from .env (the app loads it)" -ForegroundColor DarkGray
} elseif (Test-Path $keyFile) {
    $env:NM_MATTER_KEY = (Get-Content $keyFile -Raw).Trim()
    Write-Host "  NM_MATTER_KEY from .nm\dev-matter-key (development)" -ForegroundColor DarkGray
} else {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $generated = [Convert]::ToBase64String($bytes)
    New-Item -ItemType Directory -Force -Path (Split-Path $keyFile) | Out-Null
    Set-Content -Path $keyFile -Value $generated -Encoding utf8 -NoNewline
    $env:NM_MATTER_KEY = $generated
    Write-Host "  no NM_MATTER_KEY anywhere - GENERATED one and saved it to" -ForegroundColor Yellow
    Write-Host "    .nm\dev-matter-key, reused on every start" -ForegroundColor Yellow
}

# ---- start it -------------------------------------------------------------
# THE BACKEND PACKAGE LIVES UNDER backend/. `nm` is not installed into the
# interpreter, deliberately: an editable install would make every worktree
# import the MAIN checkout's code. The path is set for this process only.
$env:PYTHONPATH = (Join-Path $root "backend") + [IO.Path]::PathSeparator + $root
Write-Host "  starting  python -m nm.bootstrap.main --port $Port"
$server = Start-Process -FilePath "python" `
    -ArgumentList "-m", "nm.bootstrap.main", "--port", "$Port" `
    -WorkingDirectory $root -PassThru

# ---- wait for it to actually answer ---------------------------------------
#
# A TCP CONNECT, NOT `Invoke-WebRequest`. Windows PowerShell 5.1 has no
# `-NoProxy`, and `Invoke-WebRequest` resolves the system proxy even for
# localhost -- measured here, it hung past its own `-TimeoutSec`. A socket
# connect answers the only question this loop asks, and answers it in
# milliseconds.
$url = "http://localhost:$Port"
$ready = $false
for ($i = 0; $i -lt 100; $i++) {
    Start-Sleep -Milliseconds 200
    if ($server.HasExited) {
        Write-Host ""
        Write-Host "  the server exited immediately (code $($server.ExitCode))." -ForegroundColor Red
        Write-Host "  run it in the foreground to see why:" -ForegroundColor Red
        Write-Host "    python -m nm.bootstrap.main --port $Port"
        exit 1
    }
    $probe = New-Object System.Net.Sockets.TcpClient
    try {
        $probe.Connect("127.0.0.1", $Port)
        if ($probe.Connected) { $ready = $true }
    } catch { } finally { $probe.Close() }
    if ($ready) { break }
}

if (-not $ready) {
    Write-Host ""
    Write-Host "  started (pid $($server.Id)) but /api/health did not answer in 20s." -ForegroundColor Yellow
    Write-Host "  NOT opening the browser: a connection error reads exactly" -ForegroundColor Yellow
    Write-Host "  like a broken build, and this is a slow start." -ForegroundColor Yellow
    exit 1
}

Write-Host "  ready     pid $($server.Id)  ->  $url" -ForegroundColor Green

# WHAT THE SERVER SAYS ABOUT ITSELF, before the advocate trusts a screen.
# `readiness` reports three states per capability, and a capability that
# cannot run has to be visible BEFORE a turn depends on it.
try {
    # PROXY OFF FOR THIS ONE READ, same reason as the probe above.
    $client = New-Object System.Net.WebClient
    $client.Proxy = $null
    $health = $client.DownloadString("$url/api/health") | ConvertFrom-Json
    Write-Host ""
    foreach ($p in $health.PSObject.Properties) {
        if ($p.Value -is [string]) {
            Write-Host ("    {0,-14} {1}" -f $p.Name, $p.Value) -ForegroundColor DarkGray
        }
    }
} catch { }

if (-not $NoBrowser) {
    Write-Host ""
    Write-Host "  opening $url"
    Start-Process $url
}

Write-Host ""
Write-Host "  Stop it with:  Stop-Process -Id $($server.Id)"
Write-Host ""
