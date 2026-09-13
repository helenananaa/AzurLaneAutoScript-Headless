[CmdletBinding()]
param(
    [ValidateSet('Start', 'Stop', 'Status', 'RestartGame', 'Reconnect')]
    [string]$Action = 'Status',
    [string]$Distro = 'ALAS-Android-Build',
    [string]$User = 'alas-kvm-build',
    [string]$Config,
    [string]$Domain = 'E:\Runtime\ALAS\android-build-domain.kvm.local.json',
    [string]$Profile,
    [switch]$AndroidOnly
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $Config) { $Config = Join-Path $repoRoot 'integration\runtime\local-kvm-20260907\runtime-config.json' }
if (-not $Profile) { $Profile = Join-Path $repoRoot 'integration\runtime\kvm-image-build-profile.example.json' }
if ($Action -eq 'Start') {
    & 'E:\Runtime\ALAS\Mount-ALASBuildDisks.ps1' | Out-Host
}
$windowsPaths = @((Join-Path $repoRoot 'scripts\python\manage_kvm_local_dev.py'), $Config, $Domain, $Profile) |
    ForEach-Object { (Resolve-Path -LiteralPath $_).Path.Replace('\', '/') }
# Cross the Windows/WSL boundary once; keep path arguments out of shell code.
$pathCode = @'
import json, subprocess, sys
print(json.dumps([subprocess.check_output(["wslpath", "-a", "-u", p], text=True).strip() for p in sys.argv[1:]]))
'@
$converted = & wsl.exe -d $Distro -u $User --exec /opt/alas-build-tools/bin/python -c $pathCode @windowsPaths
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve the KVM paths inside WSL' }
$wslPaths = ($converted | Out-String) | ConvertFrom-Json
$manager, $configPath, $domainPath, $profilePath = $wslPaths
$common = @('--config', $configPath, '--domain', $domainPath, '--profile', $profilePath)
function Invoke-Manager([string]$operation, [string[]]$extra = @()) {
    $output = & wsl.exe -d $Distro -u $User --exec /opt/alas-build-tools/bin/python $manager $operation @common @extra
    if ($LASTEXITCODE -ne 0) { throw "KVM $operation failed; inspect the error above." }
    return ($output | Out-String).Trim()
}
switch ($Action) {
    'Status' { Invoke-Manager 'status' }
    'Stop' { Invoke-Manager 'stop' }
    'RestartGame' { Invoke-Manager 'ready' }
    'Reconnect' { Invoke-Manager 'reconnect' }
    'Start' {
        $current = (Invoke-Manager 'status') | ConvertFrom-Json
        if ($current.running) {
            if ($current.state -in @('adb-disconnected', 'adb-unavailable')) {
                Invoke-Manager 'reconnect'
                break
            }
            $current | ConvertTo-Json -Depth 8
            break
        }
        $logRoot = Join-Path $repoRoot 'artifacts\local-kvm'
        New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
        $stamp = Get-Date -Format 'yyyyMMddTHHmmssfff'
        $stdout = Join-Path $logRoot "launcher-$stamp.stdout.log"
        $stderr = Join-Path $logRoot "launcher-$stamp.stderr.log"
        # The hidden foreground WSL client waits for the service, keeping WSL
        # alive without an unrelated forever-running sleep or scheduled task.
        $arguments = @('-d', $Distro, '-u', $User, '--exec', '/opt/alas-build-tools/bin/python', $manager, 'serve') + $common
        $quoted = $arguments | ForEach-Object {
            if ($_ -match '["\r\n]') { throw 'Unsupported quote/newline in launch argument' }
            if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
        }
        $launcher = Start-Process -FilePath wsl.exe -ArgumentList ($quoted -join ' ') -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        $deadline = (Get-Date).AddSeconds(90)
        do {
            Start-Sleep -Seconds 1
            $launcher.Refresh()
            # Only service existence matters here. The ready operation owns
            # ADB/framework/network waits and the final fresh guest status.
            $current = (Invoke-Manager 'status' @('--service-only')) | ConvertFrom-Json
            if ($current.state -eq 'failed') {
                throw "KVM startup failed: result=$($current.service.Result), exit=$($current.service.ExecMainStatus); see $($current.failure_log) or journalctl -u $($current.unit)"
            }
            if ($current.running) { break }
            if ($launcher.HasExited) { throw "KVM launcher exited; see $stderr" }
        } while ((Get-Date) -lt $deadline)
        if (-not $current.running) { throw "KVM service did not start; see $stderr" }
        if ($AndroidOnly) { Invoke-Manager 'ready' @('--android-only') }
        else { Invoke-Manager 'ready' }
    }
}
