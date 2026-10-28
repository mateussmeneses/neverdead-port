$ErrorActionPreference = 'Stop'
$launcher = Join-Path $PSScriptRoot '..\src\launcher.ps1'
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('NeverDead launcher test ' + [guid]::NewGuid())
function Expect-Rejection([string]$Folder) {
    $rejected = $false
    try { & $launcher -ValidateOnly -GameFolder $Folder } catch { $rejected = $true }
    if (!$rejected) { throw "Accepted invalid folder: $Folder" }
}
try {
    Expect-Rejection ''
    Expect-Rejection $fixture
    [IO.Directory]::CreateDirectory($fixture) | Out-Null
    Expect-Rejection $fixture
    $required = @('default.xex', 'Envs\NeverDead.Xbox360_textures', 'GUIMenu\loadingInitial.guiBE', 'Text\Menu\Menu_En.asrBE')
    foreach ($relative in $required) {
        $file = Join-Path $fixture $relative
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($file)) | Out-Null
        [IO.File]::WriteAllBytes($file, [byte[]]@(1))
    }
    & $launcher -ValidateOnly -GameFolder $fixture
    foreach ($relative in $required) {
        $file = Join-Path $fixture $relative
        [IO.File]::WriteAllBytes($file, [byte[]]@())
        Expect-Rejection $fixture
        [IO.File]::WriteAllBytes($file, [byte[]]@(1))
    }
    'PASS: valid spaced path, empty/missing folder, and each empty required file.'
} finally {
    if ((Split-Path $fixture -Leaf) -like 'NeverDead launcher test *' -and (Test-Path -LiteralPath $fixture)) {
        Remove-Item -LiteralPath $fixture -Recurse -Force
    }
}
