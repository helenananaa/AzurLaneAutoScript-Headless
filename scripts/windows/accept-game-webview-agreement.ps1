[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Serial,
    [string]$GamePackage = 'com.bilibili.azurlane',
    [string]$AgreementActivity = 'com.base.gsc_agreement_library.AgreementWebActivity',
    [string]$MainActivity = 'com.manjuu.azurlane.MainActivity',
    [string]$ExpectedTitle = '',
    [ValidateRange(5, 60)][int]$TransitionTimeoutSeconds = 30,
    [ValidateRange(10, 120)][int]$PreClickObservationSeconds = 15,
    [ValidateRange(10, 180)][int]$PostClickObservationSeconds = 60,
    [string]$OutputRoot = ''
)

$ErrorActionPreference = 'Stop'
$adb = (Get-Command adb -ErrorAction Stop).Source
$python = (Get-Command python -ErrorAction Stop).Source
$sdkAgreementTitle = 'sdk' + [char]0x534f + [char]0x8bae
if ([string]::IsNullOrWhiteSpace($ExpectedTitle)) {
    $ExpectedTitle = $sdkAgreementTitle
}
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$cdpHelper = Join-Path $repoRoot 'scripts\python\webview_agreement_cdp.py'
if (-not (Test-Path -LiteralPath $cdpHelper -PathType Leaf)) {
    throw "WebView CDP helper is missing: $cdpHelper"
}
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $repoRoot 'evidence'
}
$capturedAt = [DateTimeOffset]::UtcNow
$captureName = 'webview-agreement-{0}-{1}' -f $capturedAt.ToString('yyyyMMddTHHmmssZ'),
    ($Serial -replace '[^A-Za-z0-9._-]', '_')
$outputDirectory = Join-Path $OutputRoot $captureName
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

function Invoke-Adb {
    param([Parameter(Mandatory = $true)][string[]]$Arguments, [switch]$AllowFailure)
    $previousErrorActionPreference = $ErrorActionPreference
    if ($AllowFailure) { $ErrorActionPreference = 'Continue' }
    try {
        $lines = @(& $adb @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $text = ($lines | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "adb $($Arguments -join ' ') failed ($exitCode): $text"
    }
    return $text
}

function Write-JsonFile {
    param([Parameter(Mandatory = $true)][string]$Path,
          [Parameter(Mandatory = $true)]$Value)
    [IO.File]::WriteAllText(
        $Path,
        (($Value | ConvertTo-Json -Depth 12) + [Environment]::NewLine),
        [Text.UTF8Encoding]::new($false)
    )
}

function Get-ForegroundComponent {
    $activities = Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'dumpsys', 'activity',
        'activities')
    $line = $activities -split "`r?`n" | Where-Object {
        $_ -match '(?:topResumedActivity=|mResumedActivity:)'
    } | Select-Object -First 1
    if ($line -match 'u\d+\s+([^\s}]+/[^\s}]+)') { return $Matches[1] }
    return $null
}

$pidText = (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'pidof', $GamePackage)).Trim()
if ($pidText -notmatch '^\d+$') { throw 'expected exactly one running game PID' }
$gamePid = [int]$pidText
$expectedAgreement = "$GamePackage/$AgreementActivity"
$expectedMain = "$GamePackage/$MainActivity"
if ((Get-ForegroundComponent) -ne $expectedAgreement) {
    throw "refusing agreement action because $expectedAgreement is not foreground"
}

$unixSockets = Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'cat', '/proc/net/unix')
$socketName = "webview_devtools_remote_$gamePid"
$socketMatches = @($unixSockets -split "`r?`n" | Where-Object {
    $_ -match "@$([regex]::Escape($socketName))$"
})
if ($socketMatches.Count -ne 1) {
    throw "expected exactly one @$socketName socket, found $($socketMatches.Count)"
}

$forwardPort = $null
$passed = $false
$caughtError = $null
try {
    $forwardPort = [int](Invoke-Adb -Arguments @('-s', $Serial, 'forward', 'tcp:0',
        "localabstract:$socketName")).Trim()
    $targets = @(Invoke-RestMethod -Uri "http://127.0.0.1:$forwardPort/json")
    $matchingTargets = @($targets | Where-Object {
        $_.type -eq 'page' -and $_.title -ceq $ExpectedTitle -and
        -not [string]::IsNullOrWhiteSpace([string]$_.webSocketDebuggerUrl)
    })
    if ($matchingTargets.Count -ne 1) {
        throw "expected exactly one visible $ExpectedTitle WebView target"
    }
    $preClickLog = Invoke-Adb -Arguments @('-s', $Serial, 'logcat', '-d')
    Start-Sleep -Seconds $PreClickObservationSeconds
    if ((Get-ForegroundComponent) -ne $expectedAgreement -or
        (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'pidof', $GamePackage)).Trim() -ne
            "$gamePid") {
        throw 'agreement state changed during the pre-click observation window'
    }

    $clickedAt = [DateTimeOffset]::UtcNow
    $env:NO_PROXY = '127.0.0.1,localhost'
    $env:no_proxy = '127.0.0.1,localhost'
    $cdpLines = @(& $python $cdpHelper --endpoint "http://127.0.0.1:$forwardPort" `
        --expected-title $ExpectedTitle --click 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "WebView CDP helper failed: $($cdpLines -join [Environment]::NewLine)"
    }
    $cdpResult = ($cdpLines -join [Environment]::NewLine) | ConvertFrom-Json
    $matchingTarget = $cdpResult.target
    $dom = $cdpResult.dom
    $clickResult = $cdpResult.action
    if ($clickResult.clicked -ne $true -or [int]$clickResult.count -ne 1) {
        throw 'CDP did not confirm the unique agreement action'
    }

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TransitionTimeoutSeconds)
    do {
        Start-Sleep -Milliseconds 500
        $foreground = Get-ForegroundComponent
        $postPid = (Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'pidof', $GamePackage) `
            -AllowFailure).Trim()
        if ($foreground -eq $expectedMain -and $postPid -eq "$gamePid") { break }
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    if ($foreground -ne $expectedMain -or $postPid -ne "$gamePid") {
        throw 'agreement click did not return to MainActivity with the same game PID'
    }

    $postDeadline = [DateTimeOffset]::UtcNow.AddSeconds($PostClickObservationSeconds)
    do {
        Start-Sleep -Seconds 2
        if ((Invoke-Adb -Arguments @('-s', $Serial, 'shell', 'pidof', $GamePackage) `
            -AllowFailure).Trim() -ne "$gamePid") {
            throw 'game PID changed during the post-click observation window'
        }
    } while ([DateTimeOffset]::UtcNow -lt $postDeadline)
    $postClickLog = Invoke-Adb -Arguments @('-s', $Serial, 'logcat', '-d')
    $fatalPattern = 'Fatal signal|FATAL EXCEPTION|destroyed mutex|Abort message'
    if ($postClickLog -match $fatalPattern) {
        throw 'fatal marker appeared during the agreement transition'
    }

    $manifest = [ordered]@{
        schema = 'alas-headless.webview-agreement/v1'
        captured_at_utc = $capturedAt.ToString('o')
        clicked_at_utc = $clickedAt.ToString('o')
        serial = $Serial
        package = $GamePackage
        pid = $gamePid
        agreement_activity = $expectedAgreement
        postcondition_activity = $foreground
        devtools_socket = $socketName
        target = [ordered]@{
            id = $matchingTarget.id
            title = $matchingTarget.title
            url = $matchingTarget.url
        }
        dom = $dom
        action = $clickResult
        pre_click_observation_seconds = $PreClickObservationSeconds
        post_click_observation_seconds = $PostClickObservationSeconds
        fatal_markers = @()
        passed = $true
    }
    Write-JsonFile -Path (Join-Path $outputDirectory 'manifest.json') -Value $manifest
    [IO.File]::WriteAllText(
        (Join-Path $outputDirectory 'logcat.pre-click.txt'), $preClickLog,
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        (Join-Path $outputDirectory 'logcat.post-click.txt'), $postClickLog,
        [Text.UTF8Encoding]::new($false)
    )
    $passed = $true
    Write-Output $outputDirectory
}
catch {
    $caughtError = $_
    throw
}
finally {
    if ($forwardPort) {
        Invoke-Adb -Arguments @('-s', $Serial, 'forward', '--remove', "tcp:$forwardPort") `
            -AllowFailure | Out-Null
    }
    if (-not $passed) {
        $failure = [ordered]@{
            schema = 'alas-headless.webview-agreement-failure/v1'
            captured_at_utc = $capturedAt.ToString('o')
            serial = $Serial
            package = $GamePackage
            pid = $gamePid
            foreground = Get-ForegroundComponent
            failure = if ($caughtError) { $caughtError.Exception.Message } else { 'unknown' }
            passed = $false
        }
        Write-JsonFile -Path (Join-Path $outputDirectory 'manifest.failed.json') -Value $failure
    }
}
