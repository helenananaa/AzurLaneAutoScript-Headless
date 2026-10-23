[CmdletBinding(DefaultParameterSetName = 'Bounded')]
param(
    [Parameter(Mandatory = $true)]
    [string]$BundleDirectory,

    [Parameter(ParameterSetName = 'Bounded')]
    [ValidateRange(1, 2147483647)]
    [int]$MaxTasks = 3,

    [Parameter(Mandatory = $true, ParameterSetName = 'Continuous')]
    [switch]$Continuous,

    [switch]$RestartBeforeLoop,
    [switch]$ContinueAfterFailure,
    [string]$StopFile,
    [string]$Output,
    [switch]$Plan
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$bundleRoot = (Resolve-Path -LiteralPath $BundleDirectory).Path
$manifest = Get-Content -Raw -LiteralPath (Join-Path $bundleRoot 'manifest.json') | ConvertFrom-Json
$runner = Join-Path $repoRoot 'scripts\python\run_alas_configured_scheduler_live.py'
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $bundleRoot ('operator-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json')
}

# Delegate task selection, timing, persistence and recovery to the existing runner.
$runnerArguments = @(
    $runner,
    '--alas-root', [string]$manifest.alas_root,
    '--seed-config', [string]$manifest.scheduler_seed,
    '--persistent-config', [string]$manifest.scheduler_config,
    '--driver-revision', [string]$manifest.observer.revision,
    '--output', $Output
)
if ($Continuous) {
    $runnerArguments += '--continuous'
} else {
    $runnerArguments += @('--max-tasks', [string]$MaxTasks)
}
if ($RestartBeforeLoop) {
    $runnerArguments += '--restart-before-loop'
}
if ($ContinueAfterFailure) {
    $runnerArguments += '--continue-after-failure'
}
if (-not [string]::IsNullOrWhiteSpace($StopFile)) {
    $runnerArguments += @('--stop-file', [IO.Path]::GetFullPath($StopFile))
}
foreach ($budget in $manifest.scheduler_budgets) {
    $runnerArguments += @('--budget', [string]$budget)
}

if ($Plan) {
    [ordered]@{
        repository = $repoRoot
        executable = $manifest.python
        arguments = $runnerArguments
        adb_directory = $manifest.adb_directory
        executes_game = $false
    } | ConvertTo-Json -Depth 4
    return
}

$savedPath = $env:PATH
$savedEncoding = $env:PYTHONIOENCODING
try {
    if (-not [string]::IsNullOrWhiteSpace($manifest.adb_directory)) {
        $env:PATH = [string]$manifest.adb_directory + [IO.Path]::PathSeparator + $env:PATH
    }
    $env:PYTHONIOENCODING = 'utf-8'
    & ([string]$manifest.python) @runnerArguments
    $runnerExitCode = $LASTEXITCODE
} finally {
    $env:PATH = $savedPath
    $env:PYTHONIOENCODING = $savedEncoding
}
exit $runnerExitCode
