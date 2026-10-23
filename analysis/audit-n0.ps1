[CmdletBinding()]
param(
    [switch]$RepairManifest
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path $PSScriptRoot -Parent
$manifest = Join-Path $root 'references.csv'
$logDir = Join-Path $root 'logs'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$log = Join-Path $logDir "n0-$stamp.log"
$prefix = Join-Path $PSScriptRoot "n0-$stamp"
$rows = @(Import-Csv -LiteralPath $manifest)
if ($rows.Count -ne 13) {
    throw "Expected 13 references; found $($rows.Count). No manifest changes made."
}

function Invoke-Logged {
    param([string]$Program, [string[]]$Arguments)
    Write-Host "> $Program $($Arguments -join ' ')"
    $output = @(& $Program @Arguments 2>&1)
    $code = $LASTEXITCODE
    foreach ($line in $output) { Write-Host "$line" }
    Write-Host "EXIT=$code"
    [pscustomobject]@{ Output = $output; ExitCode = $code }
}

Start-Transcript -LiteralPath $log | Out-Null
try {
    Write-Host "UTC=$([DateTime]::UtcNow.ToString('o')) ROOT=$root"
    $inventory = @()
    $submodules = @()
    $hashes = [System.Collections.Generic.List[object]]::new()
    foreach ($r in $rows) {
        Write-Host "=== $($r.Group)\$($r.Name) ==="
        $expectedPath = Join-Path (Join-Path (Join-Path $root 'refs') $r.Group) $r.Name
        if ([IO.Path]::GetFullPath($r.Path) -ne [IO.Path]::GetFullPath($expectedPath)) {
            throw "Unexpected manifest path: $($r.Path)"
        }
        $head = Invoke-Logged git @('--no-pager', '-C', $r.Path, 'rev-parse', '--verify', 'HEAD')
        $commit = ($head.Output -join '').Trim()
        if ($head.ExitCode -ne 0 -or $commit -notmatch '^[0-9a-f]{40}$') {
            throw "Invalid HEAD: $($r.Name). No manifest changes made."
        }
        if ($commit -ne $r.Commit) {
            throw "HEAD differs from bootstrap pin: $($r.Name). No manifest changes made."
        }
        $status = Invoke-Logged git @('--no-pager', '-C', $r.Path, 'status', '--porcelain=v1', '--untracked-files=normal')
        $subs = Invoke-Logged git @('--no-pager', '-C', $r.Path, 'submodule', 'status', '--recursive')
        $commitInfo = Invoke-Logged git @('--no-pager', '-C', $r.Path, 'show', '-s', '--format=%H %cI %s', 'HEAD')
        if ($status.ExitCode -ne 0 -or $subs.ExitCode -ne 0 -or $commitInfo.ExitCode -ne 0) {
            throw "Git metadata check failed: $($r.Name). No manifest changes made."
        }
        foreach ($line in $subs.Output) {
            $text = "$line"
            if ($text -notmatch '^([-+ U])([0-9a-f]{40}) (.+?)(?: \(.+\))?$') {
                throw "Unrecognized submodule status: $text"
            }
            $submodules += [pscustomobject]@{
                Repository = $r.Name
                State = $Matches[1]
                Commit = $Matches[2]
                Path = $Matches[3]
            }
        }
        $inventory += [pscustomobject]@{
            Name = $r.Name
            Group = $r.Group
            Commit = $commit
            HeadVerified = $true
            MatchesBootstrap = $true
            WorktreeClean = ($status.Output.Count -eq 0)
            Submodules = $subs.Output.Count
            Uninitialized = @($subs.Output | Where-Object { "$_".StartsWith('-') }).Count
            Path = $r.Path
        }
        $tracked = @(& git --no-pager -C $r.Path -c core.quotepath=false ls-files)
        if ($LASTEXITCODE -ne 0) { throw "Cannot list tracked files: $($r.Name)" }
        foreach ($relative in $tracked) {
            $file = Join-Path $r.Path $relative
            if (Test-Path -LiteralPath $file -PathType Leaf) {
                $item = Get-Item -LiteralPath $file
                $hashes.Add([pscustomobject]@{
                    Path = [IO.Path]::GetRelativePath($root, $item.FullName)
                    Length = $item.Length
                    SHA256 = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
                })
            } elseif (-not (Test-Path -LiteralPath $file -PathType Container)) {
                throw "Missing tracked file: $file"
            }
        }
    }
    $inventory | Export-Csv -LiteralPath "$prefix-repositories.csv" -NoTypeInformation -Encoding utf8
    $submodules | Export-Csv -LiteralPath "$prefix-submodules.csv" -NoTypeInformation -Encoding utf8
    $workspace = foreach ($name in 'src', 'refs', 'build', 'game-dump', 'generated', 'tests', 'analysis', 'logs') {
        $path = Join-Path $root $name
        $children = @(Get-ChildItem -LiteralPath $path -Force)
        [pscustomobject]@{
            Directory = $name
            ImmediateEntries = $children.Count
            Entries = (($children | ForEach-Object { $_.Name }) -join ';')
        }
        if ($name -in @('src', 'build', 'game-dump', 'generated', 'tests')) {
            foreach ($file in (Get-ChildItem -LiteralPath $path -File -Recurse -Force)) {
                $hashes.Add([pscustomobject]@{
                    Path = [IO.Path]::GetRelativePath($root, $file.FullName)
                    Length = $file.Length
                    SHA256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
                })
            }
        }
    }
    $workspace | Export-Csv -LiteralPath "$prefix-workspace.csv" -NoTypeInformation -Encoding utf8
    $hashes | Export-Csv -LiteralPath "$prefix-files-sha256.csv" -NoTypeInformation -Encoding utf8
    Write-Host "Repositories=$($inventory.Count) Submodules=$($submodules.Count) HashedFiles=$($hashes.Count)"
    $inventory | Format-Table Name, HeadVerified, MatchesBootstrap, WorktreeClean, Submodules, Uninitialized | Out-Host
    $workspace | Format-Table Directory, ImmediateEntries | Out-Host

    foreach ($tool in 'git', 'cmake', 'ninja', 'python', 'clang', 'clang++', 'clang-cl', 'cl', 'MSBuild', 'rexglue') {
        $command = Get-Command $tool -ErrorAction SilentlyContinue
        if ($command) { Write-Host "$tool=$($command.Source)" }
        else { Write-Host "$tool=NOT_ON_PATH" }
    }
    foreach ($tool in 'git', 'cmake', 'ninja', 'python') {
        $version = Invoke-Logged $tool @('--version')
        if ($version.ExitCode -ne 0) { throw "Cannot query version: $tool" }
    }
    $cmakeHelp = Invoke-Logged cmake @('--help')
    if ($cmakeHelp.ExitCode -ne 0) { throw 'Cannot read CMake help' }
    foreach ($r in $rows) {
        if (Test-Path -LiteralPath (Join-Path $r.Path 'CMakePresets.json')) {
            $presets = Invoke-Logged cmake @('-S', $r.Path, '--list-presets=all')
            if ($presets.ExitCode -ne 0) { throw "Invalid presets: $($r.Name)" }
        }
    }
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path -LiteralPath $vswhere) {
        $vs = Invoke-Logged $vswhere @('-all', '-products', '*', '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath')
        if ($vs.ExitCode -ne 0) { throw 'vswhere failed' }
        foreach ($installation in $vs.Output) {
            $llvmDir = Join-Path "$installation" 'VC\Tools\Llvm'
            if (Test-Path -LiteralPath $llvmDir) {
                Get-ChildItem -LiteralPath $llvmDir -Filter 'clang*.exe' -Recurse |
                    Select-Object -ExpandProperty FullName | Out-Host
            }
        }
    }
    foreach ($path in 'C:\Program Files\LLVM\bin\clang.exe',
        'C:\Program Files (x86)\Windows Kits\10\Include\10.0.26100.0\um\d3d12.h',
        'C:\Program Files (x86)\Windows Kits\10\Include\10.0.26100.0\ucrt\stdio.h',
        'refs\core\rexglue-sdk\tools\binutils\powerpc-none-elf-as.exe',
        'refs\core\rexglue-sdk\tools\binutils\powerpc-none-elf-ld.exe',
        'refs\core\rexglue-sdk\tools\binutils\powerpc-none-elf-nm.exe',
        'refs\ports\DownpourRecomp\generated\rexglue.cmake',
        'refs\ports\EdgeOfTimeRecomp\generated\rexglue.cmake') {
        $resolved = if ([IO.Path]::IsPathRooted($path)) { $path } else { Join-Path $root $path }
        Write-Host "$resolved EXISTS=$(Test-Path -LiteralPath $resolved)"
    }
    $sdkIncludes = 'C:\Program Files (x86)\Windows Kits\10\Include'
    Get-ChildItem -LiteralPath $sdkIncludes -Directory | Select-Object -ExpandProperty Name | Out-Host
    Get-CimInstance Win32_VideoController | Format-Table Name, DriverVersion | Out-Host
    Get-PSDrive C | Format-List Used, Free | Out-Host
    foreach ($name in 'VCPKG_ROOT', 'VULKAN_SDK', 'REXSDK_DIR', 'REXGLUE_ROOT') {
        Write-Host "$name PRESENT=$(Test-Path Env:$name)"
    }
    if ($RepairManifest) {
        $backup = Join-Path $logDir "references-before-n0-$stamp.csv"
        Copy-Item -LiteralPath $manifest -Destination $backup
        foreach ($r in $rows) { $r.Status = 'OK' }
        $rows | Export-Csv -LiteralPath $manifest -NoTypeInformation -Encoding utf8BOM
        $repaired = @(Import-Csv -LiteralPath $manifest)
        if ($repaired.Count -ne $rows.Count -or @($repaired | Where-Object Status -ne 'OK').Count -ne 0) {
            throw "Manifest verification failed. Backup: $backup"
        }
        Write-Host "Repaired references.csv: OK means HEAD verified, NOT build readiness. Backup=$backup"
    }
    Write-Host "AUDIT_OK PREFIX=$prefix LOG=$log"
} finally {
    Stop-Transcript | Out-Null
}
