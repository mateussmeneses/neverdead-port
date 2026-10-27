[CmdletBinding()]
param(
    [string]$GameDataRoot = 'C:\projetos\NeverDeadxex',
    [Parameter(Mandatory)]
    [string]$SoakProfilePath,
    [int]$WaitForIdleSeconds = 300
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$harness = Join-Path $PSScriptRoot 'test_n12_gameplay_save_audio.ps1'
$outputDir = Join-Path $PSScriptRoot 'n12-validation'
$reportPath = Join-Path $outputDir 'n12_validation_report.json'
$pwsh = Join-Path $PSHOME 'pwsh.exe'
$soak = Get-Content -LiteralPath (Resolve-Path -LiteralPath $SoakProfilePath) -Raw |
    ConvertFrom-Json
$userDir = [string]$soak.save_persistence.user_data_root
if (-not $userDir -or -not (Test-Path -LiteralPath $userDir -PathType Container)) {
    throw "Soak profile user-data root is missing: '$userDir'."
}
$expectedSave = @($soak.save_persistence.final_files.PSObject.Properties |
    Where-Object Name -Match '(^|[\\/])ND\.sav$')
if ($expectedSave.Count -ne 1 -or -not $expectedSave[0].Value.sha256) {
    throw 'Soak profile must contain exactly one final ND.sav hash.'
}
$expectedSaveHash = [string]$expectedSave[0].Value.sha256

while ($true) {
    & $pwsh -NoProfile -File $harness -GameDataRoot $GameDataRoot `
        -UserDataRoot $userDir -WaitForIdleSeconds $WaitForIdleSeconds
    if ($LASTEXITCODE -eq 75) {
        Write-Host 'Reopen interrupted by laptop activity; re-arming...'
        continue
    }
    if ($LASTEXITCODE -ne 0) {
        throw "N12 reopen failed with exit code $LASTEXITCODE."
    }
    break
}

$reopenReportPath = Join-Path $outputDir 'n15_save_reopen_cycle_report.json'
Copy-Item -LiteralPath $reportPath -Destination $reopenReportPath -Force
$reopen = Get-Content -LiteralPath $reopenReportPath -Raw | ConvertFrom-Json
$persistedSaveReopened = (
    $reopen.SavePersistence.InitialHash -and
    $expectedSaveHash -eq $reopen.SavePersistence.InitialHash
)
$persistencePassed = (
    $soak.stability_gate.passed -and
    $soak.stability_gate.checks.checkpoint_state_persisted -and
    $persistedSaveReopened -and
    $reopen.SavePersistence.ItemsEnumerated -gt 0 -and
    $reopen.SavePersistence.DeviceSelectorTriggered -and
    @($reopen.Captures).Count -ge 11 -and
    $reopen.StabilityAudit.FatalTraps -eq 0 -and
    $reopen.StabilityAudit.D3D12Errors -eq 0 -and
    $reopen.StabilityAudit.DredFaults -eq 0
)

$aggregate = [ordered]@{
    PersistencePassed = $persistencePassed
    ContinueVerified = $false
    SoakProfile = (Resolve-Path -LiteralPath $SoakProfilePath).Path
    UserDataRoot = $userDir
    ExpectedSaveHash = $expectedSaveHash
    PersistedSaveReopened = $persistedSaveReopened
    ReopenItemsEnumerated = $reopen.SavePersistence.ItemsEnumerated
    ReopenCaptures = @($reopen.Captures).Count
    ReopenReport = 'n15_save_reopen_cycle_report.json'
}
$aggregatePath = Join-Path $outputDir 'n15_save_reopen_report.json'
[IO.File]::WriteAllText(
    $aggregatePath,
    ($aggregate | ConvertTo-Json -Depth 4),
    [Text.Encoding]::UTF8
)

if (-not $persistencePassed) {
    throw "Save persistence -> close -> reopen gate failed. See '$aggregatePath'."
}
Write-Host "Save persistence -> close -> reopen gate PASS: $aggregatePath"
Write-Warning 'Continue remains unverified until the resumed gameplay route is validated.'
