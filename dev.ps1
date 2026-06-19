# tickflow-stock-panel - one-shot launcher for backend + frontend (Windows / PowerShell)
#
# Usage:
#   .\dev.ps1
#   .\dev.ps1 -BackendPort 8000 -FrontendPort 5173
#   $env:BACKEND_PORT='8000'; .\dev.ps1
#
# Ctrl-C closes both processes.
#
# If you see "running scripts is disabled":
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

[CmdletBinding()]
param(
    [int]$BackendPort  = 0,
    [int]$FrontendPort = 0
)

$ErrorActionPreference = 'Stop'

# Port precedence: CLI arg > env var > default
if ($BackendPort  -le 0) { $BackendPort  = if ($env:BACKEND_PORT)  { [int]$env:BACKEND_PORT }  else { 3018 } }
if ($FrontendPort -le 0) { $FrontendPort = if ($env:FRONTEND_PORT) { [int]$env:FRONTEND_PORT } else { 3011 } }

# Force UTF-8 console output so child process logs aren't garbled
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
    $OutputEncoding           = New-Object System.Text.UTF8Encoding $false
} catch {}

$Root        = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir  = Join-Path $Root 'backend'
$FrontendDir = Join-Path $Root 'frontend'

function Log-Info($m) { Write-Host "[dev] $m" -ForegroundColor DarkGray }
function Log-Ok  ($m) { Write-Host "[dev] $m" -ForegroundColor Green }
function Log-Warn($m) { Write-Host "[dev] $m" -ForegroundColor Yellow }
function Log-Err ($m) { Write-Host "[dev] $m" -ForegroundColor Red }

# ===== 1. Dependency check =====
function Require-Cmd($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Log-Err "$cmd not found"
        Write-Host "       install via: $hint"
        exit 1
    }
}

Require-Cmd 'uv'   'powershell -c "irm https://astral.sh/uv/install.ps1 | iex"   OR   winget install --id=astral-sh.uv'
Require-Cmd 'pnpm' 'npm i -g pnpm   OR   corepack enable; corepack prepare pnpm@9 --activate'

# ===== 2. Port check - kill anything listening on the target ports =====
function Free-Port($name, $port) {
    $conns = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if (-not $conns) { return }
    $pids = @($conns.OwningProcess | Where-Object { $_ -gt 0 } | Sort-Object -Unique)
    if ($pids.Count -eq 0) { return }

    # Filter to PIDs that still exist as running processes.
    # A zombie TCP endpoint can linger after the process is already dead.
    $alive = @($pids | Where-Object {
        try { [System.Diagnostics.Process]::GetProcessById($_) | Out-Null; $true }
        catch { $false }
    })

    if ($alive.Count -eq 0) {
        # All processes are dead but kernel still holds the socket (zombie endpoint).
        # On Windows this can linger for minutes, but uvicorn/vite can still bind
        # via SO_REUSEADDR — no point waiting, just proceed.
        Log-Warn "port ${port} (${name}) - zombie socket (processes gone), starting anyway"
        return
    }

    Log-Warn "port $port ($name) is in use, killing PID: $($alive -join ', ')"
    # Use taskkill /F /T to kill the entire process tree (parent + children),
    # not just the parent. Stop-Process only kills one process, leaving child
    # processes (e.g. uvicorn spawned by uv) as orphans holding the socket.
    foreach ($p in $alive) {
        # Suppress stderr properly for Windows PowerShell (5.x)
        $null = & cmd /c "taskkill /F /T /PID $p 2>nul"
        # Fallback: if taskkill failed, try Stop-Process
        try { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } catch {}
    }

    # Wait up to 5 seconds for the kernel to release the TCP endpoint
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Milliseconds 500
        $still = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
        if (-not $still) {
            Log-Ok "port $port freed"
            return
        }
    }

    # Port still stuck — process might be dead with zombie socket
    $anyAlive = $still | Where-Object {
        try { [System.Diagnostics.Process]::GetProcessById($_.OwningProcess) | Out-Null; $true }
        catch { $false }
    }
    if ($anyAlive.Count -eq 0) {
        Log-Warn "port ${port} - processes gone but socket lingers, starting anyway"
    } else {
        Log-Err "port ${port} still in use by live process(es). Inspect: Get-NetTCPConnection -LocalPort ${port}"
        exit 1
    }
}

Free-Port 'backend'  $BackendPort
Free-Port 'frontend' $FrontendPort

# ===== 3. First-time dependency install =====
if (-not (Test-Path (Join-Path $BackendDir '.venv'))) {
    Log-Info 'first run - installing Python deps (1-2 min)...'
    Push-Location $BackendDir
    try { & uv sync } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { Log-Err 'uv sync failed'; exit 1 }
    Log-Ok 'backend deps installed'
}

if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
    Log-Info 'first run - installing Node deps...'
    Push-Location $FrontendDir
    try { & pnpm install } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { Log-Err 'pnpm install failed'; exit 1 }
    Log-Ok 'frontend deps installed'
}

# ===== 4. Banner (ASCII so it renders on any codepage) =====
Write-Host ''
Write-Host '+----------------------------------------------+' -ForegroundColor Blue
Write-Host '|  tickflow-stock-panel                        |' -ForegroundColor Blue
Write-Host '|                                              |' -ForegroundColor Blue
Write-Host "|  backend   http://localhost:$BackendPort"      -ForegroundColor Blue
Write-Host "|  frontend  http://localhost:$FrontendPort"     -ForegroundColor Blue
Write-Host '|                                              |' -ForegroundColor Blue
Write-Host '|  Ctrl-C closes both                          |' -ForegroundColor Blue
Write-Host '+----------------------------------------------+' -ForegroundColor Blue
Write-Host ''

# ===== 5. Launch jobs =====
# Each job writes its $PID to a temp file so the main thread can find the
# child powershell.exe and taskkill /T the whole process tree on exit.
$backendPidFile  = [System.IO.Path]::GetTempFileName()
$frontendPidFile = [System.IO.Path]::GetTempFileName()

$backendJob = Start-Job -Name 'backend' -ScriptBlock {
    param($pidFile, $dir, $port)
    $PID | Out-File -FilePath $pidFile -Encoding ascii -Force
    $env:PYTHONUNBUFFERED = '1'
    Set-Location $dir
    & .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port $port 2>&1
} -ArgumentList $backendPidFile, $BackendDir, $BackendPort

$frontendJob = Start-Job -Name 'frontend' -ScriptBlock {
    param($pidFile, $dir, $port)
    $PID | Out-File -FilePath $pidFile -Encoding ascii -Force
    Set-Location $dir
    & pnpm dev --port $port 2>&1
} -ArgumentList $frontendPidFile, $FrontendDir, $FrontendPort

# Wait up to 5 seconds for the PID files to materialise
function Read-JobPid($file) {
    for ($i = 0; $i -lt 50; $i++) {
        try {
            $c = (Get-Content $file -ErrorAction SilentlyContinue) -as [string]
            if ($c -and $c.Trim()) { return [int]$c.Trim() }
        } catch {}
        Start-Sleep -Milliseconds 100
    }
    return $null
}
$backendChildPid  = Read-JobPid $backendPidFile
$frontendChildPid = Read-JobPid $frontendPidFile

# ===== 6. Cleanup =====
$script:cleaning = $false
function Cleanup-All {
    if ($script:cleaning) { return }
    $script:cleaning = $true
    Write-Host ''
    Log-Info 'shutting down...'

    foreach ($p in @($backendChildPid, $frontendChildPid)) {
        if ($p) {
            # /T kills the whole process tree (the job's powershell + uvicorn/vite)
            $null = & cmd /c "taskkill /F /T /PID $p 2>nul"
        }
    }
    foreach ($j in @($backendJob, $frontendJob)) {
        if ($j) {
            Stop-Job   $j -ErrorAction SilentlyContinue
            Remove-Job $j -Force -ErrorAction SilentlyContinue
        }
    }
    foreach ($f in @($backendPidFile, $frontendPidFile)) {
        Remove-Item $f -Force -ErrorAction SilentlyContinue
    }
    Log-Ok 'bye'
}

# ===== 7. Main loop - pump output, handle Ctrl-C =====
# Treat Ctrl-C as input so try/finally is guaranteed to run.
$prevCtrlC = [Console]::TreatControlCAsInput
try {
    [Console]::TreatControlCAsInput = $true

    while ($true) {
        if ([Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            if (($key.Modifiers -band [ConsoleModifiers]::Control) -and $key.Key -eq 'C') {
                break
            }
        }

        $bOut = Receive-Job $backendJob -ErrorAction SilentlyContinue
        if ($bOut) {
            foreach ($line in $bOut) {
                Write-Host '[backend ] ' -NoNewline -ForegroundColor Blue
                Write-Host $line
            }
        }

        $fOut = Receive-Job $frontendJob -ErrorAction SilentlyContinue
        if ($fOut) {
            foreach ($line in $fOut) {
                Write-Host '[frontend] ' -NoNewline -ForegroundColor Green
                Write-Host $line
            }
        }

        if ($backendJob.State -ne 'Running' -or $frontendJob.State -ne 'Running') {
            Log-Warn 'one of the processes exited; closing the other...'
            break
        }

        Start-Sleep -Milliseconds 150
    }
}
finally {
    [Console]::TreatControlCAsInput = $prevCtrlC
    Cleanup-All
}
