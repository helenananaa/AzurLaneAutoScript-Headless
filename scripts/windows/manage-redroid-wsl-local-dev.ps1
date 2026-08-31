[CmdletBinding()]
param(
    [ValidateSet('Start', 'Stop', 'Status')]
    [string]$Action = 'Status',

    [ValidateSet('Project', 'Stock', 'Api31')]
    [string]$Profile = 'Project',

    [string]$Distro = 'Ubuntu-22.04'
)

$ErrorActionPreference = 'Stop'

if ($Distro -notmatch '^[A-Za-z0-9._-]+$') {
    throw 'Distro name contains unsupported characters'
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$linuxManagerWindows = Join-Path $repoRoot 'scripts\wsl\manage-redroid-local-dev.sh'
if (-not (Test-Path -LiteralPath $linuxManagerWindows)) {
    throw "WSL Redroid manager is missing: $linuxManagerWindows"
}

$linuxManagerForWslPath = $linuxManagerWindows.Replace('\', '/')
$linuxManagerOutput = & wsl.exe -d $Distro -- wslpath -a -u $linuxManagerForWslPath
if ($LASTEXITCODE -ne 0 -or $null -eq $linuxManagerOutput) {
    throw "Failed to resolve the WSL path for $linuxManagerWindows"
}
$linuxManager = ($linuxManagerOutput | Out-String).Trim()
if ([string]::IsNullOrWhiteSpace($linuxManager)) {
    throw "Failed to resolve the WSL path for $linuxManagerWindows"
}

$linuxHomeOutput = & wsl.exe -d $Distro -- sh -lc 'printf %s "$HOME"'
if ($LASTEXITCODE -ne 0 -or $null -eq $linuxHomeOutput) {
    throw "Failed to resolve the default user's home in $Distro"
}
$linuxHome = ($linuxHomeOutput | Out-String).Trim()
if ([string]::IsNullOrWhiteSpace($linuxHome) -or -not $linuxHome.StartsWith('/')) {
    throw "WSL returned an invalid home directory: $linuxHome"
}
$dockerConfig = "$linuxHome/.config/alas-redroid/docker"

$profileEnvironment = @()
$adbPort = 5555
if ($Profile -eq 'Project') {
    $projectOciWindows = Join-Path $repoRoot 'artifacts\transfer-cache\20260830-redroid-no-storage-overlay-r1\redroid-x86_64.oci.tar.zst'
    if (-not (Test-Path -LiteralPath $projectOciWindows)) {
        throw "Pinned project OCI archive is missing: $projectOciWindows"
    }
    $projectOciForWslPath = $projectOciWindows.Replace('\', '/')
    $projectOciOutput = & wsl.exe -d $Distro -- wslpath -a -u $projectOciForWslPath
    if ($LASTEXITCODE -ne 0 -or $null -eq $projectOciOutput) {
        throw "Failed to resolve the WSL path for $projectOciWindows"
    }
    $projectOci = ($projectOciOutput | Out-String).Trim()
    $profileEnvironment = @(
        'ALAS_REDROID_LOCAL_CONTAINER=alas-redroid-wsl-projectdev',
        'ALAS_REDROID_LOCAL_IMAGE=sha256:881be994eb02237524b070bd15638eaef5cdbc15108355d4137aa9e141854eac',
        'ALAS_REDROID_LOCAL_DATA_NAME=projectdev-data',
        'ALAS_REDROID_LOCAL_ADB_PORT=5556',
        "ALAS_REDROID_LOCAL_OCI_ZST=$projectOci",
        'ALAS_REDROID_LOCAL_OCI_ZST_SHA256=15b15270e06583e7f8b460abd0a23cbbb04ddd9f488a7efe355722d79677c51f'
    )
    $adbPort = 5556
} elseif ($Profile -eq 'Api31') {
    $profileEnvironment = @(
        'ALAS_REDROID_LOCAL_CONTAINER=alas-redroid-wsl-api31',
        'ALAS_REDROID_LOCAL_IMAGE=redroid/redroid@sha256:a6c464bbedcf1dcb67dbf91f329fbb19bee5b50631f0ca6bda6ed7c41b0e64e2',
        'ALAS_REDROID_LOCAL_DATA_NAME=api31-game-data',
        'ALAS_REDROID_LOCAL_ADB_PORT=5557'
    )
    $adbPort = 5557
}

function Invoke-LinuxManager {
    param([Parameter(Mandatory = $true)][string]$ManagerAction)

    $arguments = @('-d', $Distro, '--', 'env') + $profileEnvironment + @(
        'bash', $linuxManager, $ManagerAction
    )
    & wsl.exe @arguments
}

function Initialize-BinderFs {
    & wsl.exe -d $Distro -u root -- bash -lc 'install -d -m 0755 /dev/binderfs && (mountpoint -q /dev/binderfs || mount -t binder binder /dev/binderfs)'
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to mount binderfs in WSL'
    }
}

function Test-KeepAlive {
    & wsl.exe -d $Distro -- pgrep -f '^alas-redroid-wsl-keepalive( |$)' *> $null
    return $LASTEXITCODE -eq 0
}

function Start-KeepAlive {
    if (Test-KeepAlive) {
        return
    }
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = (Get-Command wsl.exe).Source
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.Arguments = "-d $Distro -- bash -lc `"exec -a alas-redroid-wsl-keepalive sleep infinity`""
    $process = [System.Diagnostics.Process]::Start($startInfo)
    if ($null -eq $process) {
        throw 'Failed to start the WSL keepalive process'
    }
    Start-Sleep -Milliseconds 500
    if (-not (Test-KeepAlive)) {
        throw 'The WSL keepalive process did not remain active'
    }
}

function Stop-KeepAlive {
    if (-not (Test-KeepAlive)) {
        return
    }
    & wsl.exe -d $Distro -- pkill -f '^alas-redroid-wsl-keepalive( |$)'
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to stop the WSL keepalive process'
    }
}

function Test-ManagedContainerRunning {
    foreach ($name in @('alas-redroid-wsl-localdev', 'alas-redroid-wsl-projectdev', 'alas-redroid-wsl-api31')) {
        $running = & wsl.exe -d $Distro -- docker --config $dockerConfig container inspect --format '{{.State.Running}}' $name 2>$null
        if ($LASTEXITCODE -eq 0 -and ($running | Out-String).Trim() -eq 'true') {
            return $true
        }
    }
    return $false
}

switch ($Action) {
    'Start' {
        Start-KeepAlive
        Initialize-BinderFs
        Invoke-LinuxManager -ManagerAction start
        if ($LASTEXITCODE -ne 0) {
            throw 'Local Redroid failed to start'
        }
        Write-Output "Profile: $Profile"
        Write-Output "Windows ADB endpoint: 127.0.0.1:$adbPort"
    }
    'Stop' {
        Invoke-LinuxManager -ManagerAction stop
        if ($LASTEXITCODE -ne 0) {
            throw 'Local Redroid failed to stop cleanly'
        }
        if (-not (Test-ManagedContainerRunning)) {
            Stop-KeepAlive
        }
    }
    'Status' {
        Initialize-BinderFs
        Invoke-LinuxManager -ManagerAction status
        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to read local Redroid status'
        }
        Write-Output "profile=$Profile"
        Write-Output "wsl_keepalive=$(Test-KeepAlive)"
    }
}
