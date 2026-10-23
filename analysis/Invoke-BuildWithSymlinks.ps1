[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Command
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$dir = 'C:\projetos\neverdead\refs\core\rexglue-sdk\thirdparty\libmspack\cabextract\mspack'
$files = Get-ChildItem -LiteralPath $dir -File

$backups = @{}
foreach ($f in $files) {
    $bytes = [System.IO.File]::ReadAllBytes($f.FullName)
    $backups[$f.FullName] = $bytes
}

try {
    # Materialize files from relative target
    foreach ($f in $files) {
        $rel = [System.Text.Encoding]::UTF8.GetString($backups[$f.FullName]).Trim()
        $target = [System.IO.Path]::GetFullPath((Join-Path $dir $rel))
        if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
            throw "Target for symlink '$($f.Name)' not found: '$target'"
        }
        Copy-Item -LiteralPath $target -Destination $f.FullName -Force
    }

    # Execute build
    Invoke-Expression $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Build command exited with code $LASTEXITCODE"
    }
}
finally {
    # Restore placeholders byte-for-byte
    foreach ($path in $backups.Keys) {
        [System.IO.File]::WriteAllBytes($path, $backups[$path])
    }
}
