@echo off
title NeverDead PC Port
echo =================================================================
echo  Iniciando NeverDead PC Port (Xbox 360 -^> Direct3D 12 Native)
echo =================================================================
echo  Controle: DualSense / Xbox Gamepad ou Teclado/Mouse (WASD + Espaco)
echo  Captura:  Pressione F12 a qualquer momento para tirar print D3D12
echo  Overlays: F3 (FPS/Debug), F4 (Configuracoes), ` (Console)
echo =================================================================
echo.

cd /d "C:\projetos\neverdead\build\n2-neverdead"
if not exist "user" mkdir user
if not exist "cache" mkdir cache
if not exist "logs" mkdir logs

set NEVERDEAD_CAPTURE_DIR=C:\projetos\neverdead\analysis\n10-gameplay

neverdead.exe ^
  --game_data_root="C:\projetos\NeverDeadxex" ^
  --user_data_root="C:\projetos\neverdead\build\n2-neverdead\user" ^
  --cache_root="C:\projetos\neverdead\build\n2-neverdead\cache" ^
  --mnk_mode=true ^
  --gpu_allow_invalid_fetch_constants=false ^
  --log_level=info ^
  --log_file="logs\gameplay_session.log"

pause
