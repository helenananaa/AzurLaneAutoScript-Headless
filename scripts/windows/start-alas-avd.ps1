# Start the existing game AVD; never create, wipe, stop or restart it here.
[CmdletBinding()]
param(
    [string]$AndroidSdkRoot = 'H:\Unity\Editor\Data\PlaybackEngines\AndroidPlayer\SDK',
    [string]$Adb = '',
    [string]$AvdHome = 'E:\Runtime\AndroidAVD',
    [string]$AvdName = 'alas_game_api32_x64',
    [Parameter(Mandatory = $true)][ValidateRange(5554, 5680)][int]$ConsolePort,
    [ValidateRange(1, 65535)][int]$AdbServerPort = 5037,
    [string]$DnsServer = '',
    [ValidateSet('Auto', 'Off')][string]$ClockMode = 'Auto',
    [string]$LogDirectory = (Join-Path $PSScriptRoot '..\..\artifacts\avd-launch'),
    [switch]$PlanOnly
)

$ErrorActionPreference = 'Stop'
if (-not $Adb) { $Adb = Join-Path $AndroidSdkRoot 'platform-tools\adb.exe' }
& (Join-Path $PSScriptRoot 'start-android-image-foundation-avd.ps1') `
    -AndroidSdkRoot $AndroidSdkRoot -Adb $Adb -AvdHome $AvdHome -AvdName $AvdName `
    -ConsolePort $ConsolePort -AdbServerPort $AdbServerPort -DnsServer $DnsServer `
    -ClockMode $ClockMode -LogDirectory $LogDirectory -PlanOnly:$PlanOnly
