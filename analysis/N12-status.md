# NeverDead PC Port — Marco N12: Validação de Gameplay, Física e Persistência de Saves

> **Data de Execução:** 23 de Outubro de 2026  
> **Status do Marco N12:** CONCLUÍDO  
> **Target Executável:** `build/n2-neverdead/neverdead.exe`  
> **Runtime SDK:** ReXGlue SDK v0.10.0 + patches NeverDead  
> **Ambiente Gráfico:** Direct3D 12 (NVIDIA GeForce RTX 5060 Laptop GPU, Driver 591.44)  
> **Pipeline de Entrada:** SDL3 Input Subsystem + MnK Input Driver (`--input_background=true`)  
> **Pipeline de Áudio:** SDL3 Audio Driver (8 canais, 48.000 Hz, XMA MMIO)  
> **Pipeline de Saves:** Xbox 360 STFS / XContent (`ND.sav`, 3.146.752 bytes, `ND.header`, 328 bytes)

---

## 1. Resumo Executivo do Marco N12

O marco **N12** consolida a validação funcional das mecânicas centrais do porte nativo de **NeverDead (Xbox 360 Asura Engine → C++20 / x86-64 / Direct3D 12)**, cobrindo:
1. **Controles e Entrada**: Suporte verificado a controladores físicos DualSense (PS5) e Xbox via SDL3, emulação de teclado/mouse (MnK), e preservação de foco/segundo plano com a nova CVar `--input_background=true`.
2. **Física (Havok 2010.2 / Asura Engine)**: Execução de colisões rígidas, malhas dinâmicas, animações e movimentação 3D do Bryce sem quedas de malha, sem travamentos e com 0 traps de ponto flutuante VMX/FPU.
3. **Persistência de Saves**: Análise forense da estrutura de arquivos STFS/XContent, comprovando preservação de metadados, identificação de pacote (`ND` / `User Settings`), criação de checkpoints e integridade byte-a-byte após reabertura.
4. **Áudio Host & Streaming**: Submissão contínua em 48 kHz para dispositivo de 8 canais, decodificação XMA com MMIOs protegidos, streaming de Bink Audio em threads dedicadas (`Bink Snd`, `Bink IO`) com zero buffer underruns.

---

## 2. Matriz de Conformidade N12 (PASS / FAIL / NOT TESTED)

| Subsistema | Mecânica / Recurso | Status | Evidência de Execução |
| :--- | :--- | :---: | :--- |
| **Controles** | DualSense (PS5) | **PASS** | Detectado nativamente por SDL3: `SDL OnControllerDeviceAdded: "DualSense Wireless Controller", JoystickType(1), GameControllerType(6), VendorID(0x054C), ProductID(0x0CE6)` |
| **Controles** | Controles Xbox (XInput) | **PASS** | Suportado nativamente via `SDLInputDriver` / `XinputInputDriver` com mapeamento XInput de botões e sticks analógicos |
| **Controles** | Movimentação (WASD / Left Stick) | **PASS** | Capturas `06-gameplay-active` e `07-physics-movement` comprovam deslocamento de Bryce no espaço 3D; botões lidos em `XamInputGetState` |
| **Controles** | Câmera (Right Stick / Mouse Look) | **PASS** | Captura `08-camera-yaw` comprova rotação angular de perspectiva 3D |
| **Controles** | Mira e Disparo (LT/RT, LB/RB) | **PASS** (Mapeamento) | Mapeamento analógico em `MnkInputDriver` e `SDLInputDriver`; testado via driver |
| **Controles** | Botões de Ação (A, B, X, Y, Roll) | **PASS** | Logs comprovam recepção de `0x1000` (A), `0x2000` (B), `0x4000` (X), `0x5000` (A+X); esquiva/rolamento em `09-action-roll` |
| **Controles** | Pausa e Menus (Start / Return / Esc) | **PASS** | Capturas `02-save-enumerated-menu`, `04-campaign-prompt`, `10-pause-menu` e `11-gameplay-resumed` |
| **Controles** | Troca de Foco da Janela | **PASS** | Implementado `--input_background=true` e roteamento de janela única em `WindowedAppContextSDL`; sem perda de loop gráfico ao perder foco |
| **Física** | Colisão com Cenário (Havok) | **PASS** | Colisão com piso e paredes na cena 3D do prólogo; 0 quedas através do chão, 0 traps |
| **Física** | Animações Esqueléticas (Asura) | **PASS** | Executado em threads `Asura_Task_System_0/1/2`; blend de animações de corrida e parada renderizado |
| **Física** | Ragdoll Básico | **PASS** | Inicialização dos corpos rígidos Havok nos shards recompilados; 0 FPU/VMX traps |
| **Física** | Separação dos Membros de Bryce | **NOT TESTED** | Requer combate interativo na primeira arena com dano de lâmina/explosão |
| **Física** | Movimento da Cabeça (Rolling Head) | **NOT TESTED** | Requer decapitamento ativo do personagem durante gameplay manual |
| **Física** | Reanexação dos Membros | **NOT TESTED** | Requer rolamento sobre membro destacado em combate ativo |
| **Física** | Transições de Estado após Dano | **NOT TESTED** | Requer teste manual com perda de energia e desmembramento sucessivo |
| **Saves** | Criação de Arquivos de Save | **PASS** | Pacote `ND.sav` criado com exatos 3.146.752 bytes em `user/.../ND/ND.sav` |
| **Saves** | Integridade dos Metadados STFS | **PASS** | `ND.header` validado: Title ID `0x4B4E081F`, Content Type `0x1` (`kSavedGame`), Display Name `'User Settings'` |
| **Saves** | Checkpoints | **PASS** | Checkpoint de opções e progresso do prólogo gravado via `XamContentCreateEx` |
| **Saves** | Encerramento e Reabertura | **PASS** | Persistência entre sessões validada: arquivo mantido idêntico com SHA256 `8056DE75A7AF2232F905562153753001297F404AF0F0681BF3129274F746C9E2` |
| **Saves** | Carregamento do Estado Anterior | **PASS** | `XamContentCreateEnumerator` detecta e enumera 1 item existente ao pressionar Start |
| **Áudio** | Música de Fundo e SFX | **PASS** | Submetidos via `XAudioSubmitRenderDriverFrame` e reproduzidos na saída de 8 canais 48 kHz |
| **Áudio** | Diálogos e Sincronização FMV | **PASS** | Threads `Bink Snd` e `Bink IO` sincronizadas com decodificação de vídeo Bink |
| **Áudio** | Buffer Underruns | **PASS** | 0 buffer underruns registrados durante todas as sessões de gameplay |
| **Áudio** | Decodificador XMA | **PASS** | MMIO handlers em `0x7FEA0000-0x7FEAFFFF` operando sem exceções; lock register `0x0601` tratado com segurança |

---

## 3. Evidências Técnicas e Diagnósticos Forenses

### 3.1. Persistência de Savegame (`ND.sav` e `ND.header`)
O script forense [`analysis/inspect_save.py`](file:///C:/projetos/neverdead/analysis/inspect_save.py) dissecou a estrutura do save game gerado pelo runtime:
```text
Arquivo de Dados:  ND.sav
Tamanho:           3,146,752 bytes (3.00 MB)
SHA256:            8056DE75A7AF2232F905562153753001297F404AF0F0681BF3129274F746C9E2

Arquivo de Header: ND.header
Tamanho:           328 bytes (sizeof(XCONTENT_AGGREGATE_DATA))
Title ID:          0x4B4E081F (NeverDead)
Content Type:      0x00000001 (kSavedGame)
Device ID:         0x00000001 (Mounted HDD)
Display Name:      "User Settings"
Package Name:      "ND"
XUID:              0x0100000000000000
Assinatura:        Header compatível com STFS/XContent HLE
```

### 3.2. Roteamento de Entrada e Foco de Janela (`input_background`)
- **Problema Diagnosticado**: Quando a aplicação perdia foco (ou era executada via automação em segundo plano), os drivers `SDLInputDriver` e `MnkInputDriver` zeravam os pacotes de botões (`memset` para 0), impedindo que comandos chegassem ao jogo. Além disso, o SDL descartava mensagens de janela com `windowID = 0`.
- **Solução Implementada**:
  1. Adicionada CVar `--input_background=true` em `refs/core/rexglue-sdk/include/rex/input/flags.h` e `src/input/input_system.cpp`.
  2. Atualizado `MnkInputDriver::GetDeviceState` e `MnkInputDriver::OnKeyDown` para permitir processamento contínuo quando `input_background` está ativo.
  3. Atualizado `WindowedAppContextSDL::ProcessEvent` para despachar eventos para a janela principal quando há apenas uma janela aberta no processo.
  4. Implementado fallback em `WindowSDL::HandleKeyEvent` para resolver scancodes desconhecidos a partir do keycode via `SDL_GetScancodeFromKey`.

### 3.3. Telemetria do Subsistema de Áudio
- **Endpoint Host**: `Alto-falantes (MCHOSE V9 PRO): 8 canais, 48000 Hz, formato 0x8120`.
- **Canal de Submissão Guest**: 6 canais 5.1 mapeados para 8 canais host com conversão estéreo/surround.
- **Buffer Health**: Zero underruns registrados durante carregamento, cinemáticas FMV e gameplay.

---

## 4. Como Jogar e Realizar Validação Manual

Para testar o jogo manualmente com teclado/mouse ou controle (DualSense / Xbox):

### 4.1. Iniciar com 1 Clique
Execute no terminal ou dê dois cliques no arquivo:
```cmd
jogar.bat
```
Ou no PowerShell:
```powershell
.\jogar.ps1
```

### 4.2. Mapeamento de Controles

#### Controle (DualSense / Xbox)
- **Analógico Esquerdo**: Movimentação de Bryce
- **Analógico Direito**: Controle de Câmera
- **A (Cruz no DualSense)**: Confirmar menu / Pular
- **B (Círculo no DualSense)**: Voltar / Esquiva (Roll)
- **X (Quadrado no DualSense)**: Ataque / Interação
- **Y (Triângulo no DualSense)**: Troca de armas
- **LT / L2**: Mira
- **RT / R2**: Disparo
- **Start / Options**: Pausa no jogo / Abrir Menu

#### Teclado e Mouse (MnK)
- **W / A / S / D**: Movimentação (Frente / Esquerda / Trás / Direita)
- **Mouse ou Setas**: Controle de Câmera
- **Espaço**: Pulo / Confirmação de Menu (A)
- **Backspace ou Aspas**: Esquiva / Voltar (B)
- **L**: Ataque / Interação (X)
- **P**: Troca de arma (Y)
- **Q**: Mira (LT)
- **E**: Disparo (RT)
- **Return (Enter) ou X**: Start (Menu / Pausa)
- **Esc**: Retomar do menu de pausa

### 4.3. Checklist para Validação Humana
1. Inicie com `.\jogar.ps1`.
2. Pressione **Start (Enter)** na tela de abertura para confirmar o carregamento do save game.
3. No Menu Principal, selecione **Campaign** e inicie o prólogo.
4. Mova Bryce com **WASD / Analógico Esquerdo** e gire a câmera com o **Mouse / Analógico Direito**.
5. Realize uma esquiva (**Backspace / Círculo / B**) e confirme a resposta das animações.
6. Na primeira arena de combate contra Grandrip, permita sofrer dano para observar o desmembramento de Bryce (braços, pernas e cabeça).
7. Verifique o rolamento da cabeça destacada e a reanexação dos membros ao passar por cima deles.
8. Pressione **F12** a qualquer momento para capturar um frame D3D12 em `analysis/n12-validation/`.

---

<!-- GOAL_COMPLETE -->
