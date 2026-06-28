[CmdletBinding()]
param(
    [int]$BackendPort = 3018,
    [int]$FrontendPort = 3011
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$StateDir = Join-Path $Root '.desktop'
$PidFile = Join-Path $StateDir 'dev.pid'
$DevScript = Join-Path $Root 'dev.ps1'
$FrontendUrl = "http://localhost:$FrontendPort"

New-Item -ItemType Directory -Path $StateDir -Force | Out-Null

function Test-PortListening($port) {
    $listeners = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    return [bool]$listeners
}

function Test-ProcessAlive($pid) {
    if (-not $pid) { return $false }
    try {
        [System.Diagnostics.Process]::GetProcessById([int]$pid) | Out-Null
        return $true
    } catch {
        return $false
    }
}

$existingPid = $null
if (Test-Path $PidFile) {
    $existingPid = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
}

if ((Test-ProcessAlive $existingPid) -or ((Test-PortListening $BackendPort) -and (Test-PortListening $FrontendPort))) {
    Start-Process $FrontendUrl
    exit 0
}

$ps = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
if (-not $ps) {
    $ps = (Get-Command powershell.exe -ErrorAction Stop).Source
}

$args = @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-NoExit',
    '-File', $DevScript,
    '-BackendPort', $BackendPort,
    '-FrontendPort', $FrontendPort
)

$proc = Start-Process -FilePath $ps -ArgumentList $args -WorkingDirectory $Root -WindowStyle Normal -PassThru
$proc.Id | Out-File -FilePath $PidFile -Encoding ascii -Force

Start-Sleep -Seconds 4
Start-Process $FrontendUrl
