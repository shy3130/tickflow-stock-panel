[CmdletBinding()]
param(
    [int]$BackendPort = 3018,
    [int]$FrontendPort = 3011
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ScriptsDir = Join-Path $Root 'scripts'
$IconPath = Join-Path $Root 'packaging\icon.ico'
$Desktop = [Environment]::GetFolderPath('Desktop')
$PowerShell = (Get-Command powershell.exe -ErrorAction Stop).Source

function New-Shortcut($name, $script, $description, $hidden) {
    $shortcutPath = Join-Path $Desktop "$name.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $PowerShell

    $windowArg = if ($hidden) { '-WindowStyle Hidden ' } else { '' }
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass ${windowArg}-File `"$script`" -BackendPort $BackendPort -FrontendPort $FrontendPort"
    $shortcut.WorkingDirectory = $Root
    $shortcut.Description = $description
    if (Test-Path $IconPath) {
        $shortcut.IconLocation = $IconPath
    }
    $shortcut.Save()

    return $shortcutPath
}

function New-CmdShortcut($name, $cmdPath, $description) {
    $shortcutPath = Join-Path $Desktop "$name.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $cmdPath
    $shortcut.WorkingDirectory = $Root
    $shortcut.Description = $description
    if (Test-Path $IconPath) {
        $shortcut.IconLocation = $IconPath
    }
    $shortcut.Save()

    return $shortcutPath
}

function Install-CmdLauncher($name, $script, [bool]$isStart) {
    $target = Join-Path $Desktop "$name.cmd"
    if ($isStart) {
        $devScript = Join-Path $Root 'dev.ps1'
        $content = @(
            '@echo off',
            ('cd /d "{0}"' -f $Root),
            ('start "" "http://localhost:{0}"' -f $FrontendPort),
            ('powershell.exe -NoProfile -ExecutionPolicy Bypass -NoExit -File "{0}" -BackendPort {1} -FrontendPort {2}' -f $devScript, $BackendPort, $FrontendPort)
        )
    } else {
        $content = @(
            '@echo off',
            ('cd /d "{0}"' -f $Root),
            ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" -BackendPort {1} -FrontendPort {2}' -f $script, $BackendPort, $FrontendPort),
            'pause'
        )
    }
    Set-Content -LiteralPath $target -Value $content -Encoding ASCII -Force
    return $target
}

$startScript = Join-Path $ScriptsDir 'start_desktop.ps1'
$stopScript = Join-Path $ScriptsDir 'stop_desktop.ps1'

$startCmdLauncher = Install-CmdLauncher 'TickFlow Start' $startScript $true
$stopCmdLauncher = Install-CmdLauncher 'TickFlow Stop' $stopScript $false
$startShortcut = New-CmdShortcut 'TickFlow Launch' $startCmdLauncher 'Start TickFlow stock panel'
$stopShortcut = New-Shortcut 'TickFlow Stop' $stopScript 'Stop TickFlow stock panel' $false

Write-Host "Created: $startShortcut" -ForegroundColor Green
Write-Host "Created: $stopShortcut" -ForegroundColor Green
Write-Host "Created: $startCmdLauncher" -ForegroundColor Green
Write-Host "Created: $stopCmdLauncher" -ForegroundColor Green
