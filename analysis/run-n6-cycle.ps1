[CmdletBinding()]
param(
    [string]$GameDataRoot = 'C:\projetos\NeverDeadxex',
    [ValidateRange(1, 10)]
    [int]$Apresses = 3,
    [ValidateRange(1, 120)]
    [int]$FocusTimeoutSeconds = 30,
    [switch]$AutoInput
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = Split-Path $PSScriptRoot -Parent
$buildRoot = Join-Path $root 'build\n2-neverdead'
$exe = Join-Path $buildRoot 'neverdead.exe'
$logRoot = Join-Path $buildRoot 'logs'
$resolvedGameDataRoot = (Resolve-Path -LiteralPath $GameDataRoot).Path

if (-not (Test-Path -LiteralPath (Join-Path $resolvedGameDataRoot 'default.xex') -PathType Leaf)) {
    throw "default.xex was not found under '$resolvedGameDataRoot'."
}

$running = @(Get-Process -Name neverdead -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) {
    $ids = ($running | ForEach-Object { $_.Id }) -join ', '
    throw "NeverDead is already running (PID $ids). Close it before starting another iteration."
}

Write-Host 'Building target neverdead...'
Push-Location $root
try {
    & cmake --build $buildRoot --target neverdead -j 4
    if ($LASTEXITCODE -ne 0) {
        throw "Runtime build failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "Runtime executable was not produced: '$exe'."
}

$runId = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$userDataRoot = Join-Path $buildRoot "n6-cycle-$runId-user"
$cacheRoot = Join-Path $buildRoot "n6-cycle-$runId-cache"
$logPath = Join-Path $logRoot "n6-cycle-$runId.log"
New-Item -ItemType Directory -Path $userDataRoot, $cacheRoot, $logRoot -Force | Out-Null

$arguments = @(
    "--game_data_root=$resolvedGameDataRoot"
    "--user_data_root=$userDataRoot"
    "--cache_root=$cacheRoot"
    '--mnk_mode=true'
    '--gpu_allow_invalid_fetch_constants=true'
    '--log_level=debug'
    "--log_file=$logPath"
)

Write-Host "Run: $runId"
Write-Host "Log: $logPath"
if ($AutoInput) {
    Write-Host "Automatic menu input: Start, then $Apresses A press(es), with XAM edge verification."
}
else {
    Write-Host 'Manual-input mode: use the physical controller for Start -> single-player.'
}

$process = Start-Process -FilePath $exe `
    -ArgumentList $arguments `
    -WorkingDirectory $buildRoot `
    -PassThru

Write-Host "Runtime PID: $($process.Id)."

if ($AutoInput) {
    if (-not ('N6InputBridge' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Threading;

public static class N6InputBridge {
    [StructLayout(LayoutKind.Sequential)]
    private struct INPUT {
        public uint type;
        public InputUnion data;
    }

    [StructLayout(LayoutKind.Explicit)]
    private struct InputUnion {
        [FieldOffset(0)] public KEYBDINPUT keyboard;
        [FieldOffset(0)] public MOUSEINPUT mouse;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct KEYBDINPUT {
        public ushort virtualKey;
        public ushort scanCode;
        public uint flags;
        public uint time;
        public IntPtr extraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MOUSEINPUT {
        public int dx;
        public int dy;
        public uint mouseData;
        public uint flags;
        public uint time;
        public IntPtr extraInfo;
    }

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);

    [DllImport("user32.dll")]
    private static extern bool ShowWindowAsync(IntPtr window, int command);

    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr window);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint count, INPUT[] inputs, int size);

    public static uint ForegroundProcessId() {
        uint processId;
        GetWindowThreadProcessId(GetForegroundWindow(), out processId);
        return processId;
    }

    public static bool RequestForeground(IntPtr window) {
        ShowWindowAsync(window, 9);
        return SetForegroundWindow(window);
    }

    public static bool Tap(ushort virtualKey) {
        INPUT[] inputs = new INPUT[2];
        inputs[0].type = 1;
        inputs[0].data.keyboard.virtualKey = virtualKey;
        inputs[1].type = 1;
        inputs[1].data.keyboard.virtualKey = virtualKey;
        inputs[1].data.keyboard.flags = 0x0002;

        if (SendInput(1, new INPUT[] { inputs[0] }, Marshal.SizeOf(typeof(INPUT))) != 1) {
            return false;
        }

        Thread.Sleep(180);
        return SendInput(1, new INPUT[] { inputs[1] }, Marshal.SizeOf(typeof(INPUT))) == 1;
    }
}
'@
    }

    $focusDeadline = [DateTime]::UtcNow.AddSeconds($FocusTimeoutSeconds)
    $windowHandle = [IntPtr]::Zero
    while ([DateTime]::UtcNow -lt $focusDeadline -and -not $process.HasExited) {
        $process.Refresh()
        $windowHandle = $process.MainWindowHandle
        if ($windowHandle -ne [IntPtr]::Zero) {
            [void][N6InputBridge]::RequestForeground($windowHandle)
            Start-Sleep -Milliseconds 250
            if ([N6InputBridge]::ForegroundProcessId() -eq [uint32]$process.Id) {
                break
            }
        }
        Start-Sleep -Milliseconds 200
    }

    if ($process.HasExited) {
        Write-Warning 'Runtime exited before the menu input sequence could start.'
    }
    elseif ([N6InputBridge]::ForegroundProcessId() -ne [uint32]$process.Id) {
        Write-Warning "Focus guard timed out after $FocusTimeoutSeconds seconds; no keys were sent."
    }
    else {
        function Get-RecentButtonEdges {
            param([string]$Path)
            if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
                return @()
            }
            return @(Select-String -LiteralPath $Path `
                -Pattern '\[DEBUG-N6-CRASH43\].*buttons=0x[0-9A-Fa-f]+' |
                ForEach-Object { $_.Line })
        }

        function Wait-ForButtonEdge {
            param(
                [string]$Path,
                [string[]]$PreviousEdges,
                [uint16]$ExpectedButton,
                [int]$TimeoutSeconds = 3
            )

            $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
            while ([DateTime]::UtcNow -lt $deadline -and -not $process.HasExited) {
                $currentEdges = @(Get-RecentButtonEdges -Path $Path)
                if ($currentEdges.Count -gt $PreviousEdges.Count) {
                    foreach ($line in $currentEdges | Select-Object -Skip $PreviousEdges.Count) {
                        if ($line -match 'buttons=0x([0-9A-Fa-f]+)') {
                            $buttons = [Convert]::ToUInt16($Matches[1], 16)
                            if (($buttons -band $ExpectedButton) -eq $ExpectedButton) {
                                return $true
                            }
                        }
                    }
                }
                Start-Sleep -Milliseconds 200
            }
            return $false
        }

        function Ensure-GameForeground {
            param([IntPtr]$WindowHandle)

            $deadline = [DateTime]::UtcNow.AddSeconds($FocusTimeoutSeconds)
            while ([DateTime]::UtcNow -lt $deadline -and -not $process.HasExited) {
                if ([N6InputBridge]::ForegroundProcessId() -eq [uint32]$process.Id) {
                    return $true
                }
                [void][N6InputBridge]::RequestForeground($WindowHandle)
                Start-Sleep -Milliseconds 200
            }
            return $false
        }

        function Send-GuardedTap {
            param(
                [ushort]$VirtualKey,
                [uint16]$ExpectedButton,
                [string]$Label
            )

            if (-not (Ensure-GameForeground -WindowHandle $windowHandle)) {
                throw "Could not confirm the game in foreground before $Label; remaining input was cancelled."
            }

            $previousEdges = @(Get-RecentButtonEdges -Path $logPath)
            if (-not [N6InputBridge]::Tap($VirtualKey)) {
                throw "Windows rejected the $Label key event."
            }
            if (-not (Wait-ForButtonEdge -Path $logPath -PreviousEdges $previousEdges -ExpectedButton $ExpectedButton)) {
                throw "XAM did not confirm $Label within 3 seconds; remaining input was cancelled."
            }
            Write-Host "XAM confirmed $Label."

            $releaseDeadline = [DateTime]::UtcNow.AddSeconds(3)
            while ([DateTime]::UtcNow -lt $releaseDeadline -and -not $process.HasExited) {
                if ([N6InputBridge]::ForegroundProcessId() -ne [uint32]$process.Id) {
                    throw "Focus changed after $Label; remaining input was cancelled."
                }
                $edges = @(Get-RecentButtonEdges -Path $logPath)
                if ($edges.Count -gt 0 -and $edges[-1] -match 'buttons=0x0000') {
                    return
                }
                Start-Sleep -Milliseconds 100
            }
        }

        try {
            Send-GuardedTap -VirtualKey 13 -ExpectedButton 0x0010 -Label 'Start'
            for ($press = 1; $press -le $Apresses -and -not $process.HasExited; $press++) {
                Start-Sleep -Seconds 1
                Send-GuardedTap -VirtualKey 32 -ExpectedButton 0x1000 -Label "A ($press/$Apresses)"
            }
        }
        catch {
            Write-Warning $_.Exception.Message
        }
    }
}

Write-Host 'Waiting for runtime exit...'
$process.WaitForExit()
$process.Refresh()

if (-not (Test-Path -LiteralPath $logPath -PathType Leaf)) {
    throw "Runtime exited without creating its log: '$logPath'."
}

$fatal = Select-String -LiteralPath $logPath `
    -Pattern '\[FATAL\].*guest address (0x[0-9A-Fa-f]+) \(LR=(0x[0-9A-Fa-f]+), SP=(0x[0-9A-Fa-f]+)\)' |
    Select-Object -Last 1
$buttonEdges = @(Select-String -LiteralPath $logPath `
    -Pattern '\[DEBUG-N6-CRASH43\].*buttons=0x[0-9A-Fa-f]+')
$pressedButtons = @(
    foreach ($edge in $buttonEdges) {
        if ($edge.Line -match 'buttons=(0x[0-9A-Fa-f]+)' -and $Matches[1] -ne '0x0000') {
            $Matches[1]
        }
    }
) | Select-Object -Unique

Write-Host ''
Write-Host "Process exit code: $($process.ExitCode)"
Write-Host "XAM button edges: $($buttonEdges.Count); non-zero states: $($pressedButtons -join ', ')"
if ($fatal) {
    if ($fatal.Line -match 'guest address (0x[0-9A-Fa-f]+) \(LR=(0x[0-9A-Fa-f]+), SP=(0x[0-9A-Fa-f]+)\)') {
        Write-Host "First actionable fatal: target=$($Matches[1]) LR=$($Matches[2])"
    }
    Write-Host "Fatal log: $($fatal.Line)"
}
else {
    Write-Host 'No invalid-function fatal was found; process exit alone does not prove gameplay.'
}
Write-Host "Full log: $logPath"
