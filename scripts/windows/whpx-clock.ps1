# Shared by Windows AVD launchers. Dot-sourcing only defines functions.
function Get-WhpxProcessorClockFrequency {
    if (-not ('AlasHeadless.WhpxClock' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace AlasHeadless {
    public static class WhpxClock {
        [DllImport("WinHvPlatform.dll", ExactSpelling = true)]
        public static extern int WHvGetCapability(
            uint capability, out ulong frequency, uint size, out uint written);
    }
}
'@
    }
    [uint64]$frequency = 0
    [uint32]$written = 0
    $result = [AlasHeadless.WhpxClock]::WHvGetCapability(
        0x1004, [ref]$frequency, 8, [ref]$written)
    if ($result -lt 0 -or $written -ne 8 -or $frequency -eq 0) {
        throw "WHvGetCapability(ProcessorClockFrequency) failed: HRESULT=$result, bytes=$written, Hz=$frequency"
    }
    return $frequency
}

function Get-EmulatorClockConfiguration {
    param(
        [Parameter(Mandatory = $true)][string]$Emulator,
        [ValidateSet('Auto', 'Off')][string]$Mode = 'Auto'
    )
    $configuration = [ordered]@{
        mode = $Mode
        status = 'disabled'
        acceleration_check = $null
        frequency_hz = $null
        tsc_early_khz = $null
        arguments = @()
    }
    if ($Mode -eq 'Off') {
        return [pscustomobject]$configuration
    }

    $probe = @(& $Emulator -accel-check 2>&1)
    $probeExit = $LASTEXITCODE
    $probeText = ($probe | ForEach-Object { $_.ToString() }) -join "`n"
    $configuration.acceleration_check = $probeText
    if ($probeExit -ne 0) {
        $configuration.status = 'acceleration-check-failed'
        Write-Warning 'Emulator acceleration check failed; no WHPX clock override was generated.'
        return [pscustomobject]$configuration
    }
    if ($probeText -notmatch '\bWHPX\b') {
        $configuration.status = 'not-whpx'
        return [pscustomobject]$configuration
    }

    try {
        [uint64]$frequency = Get-WhpxProcessorClockFrequency
        # tsc_early_khz is an unsigned int in the guest kernel. Round Hz to kHz.
        $khz = [math]::Floor(([decimal]$frequency + 500) / 1000)
        if ($frequency -eq 0 -or $khz -lt 1 -or $khz -gt [uint32]::MaxValue) {
            throw "WHPX frequency cannot be represented as tsc_early_khz: $frequency Hz"
        }
    } catch {
        throw "WHPX clock query failed; no emulator was launched by this clock helper. Retry the host query, or explicitly use -ClockMode Off to launch without the workaround. $($_.Exception.Message)"
    }
    $configuration.status = 'whpx-tsc'
    $configuration.frequency_hz = $frequency
    $configuration.tsc_early_khz = [uint32]$khz
    $configuration.arguments = @(
        '-qemu', '-append', "tsc_early_khz=$([uint32]$khz) clocksource=tsc"
    )
    return [pscustomobject]$configuration
}

function ConvertTo-WindowsNativeArguments {
    param([Parameter(Mandatory = $true)][AllowEmptyCollection()][AllowEmptyString()][string[]]$Arguments)
    # Start-Process joins ArgumentList with spaces. Quote each CRT argument so
    # the two kernel settings reach -append as one argument, including paths
    # containing spaces, quotes or trailing backslashes.
    $quoted = foreach ($argument in $Arguments) {
        $escaped = [regex]::Replace($argument, '(\\*)"', '$1$1\"')
        '"' + [regex]::Replace($escaped, '(\\+)$', '$1$1') + '"'
    }
    return $quoted -join ' '
}
