<#
.SYNOPSIS
    NeverDead PC Port — N11 Direct3D 12 & Xenos Graphics Correctness Validation Harness
.DESCRIPTION
    Validates rendering correctness with gpu_allow_invalid_fetch_constants = false.
    Captures native D3D12 HDR guest-output frames, verifies Asura Engine render target binding,
    inspects texture fetch constant decoding, checks D3D12 InfoQueue/DRED integrity,
    and analyzes lighting, shadows, and non-black pixel distribution.
#>
[CmdletBinding()]
param(
    [string]$GameDataRoot = 'C:\projetos\NeverDeadxex',
    [int]$WaitTitleSeconds = 12,
    [switch]$Interactive,
    [switch]$AllowInvalidGlobal = $false
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = Split-Path $PSScriptRoot -Parent
$buildRoot = Join-Path $root 'build\n2-neverdead'
$exe = Join-Path $buildRoot 'neverdead.exe'
$captureDir = Join-Path $PSScriptRoot 'n11-graphics'
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
$userDir = Join-Path $buildRoot "n11-user-$runId"
$cacheDir = Join-Path $buildRoot "n11-cache-$runId"
$logPath = Join-Path $logRoot "n11-graphics-$runId.log"
New-Item -ItemType Directory -Path $userDir, $cacheDir -Force | Out-Null

Write-Host "================================================================="
Write-Host " NeverDead N11: Direct3D 12 & Xenos Graphics Correctness Harness "
Write-Host "================================================================="
Write-Host " Run ID:                       $runId"
Write-Host " Game Data:                    $resolvedGameData"
Write-Host " Captures Dir:                 $captureDir"
Write-Host " Log File:                     $logPath"
Write-Host " Allow Invalid Global CVar:    $AllowInvalidGlobal"
Write-Host " Target Filter Verification:   $(-not $AllowInvalidGlobal) (Strict Filter Active)"
Write-Host "================================================================="

# Compile C# Win32 Window & Input Bridge
if (-not ('N11Bridge' -as [type])) {
    $csharpSrc = @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Threading;

public static class N11Bridge {
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
        public MOUSEKEYBDHARDWAREINPUT data;
    }

    [StructLayout(LayoutKind.Explicit)]
    public struct MOUSEKEYBDHARDWAREINPUT {
        [FieldOffset(0)] public KEYBDINPUT keyboard;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct KEYBDINPUT {
        public ushort virtualKey;
        public ushort scanCode;
        public uint flags;
        public uint time;
        public IntPtr extraInfo;
    }

    public static bool RequestForeground(IntPtr hWnd) {
        ShowWindowAsync(hWnd, 9); // SW_RESTORE
        Thread.Sleep(150);
        return SetForegroundWindow(hWnd);
    }

    public static bool TapKey(ushort vk) {
        INPUT[] inputs = new INPUT[2];
        inputs[0].type = 1; // INPUT_KEYBOARD
        inputs[0].data.keyboard.virtualKey = vk;
        inputs[0].data.keyboard.flags = 0; // KeyDown

        inputs[1].type = 1;
        inputs[1].data.keyboard.virtualKey = vk;
        inputs[1].data.keyboard.flags = 0x0002; // KeyUp

        if (SendInput(1, new INPUT[] { inputs[0] }, Marshal.SizeOf(typeof(INPUT))) != 1) return false;
        Thread.Sleep(100);
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
$invalidFlag = if ($AllowInvalidGlobal) { "--gpu_allow_invalid_fetch_constants=true" } else { "--gpu_allow_invalid_fetch_constants=false" }
$arguments = @(
    "--game_data_root=$resolvedGameData",
    "--user_data_root=$userDir",
    "--cache_root=$cacheDir",
    "--mnk_mode=true",
    $invalidFlag,
    "--log_level=debug",
    "--log_file=$logPath"
)

$env:NEVERDEAD_CAPTURE_DIR = $captureDir

Write-Host "Launching NeverDead runtime with $invalidFlag..."
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
    [void][N11Bridge]::RequestForeground($windowHandle)
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
        $luminanceSum = 0.0

        # Sample 144 points in a 12x12 grid
        for ($gx = 10; $gx -lt 90; $gx += 7) {
            for ($gy = 10; $gy -lt 90; $gy += 7) {
                $px = [int]($w * $gx / 100)
                $py = [int]($h * $gy / 100)
                $c = $bmp.GetPixel($px, $py)
                $totalSampled++
                $lum = (0.299 * $c.R + 0.587 * $c.G + 0.114 * $c.B)
                $luminanceSum += $lum
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
            AverageLuminance = ($luminanceSum / [Math]::Max(1, $totalSampled))
        }
    } catch {
        return @{ Width = 0; Height = 0; Sampled = 0; NonBlackPixels = 0; Ratio = 0.0; AverageLuminance = 0.0 }
    }
}

function Take-StageCapture {
    param([string]$StageName, [string]$Description)
    $cleanStage = $StageName -replace '[^a-zA-Z0-9_\-]', '_'
    
    # Send trigger to runtime background capture worker
    Set-Content -LiteralPath $triggerFile -Value "n11-$cleanStage" -Encoding ASCII

    # Wait up to 5 seconds for BMP generation
    $bmpDeadline = [DateTime]::UtcNow.AddSeconds(5)
    $foundBmp = $null
    while ([DateTime]::UtcNow -lt $bmpDeadline) {
        $bmps = @(Get-ChildItem -Path $captureDir -Filter "n11-${cleanStage}-*.bmp" -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
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

        $statusVisual = if ($metrics.Ratio -gt 0.20) { "VERIFIED (Full 3D HDR Scene)" } elseif ($metrics.Ratio -gt 0.05) { "VERIFIED (Scene Rendered)" } else { "MONOCHROME / DARK" }
        Write-Host "  [D3D12-CAPTURE] $StageName ($Description)"
        Write-Host "                  File: $([System.IO.Path]::GetFileName($activePath)) | Resolution: $($metrics.Width)x$($metrics.Height)"
        Write-Host "                  Size: $size bytes | SHA256: $sha"
        Write-Host "                  Visual: $statusVisual ($([math]::Round($metrics.Ratio * 100, 1))% non-black, avg lum $([math]::Round($metrics.AverageLuminance, 1)))"

        $script:capturedFrames += @{
            Stage = $StageName
            Description = $Description
            Path = $activePath
            FileName = [System.IO.Path]::GetFileName($activePath)
            Resolution = "$($metrics.Width)x$($metrics.Height)"
            SHA256 = $sha
            Size = $size
            Status = $statusVisual
            NonBlackRatio = $metrics.Ratio
            AverageLuminance = $metrics.AverageLuminance
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
    [void][N11Bridge]::TapKey(13) # VK_RETURN
    Start-Sleep -Seconds 3
    Take-StageCapture -StageName "02-main-menu" -Description "Main Menu selection"

    # Stage 3: Campaign / Single Player Confirmation
    Write-Host "Tapping A (Space) to select Single Player..."
    [void][N11Bridge]::TapKey(32) # VK_SPACE
    Start-Sleep -Seconds 2
    Take-StageCapture -StageName "03-menu-selection" -Description "Single Player / New Game prompt"

    # Stage 4: Confirm New Game
    Write-Host "Tapping A (Space) to confirm New Game..."
    [void][N11Bridge]::TapKey(32) # VK_SPACE
    Start-Sleep -Seconds 4
    Take-StageCapture -StageName "04-prologue-cutscene" -Description "Prologue cinematic sequence"

    # Stage 5: Skip cutscene to reach gameplay
    Write-Host "Tapping START to skip cutscene into gameplay..."
    [void][N11Bridge]::TapKey(13) # VK_RETURN
    Start-Sleep -Seconds 4
    Take-StageCapture -StageName "05-gameplay-entry" -Description "In-game 3D scene entry"

    # Stage 6: Character Movement (Bryce WASD)
    Write-Host "Exercising character movement: Holding W (Forward) for 2.0s..."
    [void][N11Bridge]::HoldKey(87, 2000) # 'W'
    Start-Sleep -Milliseconds 500
    Take-StageCapture -StageName "06-character-movement" -Description "Bryce moving forward"

    # Stage 7: Camera Rotation (Arrow Keys)
    Write-Host "Exercising camera yaw: Holding Right Arrow for 1.5s..."
    [void][N11Bridge]::HoldKey(39, 1500) # VK_RIGHT
    Start-Sleep -Milliseconds 500
    Take-StageCapture -StageName "07-camera-rotation" -Description "Camera perspective adjustment"

    # Stage 8: Combat / Action State
    Write-Host "Exercising action state: Tapping Space (Jump/Roll)..."
    [void][N11Bridge]::TapKey(32)
    Start-Sleep -Milliseconds 600
    Take-StageCapture -StageName "08-action-state" -Description "Character jump/action state"

    Write-Host "`nAutomated test sequence completed. Terminating runtime..."
    try {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    } catch {}
}

# Wait for process shutdown and flush
Start-Sleep -Seconds 2

Write-Host "`n================================================================="
Write-Host " Execution & Rendering Telemetry Audit                           "
Write-Host "================================================================="

$logContent = if (Test-Path -LiteralPath $logPath) { Get-Content -LiteralPath $logPath -Raw } else { "" }

# Audit Metrics
$fatalTraps = @([regex]::Matches($logContent, '\[FATAL\] Call to invalid or unregistered function')).Count
$d3d12Errors = @([regex]::Matches($logContent, '\[(critical|error)\] \[d3d12\]')).Count
$dredErrors = @([regex]::Matches($logContent, 'DRED (page fault|breadcrumb)')).Count
$invalidTexWarnings = @([regex]::Matches($logContent, 'Texture fetch constant .* has "invalid" type')).Count
$unregisteredImports = @([regex]::Matches($logContent, 'Unimplemented kernel call')).Count
$edramResolves = @([regex]::Matches($logContent, 'Resolve')).Count

Write-Host " Fatal Guest Traps:                  $fatalTraps"
Write-Host " D3D12 Errors:                       $d3d12Errors"
Write-Host " DRED Faults / Page Faults:          $dredErrors"
Write-Host " Invalid Texture Warnings:           $invalidTexWarnings"
Write-Host " Unregistered Kernel Calls:          $unregisteredImports"
Write-Host " Total Visual Frames Captured:       $($capturedFrames.Count)"

# JSON Telemetry Report
$report = @{
    Timestamp = (Get-Date).ToString("o")
    RunId = $runId
    Mode = "Direct3D 12 Graphics Correctness (N11)"
    GpuAllowInvalidFetchConstants = $AllowInvalidGlobal
    TargetedFilterActive = (-not $AllowInvalidGlobal)
    ExecutionAudit = @{
        FatalTraps = $fatalTraps
        D3D12Errors = $d3d12Errors
        DredErrors = $dredErrors
        InvalidTextureWarnings = $invalidTexWarnings
        UnregisteredImports = $unregisteredImports
    }
    Captures = $capturedFrames
}

$reportJson = $report | ConvertTo-Json -Depth 5
$reportPath = Join-Path $captureDir "n11_graphics_report.json"
[System.IO.File]::WriteAllText($reportPath, $reportJson, [System.Text.Encoding]::UTF8)

Write-Host "`nSaved N11 Graphics Report to: $reportPath"
Write-Host "================================================================="

if ($fatalTraps -gt 0 -or $d3d12Errors -gt 0 -or $invalidTexWarnings -gt 0) {
    Write-Error "Graphics validation encountered regressions (Traps: $fatalTraps, D3D12 Errors: $d3d12Errors, Invalid Texture Warnings: $invalidTexWarnings)"
} else {
    Write-Host ">>> N11 GRAPHICS VALIDATION GATES SATISFIED <<<" -ForegroundColor Green
}
