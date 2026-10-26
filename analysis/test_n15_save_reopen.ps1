[CmdletBinding()]
param(
    [string]$GameDataRoot = 'C:\projetos\NeverDeadxex',
    [int]$WaitForIdleSeconds = 300
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$harness = Join-Path $PSScriptRoot 'test_n12_gameplay_save_audio.ps1'
$outputDir = Join-Path $PSScriptRoot 'n12-validation'
$reportPath = Join-Path $outputDir 'n12_validation_report.json'
$pwsh = Join-Path $PSHOME 'pwsh.exe'
$reports = @()

for ($cycle = 1; $cycle -le 2; $cycle++) {
    while ($true) {
        & $pwsh -NoProfile -File $harness -GameDataRoot $GameDataRoot `
            -WaitForIdleSeconds $WaitForIdleSeconds
        if ($LASTEXITCODE -eq 75) {
            Write-Host "Cycle $cycle interrupted by laptop activity; re-arming..."
            continue
        }
        if ($LASTEXITCODE -ne 0) {
            throw "N12 cycle $cycle failed with exit code $LASTEXITCODE."
        }
        break
    }

    $cycleReportPath = Join-Path $outputDir ("n15_save_cycle_{0:D2}_report.json" -f $cycle)
    Copy-Item -LiteralPath $reportPath -Destination $cycleReportPath -Force
    $reports += Get-Content -LiteralPath $cycleReportPath -Raw | ConvertFrom-Json
}

$first = $reports[0]
$second = $reports[1]
$sameSaveReopened = (
    $first.SavePersistence.FinalHash -and
    $first.SavePersistence.FinalHash -eq $second.SavePersistence.InitialHash
)
$passed = (
    $first.SavePersistence.WasWritten -and
    $sameSaveReopened -and
    $second.SavePersistence.ItemsEnumerated -gt 0 -and
    $second.SavePersistence.DeviceSelectorTriggered -and
    @($second.Captures).Count -ge 11 -and
    $second.StabilityAudit.FatalTraps -eq 0 -and
    $second.StabilityAudit.D3D12Errors -eq 0 -and
    $second.StabilityAudit.DredFaults -eq 0
)

$aggregate = [ordered]@{
    Passed = $passed
    SameSaveReopened = $sameSaveReopened
    FirstCycleSaveWritten = $first.SavePersistence.WasWritten
    SecondCycleItemsEnumerated = $second.SavePersistence.ItemsEnumerated
    SecondCycleCaptures = @($second.Captures).Count
    CycleReports = @(
        'n15_save_cycle_01_report.json',
        'n15_save_cycle_02_report.json'
    )
}
$aggregatePath = Join-Path $outputDir 'n15_save_reopen_report.json'
[IO.File]::WriteAllText(
    $aggregatePath,
    ($aggregate | ConvertTo-Json -Depth 4),
    [Text.Encoding]::UTF8
)

if (-not $passed) {
    throw "Save -> close -> reopen -> continue gate failed. See '$aggregatePath'."
}
Write-Host "Save -> close -> reopen -> continue gate PASS: $aggregatePath"
