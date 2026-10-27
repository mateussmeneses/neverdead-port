[CmdletBinding()]
param(
    [int]$WaitForIdleSeconds = 900
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not ('N15BuildIdle' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class N15BuildIdle {
    [StructLayout(LayoutKind.Sequential)]
    public struct LASTINPUTINFO {
        public uint cbSize;
        public uint dwTime;
    }

    [DllImport("user32.dll")]
    public static extern bool GetLastInputInfo(ref LASTINPUTINFO info);

    [DllImport("kernel32.dll")]
    public static extern uint GetTickCount();

    public static uint GetLastInputTick() {
        LASTINPUTINFO info = new LASTINPUTINFO();
        info.cbSize = (uint)Marshal.SizeOf(typeof(LASTINPUTINFO));
        if (!GetLastInputInfo(ref info)) throw new System.ComponentModel.Win32Exception();
        return info.dwTime;
    }

    public static uint GetIdleMilliseconds() {
        return unchecked(GetTickCount() - GetLastInputTick());
    }
}
'@
}

$root = Split-Path $PSScriptRoot -Parent
$buildRoot = Join-Path $root 'build\n2-neverdead'
$exe = Join-Path $buildRoot 'neverdead.exe'
$runtimeDll = Join-Path $buildRoot 'rexruntime.dll'
$arguments = @('--build', $buildRoot, '--target', 'neverdead', '--parallel', '1')

while ($true) {
    Write-Host "Waiting until Windows has been idle for $WaitForIdleSeconds seconds..."
    while ([N15BuildIdle]::GetIdleMilliseconds() -lt $WaitForIdleSeconds * 1000) {
        Start-Sleep -Seconds 5
    }

    $initialInputTick = [N15BuildIdle]::GetLastInputTick()
    $build = Start-Process cmake -ArgumentList $arguments -WorkingDirectory $root `
        -WindowStyle Hidden -PassThru
    try { $build.PriorityClass = 'BelowNormal' } catch {}
    $interrupted = $false
    while (-not $build.HasExited) {
        Start-Sleep -Seconds 1
        $build.Refresh()
        if ([N15BuildIdle]::GetLastInputTick() -ne $initialInputTick) {
            & taskkill.exe /PID $build.Id /T /F | Out-Null
            $build.WaitForExit()
            $interrupted = $true
            Write-Host 'Build stopped because laptop activity resumed; re-arming...'
            break
        }
    }
    if ($interrupted) { continue }
    if ($build.ExitCode -ne 0) {
        throw "N15 build failed with exit code $($build.ExitCode)."
    }
    break
}

function Test-BinaryMarker {
    param([string]$Path, [string]$Marker)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    return [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($Path)).Contains($Marker)
}

if (-not (Test-BinaryMarker $exe 'N15 gameplay pause thunk 0x8253B640 reached') -or
    -not (Test-BinaryMarker $runtimeDll 'Read save file:')) {
    throw 'N15 build completed without the required runtime evidence markers.'
}
Write-Host 'N15 instrumented build PASS.'
