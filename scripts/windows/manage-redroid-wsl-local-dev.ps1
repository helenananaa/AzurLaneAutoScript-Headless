[CmdletBinding()]
param(
    [ValidateSet('Start', 'Stop', 'Status', 'Config')]
    [string]$Action = 'Status',

    [ValidateSet('Project', 'Stock', 'Api31')]
    [string]$Profile = 'Project',

    [string]$Distro = 'Ubuntu-22.04',

    [string]$ProjectArtifactDirectory,

    [ValidatePattern('^[a-z][a-z0-9-]{0,47}$')]
    [string]$ProjectInstance = 'projectlocal',

    [ValidateRange(1, 65535)]
    [int]$ProjectAdbPort = 5556
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
    if ([string]::IsNullOrWhiteSpace($ProjectArtifactDirectory)) {
        $workspaceParent = Split-Path -Parent $repoRoot
        $ProjectArtifactDirectory = Join-Path $workspaceParent 'AzurLaneAutoScript-Headless-localdata\redroid-x86_64-candidates\current'
    }
    $projectArtifactDirectoryItem = Get-Item -LiteralPath $ProjectArtifactDirectory -ErrorAction SilentlyContinue
    if ($null -eq $projectArtifactDirectoryItem -or -not $projectArtifactDirectoryItem.PSIsContainer) {
        throw "Project artifact directory is missing: $ProjectArtifactDirectory"
    }
    $projectArtifactDirectoryResolved = $projectArtifactDirectoryItem.FullName
    $projectIdentityPath = Join-Path $projectArtifactDirectoryResolved 'redroid-x86_64.oci-build.json'
    $projectOciWindows = Join-Path $projectArtifactDirectoryResolved 'redroid-x86_64.oci.tar'
    if (-not (Test-Path -LiteralPath $projectIdentityPath -PathType Leaf)) {
        throw "Project OCI identity is missing: $projectIdentityPath"
    }
    if (-not (Test-Path -LiteralPath $projectOciWindows -PathType Leaf)) {
        throw "Project OCI archive is missing: $projectOciWindows"
    }
    try {
        $projectIdentity = Get-Content -LiteralPath $projectIdentityPath -Raw | ConvertFrom-Json
    } catch {
        throw "Project OCI identity is malformed: $projectIdentityPath"
    }
    if ($projectIdentity.schema -ne 'alas-headless.redroid-oci-build/v1' -or
        $projectIdentity.abi -ne 'x86_64' -or
        $projectIdentity.architecture -ne 'amd64' -or
        $projectIdentity.game_delivery -ne 'external-install' -or
        $projectIdentity.game_artifact_included -ne $false) {
        throw "Project OCI identity does not describe an x86_64 external-install candidate"
    }
    $projectOciSha256 = [string]$projectIdentity.archive.sha256
    $projectManifestDigest = [string]$projectIdentity.manifest_digest
    if ($projectOciSha256 -notmatch '^[0-9a-f]{64}$') {
        throw 'Project OCI archive identity has an invalid SHA-256'
    }
    if ($projectManifestDigest -notmatch '^sha256:[0-9a-f]{64}$') {
        throw 'Project OCI identity has an invalid manifest digest'
    }
    $projectOciItem = Get-Item -LiteralPath $projectOciWindows
    if ([int64]$projectIdentity.archive.bytes -ne $projectOciItem.Length) {
        throw 'Project OCI archive size does not match its identity'
    }
    $projectOciForWslPath = $projectOciWindows.Replace('\', '/')
    $projectOciOutput = & wsl.exe -d $Distro -- wslpath -a -u $projectOciForWslPath
    if ($LASTEXITCODE -ne 0 -or $null -eq $projectOciOutput) {
        throw "Failed to resolve the WSL path for $projectOciWindows"
    }
    $projectOci = ($projectOciOutput | Out-String).Trim()
    $profileEnvironment = @(
        "ALAS_REDROID_LOCAL_CONTAINER=alas-redroid-wsl-$ProjectInstance",
        "ALAS_REDROID_LOCAL_IMAGE=$projectManifestDigest",
        "ALAS_REDROID_LOCAL_DATA_NAME=$ProjectInstance-data",
        "ALAS_REDROID_LOCAL_ADB_PORT=$ProjectAdbPort",
        'ALAS_REDROID_LOCAL_CONFIRM_IMMERSIVE=1',
        "ALAS_REDROID_LOCAL_OCI_TAR=$projectOci",
        "ALAS_REDROID_LOCAL_OCI_TAR_SHA256=$projectOciSha256"
    )
    $adbPort = $ProjectAdbPort
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
    $startInfo.UseShellExecute = $true
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $startInfo.CreateNoWindow = $true
    # Do not inherit a runtime executor's capture pipes: sleep infinity would
    # keep them open after this manager exits and make Start appear to hang.
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
    # Named Project instances created by this manager carry this label. Keep
    # legacy names below for containers created before labels were introduced.
    $named = & wsl.exe -d $Distro -- docker --host unix:///var/run/docker.sock --config $dockerConfig ps --filter 'label=io.github.alas-headless.runtime=redroid-wsl' --format '{{.Names}}'
    if ($LASTEXITCODE -ne 0) { throw 'Failed to inspect managed Redroid containers' }
    if (-not [string]::IsNullOrWhiteSpace(($named | Out-String))) { return $true }
    foreach ($name in @('alas-redroid-wsl-localdev', 'alas-redroid-wsl-projectdev', 'alas-redroid-wsl-projectlocal', 'alas-redroid-wsl-api31')) {
        $running = & wsl.exe -d $Distro -- docker --host unix:///var/run/docker.sock --config $dockerConfig container inspect --format '{{.State.Running}}' $name 2>$null
        if ($LASTEXITCODE -eq 0 -and ($running | Out-String).Trim() -eq 'true') {
            return $true
        }
    }
    return $false
}

switch ($Action) {
    'Config' {
        if ($Profile -ne 'Project') { throw 'Runtime config export currently supports Project only' }
        [ordered]@{
            schema = 'alas-headless.runtime-config/v1'
            backend = 'redroid'
            container_engine = 'wsl-docker'
            serial = "127.0.0.1:$adbPort"
            package = 'com.bilibili.azurlane'
            component = 'com.bilibili.azurlane/com.manjuu.azurlane.MainActivity'
            host_class = 'windows-wsl2-x86_64-redroid'
            container_id = "alas-redroid-wsl-$ProjectInstance"
            image_manifest_digest = $projectManifestDigest
            userdata_path = "$linuxHome/.local/share/alas-redroid/$ProjectInstance-data"
            project_instance = $ProjectInstance
            manager_script = $PSCommandPath
            project_artifact_directory = $projectArtifactDirectoryResolved
            distro = $Distro
            adb = (Get-Command adb -ErrorAction Stop).Source
        } | ConvertTo-Json -Depth 4
    }
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
