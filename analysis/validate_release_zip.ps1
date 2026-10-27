param(
    [Parameter(Mandatory = $true)]
    [string]$ZipPath
)

$ErrorActionPreference = 'Stop'
$resolvedZip = (Resolve-Path -LiteralPath $ZipPath).Path
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($resolvedZip)

try {
    $files = @($archive.Entries | Where-Object { $_.Name })
    $roots = @($files.FullName | ForEach-Object { ($_ -split '/')[0] } | Sort-Object -Unique)
    if ($roots.Count -ne 1) {
        throw "Release ZIP must contain exactly one root directory"
    }

    $expected = @(
        'README.md'
        'neverdead.exe'
        'neverdead.toml'
        'rexgpu-xenos.dll'
        'rexruntime.dll'
    )
    $actual = @($files.FullName | ForEach-Object {
        if ($_ -match '(^|/)\.\.(/|$)' -or $_ -match '^/' -or $_ -match '\\') {
            throw "Unsafe archive path: $_"
        }
        ($_ -split '/', 2)[1]
    } | Sort-Object)
    $difference = @(Compare-Object $expected $actual)
    if ($difference.Count) {
        throw "Unexpected release contents: $($difference | Out-String)"
    }
    if (@($actual | Sort-Object -Unique).Count -ne $actual.Count) {
        throw "Release ZIP contains duplicate files"
    }
    if ($files.Where({ $_.Length -eq 0 }).Count) {
        throw 'Release ZIP contains an empty file'
    }

    foreach ($binary in $files.Where({ $_.Name -match '\.(exe|dll)$' })) {
        $stream = $binary.Open()
        try {
            if ($stream.ReadByte() -ne 0x4D -or $stream.ReadByte() -ne 0x5A) {
                throw "Packaged binary is not a valid PE file: $($binary.FullName)"
            }
        }
        finally {
            $stream.Dispose()
        }
    }

    $configEntry = $files | Where-Object Name -eq 'neverdead.toml'
    $reader = [System.IO.StreamReader]::new($configEntry.Open())
    try {
        $config = $reader.ReadToEnd()
    }
    finally {
        $reader.Dispose()
    }
    if ($config -notmatch '(?m)^render_target_path_d3d12\s*=\s*"rov"\s*$') {
        throw 'Release must retain ROV as the NeverDead fallback'
    }
    if ($config -notmatch '(?m)^gpu_allow_invalid_fetch_constants\s*=\s*false\s*$') {
        throw 'Release must retain safe fetch-constant validation'
    }

    $hash = (Get-FileHash -LiteralPath $resolvedZip -Algorithm SHA256).Hash
    [pscustomobject]@{
        Zip = $resolvedZip
        Root = $roots[0]
        Files = $actual.Count
        RenderTargetPath = 'rov'
        SHA256 = $hash
        Passed = $true
    }
}
finally {
    $archive.Dispose()
}
