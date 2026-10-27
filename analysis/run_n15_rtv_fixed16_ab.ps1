[CmdletBinding()]
param(
    [int]$WaitForIdleSeconds = 900,
    [int]$DurationSeconds = 30,
    [string]$ReferenceCapture = (Join-Path $PSScriptRoot 'n13-benchmarks\n13-warm_rov_01-gameplay-20261025-094351.bmp')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$PSNativeCommandUseErrorActionPreference = $false

$profiler = Join-Path $PSScriptRoot 'profile_n13.py'
$outputRoot = Join-Path $PSScriptRoot 'n13-benchmarks'
if (-not (Test-Path -LiteralPath $ReferenceCapture -PathType Leaf)) {
    throw "ROV reference capture not found: '$ReferenceCapture'."
}
$variants = @(
    [pscustomobject]@{ Name = 'full_range'; DisableFullRange = $false },
    [pscustomobject]@{ Name = 'limited_range'; DisableFullRange = $true }
)
$results = @()

foreach ($variant in $variants) {
    $outputDir = Join-Path $outputRoot ("n15-rtv-fixed16-{0}" -f $variant.Name)
    $profilePath = Join-Path $outputDir 'n13_warm_rtv_profile.json'
    $runStartedUtc = [DateTime]::UtcNow
    $arguments = @(
        $profiler,
        '--scenario', 'warm',
        '--render-path', 'rtv',
        '--duration', $DurationSeconds,
        '--wait-for-idle', $WaitForIdleSeconds,
        '--reference-capture', $ReferenceCapture,
        '--output-dir', $outputDir
    )
    if ($variant.DisableFullRange) {
        $arguments += '--disable-snorm16-full-range'
    }

    & python @arguments
    $profileFile = Get-Item -LiteralPath $profilePath -ErrorAction SilentlyContinue
    if (-not $profileFile -or $profileFile.LastWriteTimeUtc -lt $runStartedUtc) {
        throw "RTV $($variant.Name) run produced no profile (exit $LASTEXITCODE)."
    }
    $profile = Get-Content -LiteralPath $profilePath -Raw | ConvertFrom-Json
    $results += [ordered]@{
        Name = $variant.Name
        Profile = $profilePath
        GameplayGatePassed = $profile.gameplay_gate.passed
        PerformanceGatePassed = $profile.performance_gate.passed
        VisualGatePassed = $profile.visual_gate.passed
        LuminanceDeltaPercent = $profile.visual_gate.luminance_delta_pct
        MaximumAverageChannelDelta = $profile.visual_gate.maximum_average_channel_delta
        CaptureMetrics = $profile.gameplay_gate.capture_metrics
    }
}

$hypothesisSupported = (
    -not $results[0].VisualGatePassed -and
    $results[1].LuminanceDeltaPercent -lt $results[0].LuminanceDeltaPercent
)
$passed = (
    $hypothesisSupported -and
    $results[1].GameplayGatePassed -and
    $results[1].VisualGatePassed
)
$aggregate = [ordered]@{
    Passed = $passed
    HypothesisSupported = $hypothesisSupported
    Hypothesis = 'RTV fixed16 full-range alpha scaling causes the dark blend regression.'
    Variants = $results
}
$aggregatePath = Join-Path $outputRoot 'n15_rtv_fixed16_ab.json'
[IO.File]::WriteAllText(
    $aggregatePath,
    ($aggregate | ConvertTo-Json -Depth 8),
    [Text.Encoding]::UTF8
)

if (-not $passed) {
    throw "RTV fixed16 A/B did not confirm the alpha-blend hypothesis. See '$aggregatePath'."
}
Write-Host "RTV fixed16 A/B PASS: $aggregatePath"
