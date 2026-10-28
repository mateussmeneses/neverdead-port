param([switch]$ValidateOnly, [string]$GameFolder)
$ErrorActionPreference = 'Stop'

function Test-GameFolder([string]$Folder) {
    if ([string]::IsNullOrWhiteSpace($Folder) -or !(Test-Path -LiteralPath $Folder -PathType Container)) {
        throw 'Select an existing extracted NeverDead folder.'
    }
    foreach ($relative in @('default.xex', 'Envs\NeverDead.Xbox360_textures', 'GUIMenu\loadingInitial.guiBE', 'Text\Menu\Menu_En.asrBE')) {
        $path = Join-Path $Folder $relative
        if (!(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -eq 0) {
            throw "Missing or empty game file: $relative. Select the root of your extracted NeverDead copy."
        }
    }
}

function Get-LaunchArguments([string]$Root, [string]$Data, [string]$Log) {
    foreach ($path in @($Root, $Data, $Log)) {
        if ([string]::IsNullOrWhiteSpace($path) -or $path.Contains('"') -or $path.Contains("`n") -or $path.Contains("`r")) {
            throw 'Invalid path in launch arguments.'
        }
    }
    $gamePath = Join-Path $Root '.'
    return '--game_data_root="{0}" --user_data_root="{1}\user" --cache_root="{1}\cache" --log_file="{2}" --render_target_path_d3d12=rov --gpu_allow_invalid_fetch_constants=false --log_level=info' -f $gamePath, $Data.TrimEnd('\'), $Log
}

if ($ValidateOnly) { Test-GameFolder $GameFolder; return }
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$data = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'NeverDeadPort'
[IO.Directory]::CreateDirectory($data) | Out-Null
$settings = Join-Path $data 'game-folder.txt'
$form = New-Object Windows.Forms.Form
$form.Text = 'NeverDead - Alpha launcher'
$form.ClientSize = New-Object Drawing.Size(600, 180)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$label = New-Object Windows.Forms.Label
$label.Text = 'Select your extracted game folder. Renderer: ROV (recommended).'
$label.SetBounds(15, 15, 570, 25)
$folder = New-Object Windows.Forms.TextBox
$folder.SetBounds(15, 45, 465, 25)
if (Test-Path -LiteralPath $settings) { $folder.Text = [IO.File]::ReadAllText($settings) }
$browse = New-Object Windows.Forms.Button
$browse.Text = 'Browse...'
$browse.SetBounds(490, 43, 95, 28)
$browse.Add_Click({
    $dialog = New-Object Windows.Forms.FolderBrowserDialog
    try { if ($dialog.ShowDialog() -eq 'OK') { $folder.Text = $dialog.SelectedPath } }
    finally { $dialog.Dispose() }
})
$play = New-Object Windows.Forms.Button
$play.Text = 'Play'
$play.SetBounds(15, 100, 160, 35)
$play.Add_Click({
    try {
        Test-GameFolder $folder.Text
        $exe = Join-Path $PSScriptRoot 'neverdead.exe'
        foreach ($name in @('neverdead.exe', 'rexruntime.dll', 'rexgpu-xenos.dll', 'neverdead.toml')) {
            if (!(Test-Path -LiteralPath (Join-Path $PSScriptRoot $name) -PathType Leaf)) { throw "Port file missing: $name. Extract the complete release ZIP." }
        }
        foreach ($name in @('user', 'cache', 'logs')) { [IO.Directory]::CreateDirectory((Join-Path $data $name)) | Out-Null }
        # A trailing separator before a closing quote changes Windows argv parsing.
        $root = Join-Path (Resolve-Path -LiteralPath $folder.Text).Path '.'
        $log = Join-Path $data ('logs\session-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
        $arguments = Get-LaunchArguments $root $data $log
        [IO.File]::WriteAllText($settings, $root)
        Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $PSScriptRoot | Out-Null
        $form.Close()
    } catch { [Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Unable to launch') | Out-Null }
})
$saves = New-Object Windows.Forms.Button
$saves.Text = 'Open saves'
$saves.SetBounds(190, 100, 160, 35)
$saves.Add_Click({ $path = Join-Path $data 'user'; [IO.Directory]::CreateDirectory($path) | Out-Null; Start-Process explorer.exe -ArgumentList ('"' + $path + '"') })
$logs = New-Object Windows.Forms.Button
$logs.Text = 'Open logs'
$logs.SetBounds(365, 100, 160, 35)
$logs.Add_Click({ $path = Join-Path $data 'logs'; [IO.Directory]::CreateDirectory($path) | Out-Null; Start-Process explorer.exe -ArgumentList ('"' + $path + '"') })
$form.Controls.AddRange(@($label, $folder, $browse, $play, $saves, $logs))
[void]$form.ShowDialog()
$form.Dispose()
