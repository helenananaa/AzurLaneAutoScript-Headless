[CmdletBinding()]
param(
    [string]$AndroidSdkRoot = 'H:\Unity\Editor\Data\PlaybackEngines\AndroidPlayer\SDK',
    [string]$AndroidNdkRoot = 'H:\Unity\Editor\Data\PlaybackEngines\AndroidPlayer\NDK',
    [string]$JavaHome = 'D:\java\jdk-24',
    [string]$GradlePath = 'H:\program\AzurLaneAutoScript-Headless-localdata\AzurLaneAutoScript-Headless-arm64-venus\artifacts\toolchains\gradle-9.4.1\bin\gradle.bat',
    [string]$BundletoolJar,
    [string]$OutputRoot
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $repoRoot 'artifacts\android-update-lab'
}
if ([string]::IsNullOrWhiteSpace($BundletoolJar)) {
    $BundletoolJar = Join-Path $repoRoot 'artifacts\bundletool-all-1.18.3.jar'
}
$project = Join-Path $repoRoot 'probes\android-update-lab'
$output = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputRoot)
$gradleHome = Join-Path $output 'gradle-home'
$labKey = Join-Path $output 'alas-update-lab.jks'
$badKey = Join-Path $output 'alas-update-lab-wrong-signer.jks'
$storePassword = 'alas-update-lab-only'
$bundletoolSha256 = 'a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29'

foreach ($required in @(
    $GradlePath,
    (Join-Path $JavaHome 'bin\java.exe'),
    (Join-Path $JavaHome 'bin\keytool.exe'),
    (Join-Path $AndroidNdkRoot 'ndk-build.cmd'),
    (Join-Path $AndroidSdkRoot 'build-tools\36.0.0\zipalign.exe'),
    (Join-Path $AndroidSdkRoot 'build-tools\36.0.0\apksigner.bat'),
    $BundletoolJar
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required update-lab tool is missing: $required"
    }
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $BundletoolJar).Hash.ToLowerInvariant() -ne
    $bundletoolSha256) {
    throw 'bundletool SHA-256 differs from the pinned 1.18.3 artifact'
}

New-Item -ItemType Directory -Path $output, $gradleHome -Force | Out-Null

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $FilePath @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

function Ensure-TestKey {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Alias,
        [Parameter(Mandatory = $true)][string]$CommonName
    )
    if (Test-Path -LiteralPath $Path) {
        return
    }
    Invoke-Checked -FilePath (Join-Path $JavaHome 'bin\keytool.exe') -Arguments @(
        '-genkeypair', '-noprompt', '-keystore', $Path,
        '-storepass', $storePassword, '-keypass', $storePassword,
        '-alias', $Alias, '-dname', "CN=$CommonName, O=ALAS Headless Research",
        '-keyalg', 'RSA', '-keysize', '2048', '-validity', '3650'
    )
}

function Sign-Apk {
    param(
        [Parameter(Mandatory = $true)][string]$UnsignedApk,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$KeyStore,
        [Parameter(Mandatory = $true)][string]$Alias
    )
    $aligned = "$Destination.aligned"
    Invoke-Checked -FilePath (Join-Path $AndroidSdkRoot 'build-tools\36.0.0\zipalign.exe') `
        -Arguments @('-f', '-p', '4', $UnsignedApk, $aligned)
    Invoke-Checked -FilePath (Join-Path $AndroidSdkRoot 'build-tools\36.0.0\apksigner.bat') `
        -Arguments @(
            'sign', '--ks', $KeyStore, '--ks-pass', "pass:$storePassword",
            '--ks-key-alias', $Alias, '--key-pass', "pass:$storePassword",
            '--out', $Destination, $aligned
        )
    Remove-Item -LiteralPath $aligned
    Invoke-Checked -FilePath (Join-Path $AndroidSdkRoot 'build-tools\36.0.0\apksigner.bat') `
        -Arguments @('verify', '--verbose', '--print-certs', $Destination)
}

function Build-Version {
    param(
        [Parameter(Mandatory = $true)][int]$VersionCode,
        [Parameter(Mandatory = $true)][string]$VersionName
    )
    $previousJavaHome = $env:JAVA_HOME
    $previousAndroidSdkRoot = $env:ANDROID_SDK_ROOT
    try {
        $env:JAVA_HOME = $JavaHome
        $env:ANDROID_SDK_ROOT = $AndroidSdkRoot
        Invoke-Checked -FilePath $GradlePath -Arguments @(
            '--no-daemon', '--gradle-user-home', $gradleHome,
            '--project-dir', $project,
            '-PalasCompileSdk=android-35', '-PalasBuildTools=36.0.0',
            "-PalasNdkPath=$AndroidNdkRoot",
            '-PalasNdkVersion=23.1.7779620',
            '-PalasTargetSdk=32', "-PalasLabVersionCode=$VersionCode",
            "-PalasLabVersionName=$VersionName", 'clean',
            ':app:assembleRelease', ':app:bundleRelease'
        )
    }
    finally {
        $env:JAVA_HOME = $previousJavaHome
        $env:ANDROID_SDK_ROOT = $previousAndroidSdkRoot
    }
    $unsignedApk = Join-Path $project 'app\build\outputs\apk\release\app-release-unsigned.apk'
    $bundle = Join-Path $project 'app\build\outputs\bundle\release\app-release.aab'
    if (-not (Test-Path -LiteralPath $unsignedApk) -or
        -not (Test-Path -LiteralPath $bundle)) {
        throw "Gradle did not produce the version $VersionCode APK and AAB"
    }
    $destinationApk = Join-Path $output "update-lab-v$VersionCode.apk"
    $destinationBundle = Join-Path $output "update-lab-v$VersionCode.aab"
    Sign-Apk -UnsignedApk $unsignedApk -Destination $destinationApk `
        -KeyStore $labKey -Alias 'alas-update-lab'
    Copy-Item -LiteralPath $bundle -Destination $destinationBundle -Force
    return [ordered]@{
        version_code = $VersionCode
        apk = $destinationApk
        aab = $destinationBundle
    }
}

Ensure-TestKey -Path $labKey -Alias 'alas-update-lab' -CommonName 'ALAS Update Lab'
Ensure-TestKey -Path $badKey -Alias 'wrong-signer' -CommonName 'Wrong Signer Negative Control'

$v1 = Build-Version -VersionCode 1 -VersionName '1.0'
$v2 = Build-Version -VersionCode 2 -VersionName '2.0'

$wrongSignerApk = Join-Path $output 'update-lab-v2-wrong-signer.apk'
$unsignedV2 = Join-Path $project 'app\build\outputs\apk\release\app-release-unsigned.apk'
Sign-Apk -UnsignedApk $unsignedV2 -Destination $wrongSignerApk `
    -KeyStore $badKey -Alias 'wrong-signer'

$apks = Join-Path $output 'update-lab-v2.apks'
if (Test-Path -LiteralPath $apks) {
    Remove-Item -LiteralPath $apks
}
Invoke-Checked -FilePath (Join-Path $JavaHome 'bin\java.exe') -Arguments @(
    '-jar', $BundletoolJar, 'build-apks', "--bundle=$($v2.aab)", "--output=$apks",
    "--ks=$labKey", "--ks-pass=pass:$storePassword", '--ks-key-alias=alas-update-lab',
    "--key-pass=pass:$storePassword", '--overwrite'
)

$artifacts = @($v1.apk, $v1.aab, $v2.apk, $v2.aab, $wrongSignerApk, $apks)
$manifestArtifacts = foreach ($artifact in $artifacts) {
    $item = Get-Item -LiteralPath $artifact
    [ordered]@{
        name = $item.Name
        bytes = $item.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $item.FullName).Hash.ToLowerInvariant()
    }
}

function Get-CertificateSha256 {
    param([Parameter(Mandatory = $true)][string]$Apk)
    $apksigner = Join-Path $AndroidSdkRoot 'build-tools\36.0.0\apksigner.bat'
    $lines = @(& $apksigner 'verify' '--print-certs' $Apk 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read APK certificate: $Apk"
    }
    $line = $lines | Where-Object {
        $_.ToString() -match 'certificate SHA-256 digest:\s*([0-9a-fA-F]{64})'
    } | Select-Object -First 1
    if (-not $line -or $line.ToString() -notmatch '([0-9a-fA-F]{64})') {
        throw "APK certificate SHA-256 was not reported: $Apk"
    }
    return $Matches[1].ToLowerInvariant()
}

$manifest = [ordered]@{
    schema = 'alas-headless.android-update-lab-artifacts/v1'
    package = 'io.github.alasheadless.updatelab'
    bundletool = [ordered]@{
        version = '1.18.3'
        sha256 = $bundletoolSha256
    }
    toolchain = [ordered]@{
        gradle = '9.4.1'
        android_gradle_plugin = '9.2.0'
        java_home = $JavaHome
        compile_sdk = 'android-35'
        target_sdk = 32
        build_tools = '36.0.0'
        ndk = '23.1.7779620'
    }
    signers = [ordered]@{
        accepted_sha256 = Get-CertificateSha256 -Apk $v2.apk
        negative_control_sha256 = Get-CertificateSha256 -Apk $wrongSignerApk
    }
    artifacts = @($manifestArtifacts)
    sources = @(Get-ChildItem -LiteralPath $project -Recurse -File |
        Where-Object { $_.FullName -notmatch '[\\/](build|\.cxx|\.gradle)[\\/]' } |
        Sort-Object FullName |
        ForEach-Object {
            [ordered]@{
                path = $_.FullName.Substring($project.Length + 1).Replace('\\', '/')
                sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        })
}
$manifestPath = Join-Path $output 'manifest.json'
[IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)
Write-Output $manifestPath
