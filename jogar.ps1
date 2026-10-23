<#
.SYNOPSIS
    Inicia o NeverDead PC Port em modo livre para você jogar e testar.
#>
[CmdletBinding()]
param()

$root = $PSScriptRoot
$buildDir = Join-Path $root 'build\n2-neverdead'
$exe = Join-Path $buildDir 'neverdead.exe'
$gameData = 'C:\projetos\NeverDeadxex'
$userDir = Join-Path $buildDir 'user'
$cacheDir = Join-Path $buildDir 'cache'
$logDir = Join-Path $buildDir 'logs'
$captureDir = Join-Path $root 'analysis\n10-gameplay'

New-Item -ItemType Directory -Path $userDir, $cacheDir, $logDir, $captureDir -Force | Out-Null

$env:NEVERDEAD_CAPTURE_DIR = $captureDir

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " NeverDead PC Port — Modo Jogador / Teste Interativo             " -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " Executável: $exe"
Write-Host " Controle:   DualSense / Xbox ou Teclado & Mouse"
Write-Host " Teclas:     WASD (Mover), Mouse/Setas (Câmera), Espaço (Rolar/Pular)"
Write-Host " Hotkeys:    F12 = Capturar quadro Direct3D 12 em alta resolução"
Write-Host "             F3  = Painel de FPS e Estatísticas"
Write-Host "             F4  = Configurações Gráficas / Overlays"
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "Pressione qualquer tecla ou feche a janela do jogo quando terminar.`n"

$args = @(
    "--game_data_root=$gameData",
    "--user_data_root=$userDir",
    "--cache_root=$cacheDir",
    "--mnk_mode=true",
    "--gpu_allow_invalid_fetch_constants=false",
    "--log_level=info",
    "--log_file=$(Join-Path $logDir 'gameplay_session.log')"
)

Set-Location $buildDir
& $exe $args
