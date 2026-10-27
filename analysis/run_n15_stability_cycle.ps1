[CmdletBinding()]
param(
    [ValidateRange(1800, 3600)]
    [int]$DurationSeconds = 1800,
    [int]$WaitForIdleSeconds = 900,
    [string]$GameDataRoot = 'C:\projetos\NeverDeadxex'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$PSNativeCommandUseErrorActionPreference = $false

$profiler = Join-Path $PSScriptRoot 'profile_n13.py'
$reopenRunner = Join-Path $PSScriptRoot 'test_n15_save_reopen.ps1'
$root = Split-Path $PSScriptRoot -Parent
$exe = Join-Path $root 'build\n2-neverdead\neverdead.exe'
$runtimeEvidenceSources = @(
    (Join-Path $root 'src\src\neverdead_diagnostics.cpp'),
    (Join-Path $root 'refs\core\rexglue-sdk\src\kernel\xboxkrnl\xboxkrnl_io.cpp')
)
$outputDir = Join-Path $PSScriptRoot 'n13-benchmarks\n15-stability-final'
$profilePath = Join-Path $outputDir 'n13_warm_rov_stability_profile.json'
$reopenReportPath = Join-Path $PSScriptRoot 'n12-validation\n15_save_reopen_report.json'
$pwsh = Join-Path $PSHOME 'pwsh.exe'
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

$exeFile = Get-Item -LiteralPath $exe -ErrorAction SilentlyContinue
$newestEvidenceSource = $runtimeEvidenceSources |
    ForEach-Object { Get-Item -LiteralPath $_ } |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
if (-not $exeFile -or $exeFile.LastWriteTimeUtc -lt $newestEvidenceSource.LastWriteTimeUtc) {
    throw 'NeverDead executable is missing or older than N15 evidence instrumentation; build it first.'
}

$runStartedUtc = [DateTime]::UtcNow
$profilerArguments = @(
    $profiler,
    '--scenario', 'warm',
    '--render-path', 'rov',
    '--duration', $DurationSeconds,
    '--stability',
    '--wait-for-idle', $WaitForIdleSeconds,
    '--game-data', $GameDataRoot,
    '--exe', $exe,
    '--output-dir', $outputDir
)
& python @profilerArguments
if ($LASTEXITCODE -ne 0) {
    throw "N15 stability profiler failed with exit code $LASTEXITCODE."
}
$profileFile = Get-Item -LiteralPath $profilePath -ErrorAction SilentlyContinue
if (-not $profileFile -or $profileFile.LastWriteTimeUtc -lt $runStartedUtc) {
    throw "N15 stability profiler produced no fresh profile at '$profilePath'."
}
$profile = Get-Content -LiteralPath $profilePath -Raw | ConvertFrom-Json
if (-not $profile.performance_gate.passed -or -not $profile.stability_gate.passed) {
    throw "Fresh N15 stability profile did not pass its gates: '$profilePath'."
}

& $pwsh -NoProfile -File $reopenRunner -GameDataRoot $GameDataRoot `
    -SoakProfilePath $profilePath -WaitForIdleSeconds $WaitForIdleSeconds
if ($LASTEXITCODE -ne 0) {
    throw "N15 save reopen failed with exit code $LASTEXITCODE."
}
$reopen = Get-Content -LiteralPath $reopenReportPath -Raw | ConvertFrom-Json
$passed = (
    $profile.performance_gate.passed -and
    $profile.stability_gate.passed -and
    $reopen.PersistencePassed -and
    $reopen.ContinueVerified
)
$aggregate = [ordered]@{
    Passed = $passed
    SoakPassed = [bool]$profile.stability_gate.passed
    PersistencePassed = [bool]$reopen.PersistencePassed
    ContinueVerified = [bool]$reopen.ContinueVerified
    SoakProfile = $profilePath
    ReopenReport = $reopenReportPath
}
$aggregatePath = Join-Path $outputDir 'n15_stability_cycle.json'
[IO.File]::WriteAllText(
    $aggregatePath,
    ($aggregate | ConvertTo-Json -Depth 4),
    [Text.Encoding]::UTF8
)

if (-not $passed) {
    throw "N15 stability cycle is incomplete. See '$aggregatePath'."
}
Write-Host "N15 stability cycle PASS: $aggregatePath"
