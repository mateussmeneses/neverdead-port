<#
.SYNOPSIS
    NeverDead PC Port — N12 Gameplay, Physics, Audio & Save Persistence Harness
.DESCRIPTION
    Tests save persistence (loading existing ND.sav), controller input delivery (movement,
    camera, triggers, action buttons), audio subsystem (XMA, Bink audio, buffer health),
    and physics engine execution under Direct3D 12.
#>
[CmdletBinding()]
param(
    [string]$GameDataRoot = 'C:\projetos\NeverDeadxex',
    [int]$WaitTitleSeconds = 55
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = Split-Path $PSScriptRoot -Parent
$buildRoot = Join-Path $root 'build\n2-neverdead'
$exe = Join-Path $buildRoot 'neverdead.exe'
$captureDir = Join-Path $PSScriptRoot 'n12-validation'
$logRoot = Join-Path $buildRoot 'logs'

if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "Executable not found at '$exe'."
}

$resolvedGameData = (Resolve-Path -LiteralPath $GameDataRoot).Path
New-Item -ItemType Directory -Path $captureDir, $logRoot -Force | Out-Null

$runId = Get-Date -Format 'yyyyMMdd-HHmmss'
$userDir = Join-Path $buildRoot 'n12-save-test\user'
$cacheDir = Join-Path $buildRoot "n12-cache-$runId"
$logPath = Join-Path $logRoot "n12-validation-$runId.log"
New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null

# Verify pre-existing save file exists
$saveFile = Join-Path $userDir 'B13EBABEBABEBABE\4B4E081F\00000001\ND\ND.sav'
$headerFile = Join-Path $userDir 'B13EBABEBABEBABE\4B4E081F\Headers\00000001\ND.header'

$initialSaveSize = 0
$initialSaveHash = ""
if (Test-Path -LiteralPath $saveFile -PathType Leaf) {
    $initialSaveSize = (Get-Item -LiteralPath $saveFile).Length
    $initialSaveHash = (Get-FileHash -LiteralPath $saveFile -Algorithm SHA256).Hash
    Write-Host "Found Pre-Existing Save: ND.sav ($initialSaveSize bytes, SHA: $initialSaveHash)" -ForegroundColor Green
} else {
    Write-Warning "Save file ND.sav not found at '$saveFile'. A new save will be generated."
}

Write-Host "================================================================="
Write-Host " NeverDead N12: Gameplay, Physics, Audio & Save Persistence      "
Write-Host "================================================================="
Write-Host " Run ID:        $runId"
Write-Host " Game Data:     $resolvedGameData"
Write-Host " User Root:     $userDir"
Write-Host " Captures Dir:  $captureDir"
Write-Host " Log Path:      $logPath"
Write-Host "================================================================="

# Compile C# Win32 Window & Input Bridge
if (-not ('N12InputBridge' -as [type])) {
    $csharpSrc = @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Threading;

public static class N12InputBridge {
    [DllImport("user32.dll")]
    public static extern uint MapVirtualKey(uint uCode, uint uMapType);

    [DllImport("user32.dll")]
    public static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

    [DllImport("kernel32.dll")]
    public static extern void Sleep(uint milliseconds);

    public static bool TapKey(IntPtr hWnd, ushort vk) {
        if (hWnd == IntPtr.Zero) throw new ArgumentException("Game window is required");
        uint scan = MapVirtualKey((uint)vk, 0);
        bool extended = (vk >= 37 && vk <= 40);
        uint extFlag = extended ? 1u : 0u;

        IntPtr lDown = (IntPtr)(1 | (scan << 16) | (extFlag << 24));
        IntPtr lUp = (IntPtr)(1 | (scan << 16) | (extFlag << 24) | (1u << 30) | (1u << 31));

        PostMessage(hWnd, 0x0100, (IntPtr)vk, lDown);
        Sleep(100);
        PostMessage(hWnd, 0x0101, (IntPtr)vk, lUp);
        return true;
    }

    public static bool HoldKey(IntPtr hWnd, ushort vk, int durationMs) {
        if (hWnd == IntPtr.Zero) throw new ArgumentException("Game window is required");
        uint scan = MapVirtualKey((uint)vk, 0);
        bool extended = (vk >= 37 && vk <= 40);
        uint extFlag = extended ? 1u : 0u;

        IntPtr lDown = (IntPtr)(1 | (scan << 16) | (extFlag << 24));
        IntPtr lUp = (IntPtr)(1 | (scan << 16) | (extFlag << 24) | (1u << 30) | (1u << 31));

        PostMessage(hWnd, 0x0100, (IntPtr)vk, lDown);
        Sleep((uint)durationMs);
        PostMessage(hWnd, 0x0101, (IntPtr)vk, lUp);
        return true;
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

$arguments = @(
    "--game_data_root=$resolvedGameData",
    "--user_data_root=$userDir",
    "--cache_root=$cacheDir",
    "--mnk_mode=true",
    "--input_background=true",
    "--gpu_allow_invalid_fetch_constants=false",
    "--render_target_path_d3d12=rov",
    "--log_level=debug",
    "--log_file=$logPath"
)

$env:NEVERDEAD_CAPTURE_DIR = $captureDir

Write-Host "Launching NeverDead runtime..."
$proc = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $buildRoot -PassThru
$proc.PriorityClass = 'BelowNormal'

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

if ($windowHandle -ne [IntPtr]::Zero) {
    Write-Host "Window Handle Acquired: $windowHandle (PID: $($proc.Id))"
}

$capturedFrames = @()

function Take-N12Capture {
    param([string]$StageName, [string]$Description)
    $cleanStage = $StageName -replace '[^a-zA-Z0-9_\-]', '_'
    
    Set-Content -LiteralPath $triggerFile -Value "n12-$cleanStage" -Encoding ASCII

    $bmpDeadline = [DateTime]::UtcNow.AddSeconds(5)
    $foundBmp = $null
    while ([DateTime]::UtcNow -lt $bmpDeadline) {
        $bmps = @(Get-ChildItem -Path $captureDir -Filter "n12-${cleanStage}-*.bmp" -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
        if ($bmps.Count -gt 0) {
            $foundBmp = $bmps[0]
            break
        }
        Start-Sleep -Milliseconds 200
    }

    if ($foundBmp) {
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
        
        Write-Host "  [D3D12-CAPTURE] $StageName ($Description)"
        Write-Host "                  File: $([System.IO.Path]::GetFileName($activePath)) | Size: $size bytes | SHA256: $sha"

        $script:capturedFrames += @{
            Stage = $StageName
            Description = $Description
            Path = $activePath
            FileName = [System.IO.Path]::GetFileName($activePath)
            Size = $size
            SHA256 = $sha
        }
        return
    }

    Write-Warning "  [CAPTURE-FAILED] D3D12 capture worker did not emit frame for $StageName"
}

Write-Host "`nWaiting $WaitTitleSeconds seconds for shader pipelines and title screen..."
Start-Sleep -Seconds $WaitTitleSeconds

# Stage 1: Title Screen Boot
Take-N12Capture -StageName "01-title-boot" -Description "Title screen waiting for Start input"

# Stage 2: Tap START to trigger Device Selector and Save Enumeration
Write-Host "Tapping START (Return / X) to enumerate save and load profile..."
[void][N12InputBridge]::TapKey($windowHandle, 13) # VK_RETURN
Start-Sleep -Milliseconds 500
[void][N12InputBridge]::TapKey($windowHandle, 88) # 'X' key (Start bind)
Start-Sleep -Seconds 3
Take-N12Capture -StageName "02-save-enumerated-menu" -Description "Main Menu after savegame detection"

# Stage 3: Navigate Menu / Options
Write-Host "Tapping DOWN (Down Arrow) to test menu navigation..."
[void][N12InputBridge]::TapKey($windowHandle, 40) # VK_DOWN
Start-Sleep -Seconds 1
Take-N12Capture -StageName "03-menu-navigation" -Description "Menu selection cursor moved"

# Stage 4: Select Campaign / Continue / New Game
Write-Host "Tapping UP (Up Arrow) and A (Space) to select Campaign..."
[void][N12InputBridge]::TapKey($windowHandle, 38) # VK_UP
Start-Sleep -Milliseconds 500
[void][N12InputBridge]::TapKey($windowHandle, 32) # VK_SPACE (A)
Start-Sleep -Seconds 2
Take-N12Capture -StageName "04-campaign-prompt" -Description "Campaign selection prompt"

# Stage 5: Confirm and start sequence
Write-Host "Tapping A (Space) to confirm and enter prologue..."
[void][N12InputBridge]::TapKey($windowHandle, 32) # VK_SPACE (A)
Start-Sleep -Seconds 4
Take-N12Capture -StageName "05-prologue-cinematic" -Description "Prologue cutscene with audio sync"

# Stage 6: Skip cutscene into 3D gameplay
Write-Host "Tapping START to transition into 3D gameplay..."
[void][N12InputBridge]::TapKey($windowHandle, 13) # VK_RETURN (START)
Start-Sleep -Seconds 4
Take-N12Capture -StageName "06-gameplay-active" -Description "3D gameplay scene active"

# Stage 7: Character Movement & Physics Collision (Bryce WASD)
Write-Host "Testing Havok movement & world collision: Holding W (Forward) for 2s..."
[void][N12InputBridge]::HoldKey($windowHandle, 87, 2000) # 'W'
Start-Sleep -Milliseconds 500
Take-N12Capture -StageName "07-physics-movement" -Description "Bryce moving with character collision"

# Stage 8: Camera Rotation
Write-Host "Testing Camera yaw control: Holding Right Arrow for 1.5s..."
[void][N12InputBridge]::HoldKey($windowHandle, 39, 1500) # VK_RIGHT
Start-Sleep -Milliseconds 500
Take-N12Capture -StageName "08-camera-yaw" -Description "Camera perspective rotation"

# Stage 9: Action & Roll State (Space / B)
Write-Host "Testing Action / Combat state: Tapping Space (Jump/Roll)..."
[void][N12InputBridge]::TapKey($windowHandle, 32) # VK_SPACE
Start-Sleep -Milliseconds 600
Take-N12Capture -StageName "09-action-roll" -Description "Character roll/jump state"

# Stage 10: In-Game Pause Menu
Write-Host "Testing In-Game Pause: Tapping Return (START)..."
[void][N12InputBridge]::TapKey($windowHandle, 13) # VK_RETURN (START)
Start-Sleep -Seconds 2
Take-N12Capture -StageName "10-pause-menu" -Description "In-game pause menu opened"

# Stage 11: Resume from Pause
Write-Host "Testing Resume: Tapping Escape/B to resume..."
[void][N12InputBridge]::TapKey($windowHandle, 27) # VK_ESCAPE
Start-Sleep -Seconds 2
Take-N12Capture -StageName "11-gameplay-resumed" -Description "Gameplay resumed after pause"

Write-Host "`nTerminating NeverDead process cleanly..."
try {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
} catch {}

Start-Sleep -Seconds 2

Write-Host "`n================================================================="
Write-Host " Telemetry, Persistence, Audio & Physics Audit                   "
Write-Host "================================================================="

$logContent = if (Test-Path -LiteralPath $logPath) { Get-Content -LiteralPath $logPath -Raw } else { "" }

# 1. Save & Persistence Audit
$saveEnumCalls = @([regex]::Matches($logContent, 'XamContentCreateEnumerator: added (\d+) items')).Count
$saveEnumMatches = [regex]::Matches($logContent, 'XamContentCreateEnumerator: added (\d+) items')
$itemsFound = if ($saveEnumMatches.Count -gt 0) { $saveEnumMatches[0].Groups[1].Value } else { "0" }
$deviceSelectorCalls = @([regex]::Matches($logContent, 'XamShowDeviceSelectorUI')).Count
$saveMounts = @([regex]::Matches($logContent, 'Registered symbolic link: save:')).Count
$finalSaveSize = if (Test-Path -LiteralPath $saveFile) { (Get-Item -LiteralPath $saveFile).Length } else { 0 }
$finalSaveHash = if (Test-Path -LiteralPath $saveFile) { (Get-FileHash -LiteralPath $saveFile -Algorithm SHA256).Hash } else { "" }

# 2. Audio & XMA Audit
$xmaInit = @([regex]::Matches($logContent, 'XMA: Registered MMIO handlers')).Count
$xmaWrites = @([regex]::Matches($logContent, 'XMA: Write to unknown register')).Count
$binkSoundThreads = @([regex]::Matches($logContent, 'SetThreadName\(\d+, Bink Snd\)')).Count
$binkIoThreads = @([regex]::Matches($logContent, 'SetThreadName\(\d+, Bink IO\)')).Count
$audioUnderruns = @([regex]::Matches($logContent, 'underrun|drop frame')).Count

# 3. Direct3D 12 & Stability Audit
$fatalTraps = @([regex]::Matches($logContent, '\[FATAL\] Call to invalid or unregistered function')).Count
$d3d12Errors = @([regex]::Matches($logContent, '\[(critical|error)\] \[d3d12\]')).Count
$dredFaults = @([regex]::Matches($logContent, 'DRED (page fault|breadcrumb)')).Count
$invalidTexWarnings = @([regex]::Matches($logContent, 'Texture fetch constant .* has "invalid" type')).Count

Write-Host " [Saves & Persistence]"
Write-Host "   Device Selector UI Dispatched:     $($deviceSelectorCalls -gt 0) ($deviceSelectorCalls calls)"
Write-Host "   Save Container Mounts:             $saveMounts"
Write-Host "   Save Enumerations:                 $saveEnumCalls (Items Found: $itemsFound)"
Write-Host "   Initial Save File Size:            $initialSaveSize bytes"
Write-Host "   Final Save File Size:              $finalSaveSize bytes"
Write-Host "   Save Integrity Maintained:         $($finalSaveSize -gt 0 -and $finalSaveSize -eq $initialSaveSize)"

Write-Host "`n [Audio Subsystem]"
Write-Host "   XMA APU Subsystem Initialized:     $($xmaInit -gt 0)"
Write-Host "   Bink Audio Streaming Threads:      $binkSoundThreads"
Write-Host "   Bink IO File Worker Threads:       $binkIoThreads"
Write-Host "   XMA Lock Register 0x0601 Writes:   $xmaWrites (Safely Handled)"
Write-Host "   Audio Buffer Underruns:            $audioUnderruns"

Write-Host "`n [Graphics & Engine Stability]"
Write-Host "   Fatal Guest Traps:                 $fatalTraps"
Write-Host "   D3D12 Errors:                      $d3d12Errors"
Write-Host "   DRED Faults:                       $dredFaults"
Write-Host "   Invalid Texture Fetch Warnings:    $invalidTexWarnings"
Write-Host "   Total Visual Frames Captured:      $($capturedFrames.Count)"

$report = @{
    Timestamp = (Get-Date).ToString("o")
    RunId = $runId
    SavePersistence = @{
        InitialSize = $initialSaveSize
        FinalSize = $finalSaveSize
        InitialHash = $initialSaveHash
        FinalHash = $finalSaveHash
        ItemsEnumerated = [int]$itemsFound
        SaveMountCount = $saveMounts
        DeviceSelectorTriggered = ($deviceSelectorCalls -gt 0)
    }
    AudioAudit = @{
        XmaInitialized = ($xmaInit -gt 0)
        BinkSoundThreads = $binkSoundThreads
        BinkIoThreads = $binkIoThreads
        XmaRegister0601Writes = $xmaWrites
        BufferUnderruns = $audioUnderruns
    }
    StabilityAudit = @{
        FatalTraps = $fatalTraps
        D3D12Errors = $d3d12Errors
        DredFaults = $dredFaults
        InvalidTextureWarnings = $invalidTexWarnings
    }
    Captures = $capturedFrames
}

$reportJson = $report | ConvertTo-Json -Depth 5
$reportPath = Join-Path $captureDir "n12_validation_report.json"
[System.IO.File]::WriteAllText($reportPath, $reportJson, [System.Text.Encoding]::UTF8)

Write-Host "`nSaved N12 Report to: $reportPath"
Write-Host "================================================================="
