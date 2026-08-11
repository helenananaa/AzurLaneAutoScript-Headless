[CmdletBinding()]
param(
    [string]$AndroidSdkRoot = 'H:\Unity\Editor\Data\PlaybackEngines\AndroidPlayer\SDK',
    [string]$Adb = 'F:\platform-tools\adb.exe',
    [string]$AvdHome = 'H:\AndroidAVDImageFoundation',
    [string]$AvdName = 'alas_update_lab_api32_x64',
    [int]$ApiLevel = 32,
    [ValidateSet('x86_64')][string]$Abi = 'x86_64',
    [ValidateRange(5554, 5680)][int]$ConsolePort = 5620,
    [switch]$CreateIfMissing
)

$ErrorActionPreference = 'Stop'
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
New-Item -ItemType Directory -Path $resolvedAvdHome -Force | Out-Null
$avdDirectory = Join-Path $resolvedAvdHome "$AvdName.avd"
if (-not (Test-Path -LiteralPath $avdDirectory -PathType Container)) {
    if (-not $CreateIfMissing) {
        throw 'Dedicated AVD is missing; rerun with -CreateIfMissing'
    }
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
$existing = & $resolvedAdb -s $serial get-state 2>$null
if ($existing -eq 'device') {
    $runningAvd = @(& $resolvedAdb -s $serial emu avd name 2>$null) |
        Where-Object { $_ -and $_ -ne 'OK' } | Select-Object -First 1
    if ($runningAvd -ne $AvdName) {
        throw "Serial $serial belongs to a different AVD: $runningAvd"
    }
    [ordered]@{
        outcome = 'already-running'
        serial = $serial
        avd_name = $runningAvd
        avd_home = $resolvedAvdHome
        package = $package
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

$env:ANDROID_SDK_ROOT = $resolvedSdk
$env:ANDROID_HOME = $resolvedSdk
$env:ANDROID_AVD_HOME = $resolvedAvdHome
$arguments = @(
    '-avd', $AvdName, '-port', $ConsolePort, '-no-window', '-no-audio',
    '-no-boot-anim', '-no-snapshot', '-gpu', 'swiftshader_indirect', '-accel', 'on',
    '-camera-back', 'none', '-camera-front', 'none', '-no-metrics'
)
$process = Start-Process -FilePath $emulator -ArgumentList $arguments -WindowStyle Hidden -PassThru
[ordered]@{
    outcome = 'started'
    pid = $process.Id
    serial = $serial
    avd_home = $resolvedAvdHome
    package = $package
    system_image_sha256 = (Get-FileHash -LiteralPath $systemImage -Algorithm SHA256).Hash.ToLowerInvariant()
} | ConvertTo-Json
