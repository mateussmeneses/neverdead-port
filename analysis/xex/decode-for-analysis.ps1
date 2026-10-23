[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InputPath,
    [Parameter(Mandatory)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (Test-Path -LiteralPath $OutputPath) { throw 'Output must not already exist' }
$source = [IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $InputPath).Path)
function Read-U32([int]$Offset) {
    if ($Offset -lt 0 -or $Offset + 4 -gt $source.Length) { throw 'Invalid XEX offset' }
    [byte[]]$bytes = $source[$Offset..($Offset + 3)]
    [Array]::Reverse($bytes)
    [BitConverter]::ToUInt32($bytes, 0)
}
if ([Text.Encoding]::ASCII.GetString($source, 0, 4) -ne 'XEX2') { throw 'Not XEX2' }
$headerSize = Read-U32 8
$security = Read-U32 16
$count = Read-U32 20
$ffi = $null
for ($i = 0; $i -lt $count; $i++) {
    if ((Read-U32 (24 + 8 * $i)) -eq 0x3ff) { $ffi = Read-U32 (28 + 8 * $i) }
}
if ($null -eq $ffi) { throw 'No file-format info' }
if ((Read-U32 ($ffi + 4)) -ne 0x00010001) {
    throw 'This analysis adapter only supports encryption=1, compression=1'
}
$ffiSize = Read-U32 $ffi
if ($ffiSize -lt 8 -or ($ffiSize - 8) % 8) { throw 'Invalid basic block table' }
$blocks = @()
$imageSize = 0L
$payloadSize = 0L
for ($offset = $ffi + 8; $offset -lt $ffi + $ffiSize; $offset += 8) {
    $dataSize = Read-U32 $offset
    $zeroSize = Read-U32 ($offset + 4)
    if ($dataSize % 16) { throw 'AES block is not aligned' }
    $blocks += [pscustomobject]@{ DataSize = $dataSize; ZeroSize = $zeroSize }
    $imageSize += $dataSize + $zeroSize
    $payloadSize += $dataSize
}
if ($imageSize -ne (Read-U32 ($security + 4)) -or $headerSize + $payloadSize -ne $source.Length) {
    throw 'Declared image or payload size does not match block table'
}

# Use the existing reference key only in memory; never print or persist key material.
$reference = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'refs\core\360tools\tools\extract_pe.py'
$text = [IO.File]::ReadAllText($reference)
$keyBlock = [regex]::Match($text, '(?s)XEX2_RETAIL_KEY = bytes\(\[(.*?)\]\)')
if (-not $keyBlock.Success) { throw 'Reference key declaration not found' }
[byte[]]$retail = @([regex]::Matches($keyBlock.Groups[1].Value, '0x[0-9A-Fa-f]{2}') |
    ForEach-Object { [Convert]::ToByte($_.Value.Substring(2), 16) })
if ($retail.Length -ne 16) { throw 'Unexpected reference key length' }
$aes = [Security.Cryptography.Aes]::Create()
try {
    $aes.Mode = [Security.Cryptography.CipherMode]::CBC
    $aes.Padding = [Security.Cryptography.PaddingMode]::None
    $aes.Key = $retail
    $aes.IV = [byte[]]::new(16)
    $decryptor = $aes.CreateDecryptor()
    try { $session = $decryptor.TransformFinalBlock($source, $security + 0x150, 16) }
    finally { $decryptor.Dispose() }
    $aes.Key = $session
    $decryptor = $aes.CreateDecryptor()
    try { $plain = $decryptor.TransformFinalBlock($source, $headerSize, $payloadSize) }
    finally { $decryptor.Dispose() }
    $image = [byte[]]::new($imageSize)
    $src = 0L
    $dst = 0L
    foreach ($block in $blocks) {
        [Array]::Copy($plain, $src, $image, $dst, $block.DataSize)
        $src += $block.DataSize
        $dst += $block.DataSize + $block.ZeroSize
    }
    if ([Text.Encoding]::ASCII.GetString($image, 0, 2) -ne 'MZ') { throw 'Decoded image has no DOS signature' }
    $pe = [BitConverter]::ToInt32($image, 0x3c)
    if ($pe -lt 0 -or $pe + 26 -gt $image.Length -or
        [BitConverter]::ToUInt32($image, $pe) -ne 0x4550 -or
        [BitConverter]::ToUInt16($image, $pe + 4) -ne 0x1f2 -or
        [BitConverter]::ToUInt16($image, $pe + 24) -ne 0x10b) {
        throw 'Decoded image is not a valid POWERPCBE PE32 header'
    }
    [IO.File]::WriteAllBytes($OutputPath, $image)
    Get-FileHash -LiteralPath $InputPath, $OutputPath -Algorithm SHA256 |
        Select-Object Path, Hash
    Write-Output "DERIVED_IMAGE_BYTES=$imageSize; ORIGINAL_UNMODIFIED; NO_SIGNATURE_AUTHENTICATION"
} finally {
    $aes.Dispose()
    [Array]::Clear($retail)
    if (Get-Variable session -ErrorAction SilentlyContinue) { [Array]::Clear($session) }
    if (Get-Variable plain -ErrorAction SilentlyContinue) { [Array]::Clear($plain) }
}
