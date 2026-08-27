[CmdletBinding()]
param(
    [string]$Serial = '127.0.0.1:15555',
    [string]$GamePackage = 'com.bilibili.azurlane',
    [string]$GameComponent = 'com.bilibili.azurlane/com.manjuu.azurlane.MainActivity',
    [string]$AnglePackage = 'org.chromium.angle',
    [string]$AdbPath = '',
    [string]$ScrcpyPath = '',
    [switch]$RestoreOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Resolve-Executable {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$ExplicitPath,
        [Parameter(Mandatory = $true)]
        [string]$CommandName,
        [AllowEmptyString()]
        [string]$WinGetPattern = ''
    )

    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        $resolved = (Resolve-Path -LiteralPath $ExplicitPath).Path
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            throw "$CommandName executable is not a file: $resolved"
        }
        return $resolved
    }

    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    if (-not [string]::IsNullOrWhiteSpace($WinGetPattern)) {
        $packageRoot = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
        $candidates = @(
            Get-ChildItem -LiteralPath $packageRoot -Filter $CommandName -File -Recurse `
                -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -like $WinGetPattern } |
                Sort-Object -Property FullName -Descending
        )
        if ($candidates.Count -gt 0) {
            return $candidates[0].FullName
        }
    }

    throw "$CommandName was not found"
}

$adb = Resolve-Executable -ExplicitPath $AdbPath -CommandName 'adb.exe'

function Invoke-Adb {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$AdbArguments
    )

    $output = @(& $adb -s $Serial @AdbArguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "adb failed ($LASTEXITCODE): $($AdbArguments -join ' ')`n$($output -join "`n")"
    }
    return ($output -join "`n").Trim()
}

function Read-GlobalSetting {
    param([Parameter(Mandatory = $true)][string]$Name)

    $value = Invoke-Adb -AdbArguments @('shell', 'settings', 'get', 'global', $Name)
    if ([string]::IsNullOrWhiteSpace($value) -or $value -eq 'null') {
        return $null
    }
    return $value
}

function Write-GlobalSetting {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowNull()][string]$Value
    )

    if ($null -eq $Value) {
        [void](Invoke-Adb -AdbArguments @('shell', 'settings', 'delete', 'global', $Name))
    }
    else {
        [void](Invoke-Adb -AdbArguments @('shell', 'settings', 'put', 'global', $Name, $Value))
    }
}

function Restart-Game {
    [void](Invoke-Adb -AdbArguments @('shell', 'am', 'force-stop', $GamePackage))
    $startOutput = Invoke-Adb -AdbArguments @(
        'shell', 'am', 'start', '-W', '-n', $GameComponent,
        '--es', 'unity', '-force-gfx-st'
    )
    if ($startOutput -notmatch 'Status:\s+ok') {
        throw "game launch did not report Status: ok`n$startOutput"
    }
}

function Set-NullRouting {
    Write-GlobalSetting -Name 'angle_debug_package' -Value $AnglePackage
    Write-GlobalSetting -Name 'angle_gl_driver_selection_pkgs' -Value $GamePackage
    Write-GlobalSetting -Name 'angle_gl_driver_selection_values' -Value 'angle'
    Write-GlobalSetting -Name 'show_angle_in_use_dialog_box' -Value '0'
}

function Read-AngleRouting {
    return @{
        angle_debug_package = Read-GlobalSetting -Name 'angle_debug_package'
        angle_gl_driver_selection_pkgs = Read-GlobalSetting -Name 'angle_gl_driver_selection_pkgs'
        angle_gl_driver_selection_values = Read-GlobalSetting -Name 'angle_gl_driver_selection_values'
        show_angle_in_use_dialog_box = Read-GlobalSetting -Name 'show_angle_in_use_dialog_box'
    }
}

function Assert-NullRouting {
    $actual = Read-AngleRouting
    $expected = @{
        angle_debug_package = $AnglePackage
        angle_gl_driver_selection_pkgs = $GamePackage
        angle_gl_driver_selection_values = 'angle'
        show_angle_in_use_dialog_box = '0'
    }
    foreach ($name in $expected.Keys) {
        if ($actual[$name] -ne $expected[$name]) {
            throw "ANGLE NULL routing mismatch for ${name}: expected '$($expected[$name])', found '$($actual[$name])'"
        }
    }
}

function Assert-NativeRouting {
    $actual = Read-AngleRouting
    if (
        $actual['angle_gl_driver_selection_pkgs'] -ne $GamePackage -or
        $actual['angle_gl_driver_selection_values'] -ne 'native' -or
        $actual['show_angle_in_use_dialog_box'] -ne '0'
    ) {
        throw 'temporary native renderer routing was not applied exactly'
    }
}

function Wait-GamePackageRuntime {
    param([switch]$RequirePrivateAngle)

    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    do {
        try {
            $pidText = Invoke-Adb -AdbArguments @('shell', 'pidof', $GamePackage)
            $activities = Invoke-Adb -AdbArguments @('shell', 'dumpsys', 'activity', 'activities')
            $pidValues = @($pidText -split '\s+' | Where-Object { $_ -match '^[0-9]+$' })
            $foregroundPattern = '(?:topResumedActivity=|mResumedActivity:)\s*ActivityRecord\{[^\r\n}]*\s' +
                [regex]::Escape($GamePackage) + '/'
            if ($pidValues.Count -eq 1 -and $activities -match $foregroundPattern) {
                if (-not $RequirePrivateAngle) {
                    return [int]$pidValues[0]
                }
                try {
                    $maps = Invoke-Adb -AdbArguments @('shell', 'cat', "/proc/$($pidValues[0])/maps")
                    if (
                        $maps -match '/libEGL_alasx\.so(?:\s|$)' -and
                        $maps -match '/libGLESv2_alasx\.so(?:\s|$)'
                    ) {
                        return [int]$pidValues[0]
                    }
                }
                catch {
                    # Android 14 can deny shell access to another UID's proc
                    # maps. In that compatible case, require the observer's
                    # current-process log signature instead of weakening the
                    # exact package/PID/foreground checks above.
                    $observerLog = Invoke-Adb -AdbArguments @(
                        'logcat', '-d', '--pid', $pidValues[0], '-t', '400',
                        'ALAS_G3:I', '*:S'
                    )
                    if ($observerLog -match 'ALAS_G3_SNAPSHOT') {
                        return [int]$pidValues[0]
                    }
                }
            }
        }
        catch {
            # The package and proc maps can be briefly unavailable while the
            # exact game process is starting. The bounded retry remains typed
            # to this package and never falls back to screen coordinates.
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)

    if ($RequirePrivateAngle) {
        throw "game did not reach the exact foreground private-ANGLE NULL runtime: $GamePackage"
    }
    throw "game did not reach the exact foreground rendered runtime: $GamePackage"
}

$connectOutput = @(& $adb connect $Serial 2>&1)
if ($LASTEXITCODE -ne 0 -or ($connectOutput -join "`n") -notmatch '(already )?connected to') {
    throw "cannot connect to $Serial; verify the SSH tunnel first`n$($connectOutput -join "`n")"
}

if ((Invoke-Adb -AdbArguments @('get-state')) -ne 'device') {
    throw "ADB target is not ready: $Serial"
}

$installedPath = Invoke-Adb -AdbArguments @('shell', 'pm', 'path', $GamePackage)
if ($installedPath -notmatch '^package:') {
    throw "target package is not installed on ${Serial}: $GamePackage"
}

if ($RestoreOnly) {
    Set-NullRouting
    Assert-NullRouting
    Restart-Game
    $nullPid = Wait-GamePackageRuntime -RequirePrivateAngle
    Write-Host "Verified private ANGLE NULL in game PID $nullPid"
    Write-Host "Restored $GamePackage to ANGLE NULL on $Serial"
    exit 0
}

$scrcpy = Resolve-Executable `
    -ExplicitPath $ScrcpyPath `
    -CommandName 'scrcpy.exe' `
    -WinGetPattern '*\Genymobile.scrcpy_*\scrcpy-*\scrcpy.exe'

$settingNames = @(
    'angle_debug_package',
    'angle_gl_driver_selection_pkgs',
    'angle_gl_driver_selection_values',
    'show_angle_in_use_dialog_box'
)
$originalSettings = @{}
foreach ($settingName in $settingNames) {
    $originalSettings[$settingName] = Read-GlobalSetting -Name $settingName
}

try {
    Assert-NullRouting
}
catch {
    throw "The game is not currently pinned to ANGLE NULL. Run this script once with -RestoreOnly before opening rendered login. $($_.Exception.Message)"
}

try {
    Write-Host 'Switching the game to the system renderer for temporary interactive login...'
    Write-GlobalSetting -Name 'angle_gl_driver_selection_pkgs' -Value $GamePackage
    Write-GlobalSetting -Name 'angle_gl_driver_selection_values' -Value 'native'
    Write-GlobalSetting -Name 'show_angle_in_use_dialog_box' -Value '0'
    Assert-NativeRouting
    Restart-Game
    $renderedPid = Wait-GamePackageRuntime
    Write-Host "Verified temporary rendered game PID $renderedPid"

    Write-Host 'Close only the scrcpy window after login is complete; NULL routing will then be restored.'
    & $scrcpy `
        '--serial' $Serial `
        '--force-adb-forward' `
        '--no-audio' `
        '--no-clipboard-autosync' `
        '--max-size' '1280' `
        '--max-fps' '30' `
        '--window-title' 'Azur Lane - temporary rendered login'
    if ($LASTEXITCODE -ne 0) {
        throw "scrcpy exited with code $LASTEXITCODE"
    }
}
finally {
    Write-Host 'Restoring the verified ANGLE NULL routing and restarting the game...'
    foreach ($settingName in $settingNames) {
        Write-GlobalSetting -Name $settingName -Value $originalSettings[$settingName]
    }
    Assert-NullRouting
    Restart-Game
    $nullPid = Wait-GamePackageRuntime -RequirePrivateAngle
    Write-Host "Verified restored private ANGLE NULL in game PID $nullPid"
}
