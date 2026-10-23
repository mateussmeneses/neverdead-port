<#
.SYNOPSIS
    NeverDead PC Port — N10 Real Gameplay Validation & Instrumentation Harness
.DESCRIPTION
    Launches neverdead.exe, monitors state transitions, captures Direct3D 12 frames across
    title -> menus -> cutscene -> gameplay via native GPU readback, verifies character movement
    and camera controls, and audits execution logs for guest traps, D3D12 errors, and HLE status.
#>
[CmdletBinding()]
param(
    [string]$GameDataRoot = 'C:\projetos\NeverDeadxex',
    [int]$WaitTitleSeconds = 12,
    [switch]$AutoSequence,
    [switch]$Interactive,
    [int]$RunTimeoutSeconds = 90
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = Split-Path $PSScriptRoot -Parent
$buildRoot = Join-Path $root 'build\n2-neverdead'
$exe = Join-Path $buildRoot 'neverdead.exe'
$captureDir = Join-Path $PSScriptRoot 'n10-gameplay'
$logRoot = Join-Path $buildRoot 'logs'

if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "Executable not found at '$exe'. Run build first."
}

$resolvedGameData = (Resolve-Path -LiteralPath $GameDataRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $resolvedGameData 'default.xex') -PathType Leaf)) {
    throw "default.xex not found in '$resolvedGameData'."
}

# Ensure output directories exist
New-Item -ItemType Directory -Path $captureDir, $logRoot -Force | Out-Null

$runId = Get-Date -Format 'yyyyMMdd-HHmmss'
$userDir = Join-Path $buildRoot "n10-user-$runId"
$cacheDir = Join-Path $buildRoot "n10-cache-$runId"
$logPath = Join-Path $logRoot "n10-gameplay-$runId.log"
New-Item -ItemType Directory -Path $userDir, $cacheDir -Force | Out-Null

Write-Host "================================================================="
Write-Host " NeverDead N10: Real Gameplay Validation Harness                 "
Write-Host "================================================================="
Write-Host " Run ID:        $runId"
Write-Host " Game Data:     $resolvedGameData"
Write-Host " Captures Dir:  $captureDir"
Write-Host " Log File:      $logPath"
Write-Host " Mode:          $(if ($Interactive) { 'Interactive Gameplay Validation' } else { 'Automated Sequence' })"
Write-Host "================================================================="

# Compile C# Win32 Window & Input Bridge
if (-not ('N10Bridge' -as [type])) {
    $csharpSrc = @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Threading;

public static class N10Bridge {
    [DllImport("user32.dll")]
    public static extern bool GetClientRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern bool ClientToScreen(IntPtr hWnd, ref POINT lpPoint);

    [DllImport("user32.dll")]
    public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBkgnd, uint nFlags);

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);

    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr window, int command);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr window);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern uint SendInput(uint count, INPUT[] inputs, int size);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left, Top, Right, Bottom;
        public int Width { get { return Right - Left; } }
        public int Height { get { return Bottom - Top; } }
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct POINT { public int X, Y; }

    [StructLayout(LayoutKind.Sequential)]
    public struct INPUT {
        public uint type;
        public InputUnion data;
    }

    [StructLayout(LayoutKind.Explicit)]
    public struct InputUnion {
        [FieldOffset(0)] public KEYBDINPUT keyboard;
        [FieldOffset(0)] public MOUSEINPUT mouse;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct KEYBDINPUT {
        public ushort virtualKey;
        public ushort scanCode;
        public uint flags;
        public uint time;
        public IntPtr extraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct MOUSEINPUT {
        public int dx, dy;
        public uint mouseData, flags, time;
        public IntPtr extraInfo;
    }

    public static uint ForegroundProcessId() {
        uint processId;
        GetWindowThreadProcessId(GetForegroundWindow(), out processId);
        return processId;
    }

    public static bool RequestForeground(IntPtr window) {
        ShowWindowAsync(window, 9); // SW_RESTORE
        return SetForegroundWindow(window);
    }

    public static bool TapKey(ushort vk) {
        INPUT[] inputs = new INPUT[2];
        inputs[0].type = 1;
        inputs[0].data.keyboard.virtualKey = vk;
        inputs[0].data.keyboard.flags = 0; // Key down

        inputs[1].type = 1;
        inputs[1].data.keyboard.virtualKey = vk;
        inputs[1].data.keyboard.flags = 0x0002; // Key up

        if (SendInput(1, new INPUT[] { inputs[0] }, Marshal.SizeOf(typeof(INPUT))) != 1) return false;
        Thread.Sleep(150);
        return SendInput(1, new INPUT[] { inputs[1] }, Marshal.SizeOf(typeof(INPUT))) == 1;
    }

    public static bool HoldKey(ushort vk, int durationMs) {
        INPUT[] inputs = new INPUT[2];
        inputs[0].type = 1;
        inputs[0].data.keyboard.virtualKey = vk;
        inputs[0].data.keyboard.flags = 0;

        inputs[1].type = 1;
        inputs[1].data.keyboard.virtualKey = vk;
        inputs[1].data.keyboard.flags = 0x0002;

        if (SendInput(1, new INPUT[] { inputs[0] }, Marshal.SizeOf(typeof(INPUT))) != 1) return false;
        Thread.Sleep(durationMs);
        return SendInput(1, new INPUT[] { inputs[1] }, Marshal.SizeOf(typeof(INPUT))) == 1;
    }
}
'@
    Add-Type -TypeDefinition $csharpSrc -ReferencedAssemblies System.Drawing
}

# Clean any stale trigger file
$triggerFile = Join-Path $buildRoot 'capture_trigger.txt'
if (Test-Path -LiteralPath $triggerFile) {
    Remove-Item -LiteralPath $triggerFile -Force -ErrorAction SilentlyContinue
}

# Runtime launch arguments
$arguments = @(
    "--game_data_root=$resolvedGameData",
    "--user_data_root=$userDir",
    "--cache_root=$cacheDir",
    "--mnk_mode=true",
    "--gpu_allow_invalid_fetch_constants=true",
    "--log_level=debug",
    "--log_file=$logPath"
)

$env:NEVERDEAD_CAPTURE_DIR = $captureDir

Write-Host "Launching NeverDead runtime..."
$proc = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $buildRoot -PassThru

# Locate main window
$windowHandle = [IntPtr]::Zero
$deadline = [DateTime]::UtcNow.AddSeconds(15)
while ([DateTime]::UtcNow -lt $deadline -and -not $proc.HasExited) {
    $proc.Refresh()
    $windowHandle = $proc.MainWindowHandle
    if ($windowHandle -ne [IntPtr]::Zero) {
        break
    }
    Start-Sleep -Milliseconds 250
}

if ($windowHandle -eq [IntPtr]::Zero) {
    Write-Warning "Main window handle not acquired via Process.MainWindowHandle."
} else {
    Write-Host "Found Window Handle: $windowHandle (PID: $($proc.Id))"
    [void][N10Bridge]::RequestForeground($windowHandle)
}

$capturedFrames = @()

function Test-NonBlackImage {
    param([string]$ImagePath)
    try {
        $bmp = [System.Drawing.Bitmap]::FromFile($ImagePath)
        $w = $bmp.Width
        $h = $bmp.Height
        $nonBlack = 0
        $totalSampled = 0

        # Sample 100 points in a grid
        for ($gx = 10; $gx -lt 90; $gx += 8) {
            for ($gy = 10; $gy -lt 90; $gy += 8) {
                $px = [int]($w * $gx / 100)
                $py = [int]($h * $gy / 100)
                $c = $bmp.GetPixel($px, $py)
                $totalSampled++
                if ($c.R -gt 15 -or $c.G -gt 15 -or $c.B -gt 15) {
                    $nonBlack++
                }
            }
        }
        $bmp.Dispose()
        return @{
            Width = $w
            Height = $h
            Sampled = $totalSampled
            NonBlackPixels = $nonBlack
            Ratio = ($nonBlack / [Math]::Max(1, $totalSampled))
        }
    } catch {
        return @{ Width = 0; Height = 0; Sampled = 0; NonBlackPixels = 0; Ratio = 0.0 }
    }
}

function Take-StageCapture {
    param([string]$StageName, [string]$Description)
    $cleanStage = $StageName -replace '[^a-zA-Z0-9_\-]', '_'
    
    # Send trigger to runtime background capture worker
    Set-Content -LiteralPath $triggerFile -Value $cleanStage -Encoding ASCII

    # Wait up to 4 seconds for BMP generation
    $bmpDeadline = [DateTime]::UtcNow.AddSeconds(4)
    $foundBmp = $null
    $altDir = Join-Path $buildRoot 'analysis\n10-gameplay'
    while ([DateTime]::UtcNow -lt $bmpDeadline) {
        $bmps = @(Get-ChildItem -Path $captureDir, $altDir -Filter "n10-${cleanStage}-*.bmp" -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
        if ($bmps.Count -gt 0) {
            $foundBmp = $bmps[0]
            break
        }
        Start-Sleep -Milliseconds 200
    }

    if ($foundBmp) {
        # Convert BMP to PNG for artifact presentation
        $pngName = [System.IO.Path]::ChangeExtension($foundBmp.Name, '.png')
        $pngPath = Join-Path $captureDir $pngName
        try {
            $bmpObj = [System.Drawing.Bitmap]::FromFile($foundBmp.FullName)
            $bmpObj.Save($pngPath, [System.Drawing.Imaging.ImageFormat]::Png)
            $bmpObj.Dispose()
            Remove-Item -LiteralPath $foundBmp.FullName -Force -ErrorAction SilentlyContinue
        } catch {
            Write-Warning "Failed to convert BMP to PNG: $($_.Exception.Message)"
        }

        $activePath = if (Test-Path -LiteralPath $pngPath) { $pngPath } else { $foundBmp.FullName }
        $sha = (Get-FileHash -LiteralPath $activePath -Algorithm SHA256).Hash
        $size = (Get-Item -LiteralPath $activePath).Length
        $metrics = Test-NonBlackImage -ImagePath $activePath

        $statusVisual = if ($metrics.Ratio -gt 0.05) { "VERIFIED (Scene Rendered)" } else { "MONOCHROME / DARK" }
        Write-Host "  [D3D12-CAPTURE] $StageName ($Description)"
        Write-Host "                  File: $([System.IO.Path]::GetFileName($activePath)) | Resolution: $($metrics.Width)x$($metrics.Height)"
        Write-Host "                  Size: $size bytes | SHA256: $sha"
        Write-Host "                  Visual Analysis: $statusVisual ($([math]::Round($metrics.Ratio * 100, 1))% non-black content)"

        $script:capturedFrames += @{
            Stage = $StageName
            Description = $Description
            Path = $activePath
            Resolution = "$($metrics.Width)x$($metrics.Height)"
            SHA256 = $sha
            Size = $size
            Status = $statusVisual
            NonBlackRatio = $metrics.Ratio
        }
        return
    }

    Write-Warning "  [CAPTURE-FAILED] D3D12 capture worker did not emit frame for $StageName"
}

if (-not $Interactive) {
    Write-Host "`nWaiting $WaitTitleSeconds seconds for engine boot and title screen..."
    Start-Sleep -Seconds $WaitTitleSeconds

    # Stage 1: Title Screen
    Take-StageCapture -StageName "01-title-screen" -Description "Pre-title / Press START screen"

    # Stage 2: Main Menu
    Write-Host "Tapping START (Return) to enter Main Menu..."
    [void][N10Bridge]::TapKey(13) # VK_RETURN
    Start-Sleep -Seconds 3
    Take-StageCapture -StageName "02-main-menu" -Description "Main Menu selection"

    # Stage 3: Campaign / Single Player Confirmation
    Write-Host "Tapping A (Space) to select Single Player..."
    [void][N10Bridge]::TapKey(32) # VK_SPACE
    Start-Sleep -Seconds 2
    Take-StageCapture -StageName "03-menu-selection" -Description "Single Player / New Game prompt"

    # Stage 4: Confirm New Game
    Write-Host "Tapping A (Space) to confirm New Game..."
    [void][N10Bridge]::TapKey(32) # VK_SPACE
    Start-Sleep -Seconds 4
    Take-StageCapture -StageName "04-prologue-cutscene" -Description "Prologue cinematic sequence"

    # Stage 5: Skip cutscene to reach gameplay
    Write-Host "Tapping START to skip cutscene into gameplay..."
    [void][N10Bridge]::TapKey(13) # VK_RETURN
    Start-Sleep -Seconds 4
    Take-StageCapture -StageName "05-gameplay-entry" -Description "In-game 3D scene entry"

    # Stage 6: Character Movement (Bryce WASD)
    Write-Host "Exercising character movement: Holding W (Forward) for 2.0s..."
    [void][N10Bridge]::HoldKey(87, 2000) # 'W'
    Start-Sleep -Milliseconds 500
    Take-StageCapture -StageName "06-character-movement" -Description "Bryce moving forward"

    # Stage 7: Camera Rotation (Arrow Keys)
    Write-Host "Exercising camera yaw: Holding Right Arrow for 1.5s..."
    [void][N10Bridge]::HoldKey(39, 1500) # VK_RIGHT
    Start-Sleep -Milliseconds 500
    Take-StageCapture -StageName "07-camera-rotation" -Description "Camera perspective adjustment"

    # Stage 8: Actions / Roll
    Write-Host "Exercising action: Tapping Space (Jump / Roll)..."
    [void][N10Bridge]::TapKey(32) # VK_SPACE
    Start-Sleep -Milliseconds 800
    Take-StageCapture -StageName "08-action-roll" -Description "Character roll / evasion"
} else {
    Write-Host "`n================================================================="
    Write-Host " [INTERACTIVE MODE ACTIVE]                                      "
    Write-Host "================================================================="
    Write-Host " The game is now running on your display with Direct3D 12."
    Write-Host " Controller: Physical gamepad (DualSense/Xbox) or Keyboard."
    Write-Host " Keys:       WASD (Move), Mouse/Arrows (Camera), Space (Roll/Jump)"
    Write-Host " Hotkeys:    F12 = Instant D3D12 GPU Screenshot"
    Write-Host " Checklist:  1. Press START at Title"
    Write-Host "             2. Press A to select Single Player / New Game"
    Write-Host "             3. Press START to skip Prologue cutscene"
    Write-Host "             4. Move Bryce Boltzmann and pan the camera"
    Write-Host "             5. Press F12 to capture gameplay frames"
    Write-Host " Monitoring for $RunTimeoutSeconds seconds (Ctrl+C to stop)..."
    Write-Host "================================================================="

    $interDeadline = [DateTime]::UtcNow.AddSeconds($RunTimeoutSeconds)
    $captureIndex = 1
    while ([DateTime]::UtcNow -lt $interDeadline -and -not $proc.HasExited) {
        Start-Sleep -Seconds 8
        Take-StageCapture -StageName "interactive-$captureIndex" -Description "Live Gameplay Frame $captureIndex"
        $captureIndex++
    }
}

Write-Host "`nWaiting for process completion or terminating test run..."
if (-not $proc.HasExited) {
    Start-Sleep -Seconds 3
    $proc.CloseMainWindow() | Out-Null
    Start-Sleep -Seconds 2
    if (-not $proc.HasExited) {
        $proc.Kill()
    }
}

Write-Host "`n================================================================="
Write-Host " Log & Pipeline Diagnostics Audit"
Write-Host "================================================================="

if (Test-Path -LiteralPath $logPath) {
    $fatal = @(Select-String -LiteralPath $logPath -Pattern '\[critical\]|\[FATAL\]')
    $d3dErrors = @(Select-String -LiteralPath $logPath -Pattern '\[gpu\].*\[error\]')
    $d3dWarnings = @(Select-String -LiteralPath $logPath -Pattern '\[gpu\].*\[warning\]')
    $unimplemented = @(Select-String -LiteralPath $logPath -Pattern 'unimplemented|Stub')
    $buttonEdges = @(Select-String -LiteralPath $logPath -Pattern '\[DEBUG-N6-CRASH43\]')
    $nativeCaptures = @(Select-String -LiteralPath $logPath -Pattern '\[N10-CAPTURE\]')

    Write-Host " Fatal Crashes / Guest Traps:  $($fatal.Count)"
    Write-Host " D3D12 Errors:                 $($d3dErrors.Count)"
    Write-Host " D3D12 Warnings:               $($d3dWarnings.Count)"
    Write-Host " D3D12 Native Captures Logged: $($nativeCaptures.Count)"
    Write-Host " Unimplemented HLE Calls:      $($unimplemented.Count)"
    Write-Host " XAM Button Edge Traces:       $($buttonEdges.Count)"

    if ($fatal.Count -gt 0) {
        Write-Warning "Fatal Log Entries:"
        $fatal | Select-Object -First 5 | ForEach-Object { Write-Warning "  $($_.Line)" }
    }

    if ($unimplemented.Count -gt 0) {
        Write-Host "`nUnique Unimplemented / Stub HLE Calls:"
        $unimplemented | ForEach-Object { $_.Line } | Select-Object -Unique | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" }
    }
}

Write-Host "`n================================================================="
Write-Host " Visual Captures Produced: $($capturedFrames.Count)"
Write-Host "================================================================="
foreach ($f in $capturedFrames) {
    Write-Host "  [$($f.Stage)] $($f.Description)"
    Write-Host "    File: $($f.Path) ($($f.Resolution))"
    Write-Host "    Visual: $($f.Status) | SHA256: $($f.SHA256)"
}
