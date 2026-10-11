[CmdletBinding()]
param(
    [string]$AndroidSdkRoot = 'H:\Unity\Editor\Data\PlaybackEngines\AndroidPlayer\SDK',
    [string]$Adb = 'F:\platform-tools\adb.exe',
    [string]$AvdHome = 'H:\AndroidAVDImageFoundation',
    [string]$AvdName = 'alas_update_lab_api32_x64',
    [int]$ApiLevel = 32,
    [ValidateSet('x86_64')][string]$Abi = 'x86_64',
    [ValidateRange(5554, 5680)][int]$ConsolePort = 5620,
    [ValidateRange(1, 65535)][int]$AdbServerPort = 5037,
    [string]$DnsServer = '',
    [ValidateSet('Auto', 'Off')][string]$ClockMode = 'Auto',
    [string]$LogDirectory = '',
    [switch]$CreateIfMissing,
    [switch]$PlanOnly
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'whpx-clock.ps1')
if (($ConsolePort % 2) -ne 0) {
    throw 'Android emulator console port must be even'
}
$resolvedSdk = (Resolve-Path -LiteralPath $AndroidSdkRoot).Path
$resolvedAdb = (Resolve-Path -LiteralPath $Adb).Path
$resolvedAvdHome = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($AvdHome)
if ([IO.Path]::GetPathRoot($resolvedAvdHome).TrimEnd('\') -eq $resolvedAvdHome.TrimEnd('\')) {
    throw 'AVD home cannot be a drive root'
}
$emulator = Join-Path $resolvedSdk 'emulator\emulator.exe'
$avdManager = Get-ChildItem (Join-Path $resolvedSdk 'cmdline-tools') -Recurse -Filter avdmanager.bat |
    Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
foreach ($required in @($emulator, $avdManager)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required Android tool is missing: $required"
    }
}

$package = "system-images;android-$ApiLevel;default;$Abi"
$systemImage = Join-Path $resolvedSdk "system-images\android-$ApiLevel\default\$Abi\system.img"
if (-not (Test-Path -LiteralPath $systemImage -PathType Leaf)) {
    throw "Pinned system image is missing: $package"
}
$avdDirectory = Join-Path $resolvedAvdHome "$AvdName.avd"
if (-not (Test-Path -LiteralPath $avdDirectory -PathType Container)) {
    if (-not $CreateIfMissing -or $PlanOnly) {
        throw 'Dedicated AVD is missing; rerun with -CreateIfMissing'
    }
    New-Item -ItemType Directory -Path $resolvedAvdHome -Force | Out-Null
    $env:ANDROID_SDK_ROOT = $resolvedSdk
    $env:ANDROID_HOME = $resolvedSdk
    $env:ANDROID_AVD_HOME = $resolvedAvdHome
    'no' | & $avdManager create avd --name $AvdName --package $package --device pixel_2 --force | Out-Host
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $avdDirectory)) {
        throw 'avdmanager did not create the dedicated AVD'
    }
}

$config = Get-Content -LiteralPath (Join-Path $avdDirectory 'config.ini') -Raw
$expectedImageDirectory = "system-images\android-$ApiLevel\default\$Abi\"
$imageDirectoryPattern = 'image\.sysdir\.1\s*=\s*' + [regex]::Escape($expectedImageDirectory)
if ($config -notmatch $imageDirectoryPattern) {
    throw 'Existing AVD does not match the requested system image identity'
}
$serial = "emulator-$ConsolePort"
if (-not $PlanOnly) {
    $existing = & $resolvedAdb -P $AdbServerPort -s $serial get-state 2>$null
    if ($existing -eq 'device') {
        $runningAvd = @(& $resolvedAdb -P $AdbServerPort -s $serial emu avd name 2>$null) |
            Where-Object { $_ -and $_ -ne 'OK' } | Select-Object -First 1
        if ($runningAvd -ne $AvdName) {
            throw "Serial $serial belongs to a different AVD: $runningAvd"
        }
        $clocksource = @(& $resolvedAdb -P $AdbServerPort -s $serial shell cat /sys/devices/system/clocksource/clocksource0/current_clocksource 2>$null)
        if ($LASTEXITCODE -ne 0) { $clocksource = @() }
        [ordered]@{
            outcome = 'already-running'
            serial = $serial
            avd_name = $runningAvd
            avd_home = $resolvedAvdHome
            adb_server_port = $AdbServerPort
            package = $package
            clocksource = ($clocksource -join '').Trim()
            clock_configuration_applied = $false
            note = 'Existing AVD was not restarted; new launch settings apply only to a cold start.'
            system_image_sha256 = (Get-FileHash -LiteralPath $systemImage -Algorithm SHA256).Hash.ToLowerInvariant()
        } |
            ConvertTo-Json
        exit 0
    }
    $listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in @($ConsolePort, $ConsolePort + 1) }
    if ($listeners) {
        throw "Emulator console/ADB port is already in use: $ConsolePort"
    }
}

$clock = Get-EmulatorClockConfiguration -Emulator $emulator -Mode $ClockMode
$arguments = @(
    '-avd', $AvdName, '-port', $ConsolePort, '-no-window', '-no-audio',
    '-no-boot-anim', '-no-snapshot', '-gpu', 'swiftshader_indirect', '-accel', 'on',
    '-camera-back', 'none', '-camera-front', 'none', '-no-metrics'
)
if ($DnsServer) { $arguments += @('-dns-server', $DnsServer) }
if ($LogDirectory) { $arguments += '-show-kernel' }
# -qemu consumes the remainder of the command line: it must stay last.
$arguments += $clock.arguments
if ($PlanOnly) {
    [ordered]@{
        outcome = 'planned'
        emulator = $emulator
        arguments = $arguments
        avd_home = $resolvedAvdHome
        avd_name = $AvdName
        serial_requested = $serial
        adb_server_port = $AdbServerPort
        log_directory = $LogDirectory
        clock = $clock
        clocksource_verified = $false
    } | ConvertTo-Json -Depth 5
    exit 0
}

$env:ANDROID_SDK_ROOT = $resolvedSdk
$env:ANDROID_HOME = $resolvedSdk
$env:ANDROID_AVD_HOME = $resolvedAvdHome
$env:ANDROID_ADB_SERVER_PORT = [string]$AdbServerPort
$startOptions = @{
    FilePath = $emulator
    ArgumentList = (ConvertTo-WindowsNativeArguments -Arguments $arguments)
    WindowStyle = 'Hidden'
    PassThru = $true
}
if ($LogDirectory) {
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    $logPrefix = Join-Path (Resolve-Path -LiteralPath $LogDirectory).Path (Get-Date -Format 'yyyyMMdd-HHmmss-fffffff')
    $startOptions.RedirectStandardOutput = "$logPrefix.stdout.log"
    $startOptions.RedirectStandardError = "$logPrefix.stderr.log"
}
$process = Start-Process @startOptions
[ordered]@{
    outcome = 'started'
    pid = $process.Id
    serial = $serial
    avd_home = $resolvedAvdHome
    avd_name = $AvdName
    adb_server_port = $AdbServerPort
    package = $package
    arguments = $arguments
    clock = $clock
    clocksource_verified = $false
    stdout_log = $startOptions.RedirectStandardOutput
    stderr_log = $startOptions.RedirectStandardError
    system_image_sha256 = (Get-FileHash -LiteralPath $systemImage -Algorithm SHA256).Hash.ToLowerInvariant()
} | ConvertTo-Json -Depth 5
