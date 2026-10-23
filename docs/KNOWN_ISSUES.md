# NeverDead Native PC Port — Known Issues & Troubleshooting

This document tracks known issues, their root causes, and verified workarounds for the *NeverDead* native PC static recompilation port.

---

## 1. Resolved Issues & Verified Fixes

### 1.1. Black 3D Scene / HDR Render Target Fetch Descriptors
- **Issue:** The screen remained mostly black when entering 3D cutscenes and gameplay, despite audio and in-game pause menus being active.
- **Root Cause:** The Asura Engine configures its primary 1120x640 HDR float scene render target (`k_16_16_16_16_FLOAT`, format `0x20`) using descriptor `(88C04954 1F318060 004FE45F 00A80D11 00000003 00000200)` with fetch type 0 (`kInvalidTexture`). With the default conservative safety check, the texture cache refused to bind the descriptor.
- **Fix / Workaround:** Enable `gpu_allow_invalid_fetch_constants = true` in `build/n2-neverdead/neverdead.toml`, or supply `--gpu_allow_invalid_fetch_constants=true` on the command line. This allows the Direct3D 12 texture cache to bind the underlying HDR surface properly.

### 1.2. Fatal Guest Trap at `0x825E04F0` (C++ Virtual Dispatch)
- **Issue:** Early development builds aborted with a fatal guest trap at `0x825E04F0` (`LR=0x826389D8`, `SP=0x7018F790`).
- **Root Cause:** NeverDead’s engine utilizes 24-byte (0x18-byte) virtual method dispatch thunks. Automated PPC basic block analysis did not detect them as entry points due to indirect branching through guest vtables.
- **Fix / Workaround:** Registered 11 verified function boundary ranges in `src/neverdead_config.toml` (`0x825E0478` through `0x825E0564` and `0x825E05E0`). This instructs the recompiler to emit full C++ function bodies with correct prologues and epilogues.

### 1.3. `libmspack` Symlink Placeholders on Windows Git
- **Issue:** Re-running CMake or Ninja after cloning can cause compilation errors: `fatal error C1189: #error: placeholder for ...`.
- **Root Cause:** Windows Git clones Unix symbolic links as 30-byte text files pointing to relative paths (`../../libmspack/mspack/lzxd.c`) unless developer mode / native symlinks are enabled with administrative privileges.
- **Fix / Workaround:** Build using [`analysis/Invoke-BuildWithSymlinks.ps1`](file:///C:/projetos/neverdead/analysis/Invoke-BuildWithSymlinks.ps1). The script safely hardlinks the source files into `cabextract/mspack` before invoking Ninja, and cleanly restores the original text placeholders in a `finally` block upon completion.

---

## 2. Active Technical Issues & Workarounds

### 2.1. High CPU Utilization in Complex 3D Sequences
- **Issue:** In scenes with large numbers of recompiled basic blocks and dynamic entities, CPU core utilization rises to ~150–200% host equivalent, leading to framerate dips on older quad-core processors.
- **Root Cause:** Function calls between recompiled PPC blocks currently execute through indirect dispatch handlers rather than direct tail-call inlining.
- **Workaround:** Close background CPU-heavy applications. Future releases (see `PORT_ROADMAP.md`) will incorporate basic block dispatch inlining and AVX2 vector optimizations.

### 2.2. XMA Unknown Register `0x0601` Debug Spam
- **Issue:** When running with `--log_level=debug`, the log receives frequent entries: `[debug] [apu] [t27384] XMA: Write to unknown register (0601): 00000003`.
- **Root Cause:** Asura’s audio driver performs lock/unlock synchronization writes to hardware register `0x0601` during audio packet queuing. ReXGlue logs this write because Xenos APU register `0x0601` is not part of the standard XMA ring buffer documentation.
- **Workaround:** This message is harmless and does not affect audio output or stability. Set `--log_level=info` or `log_level = "info"` in `neverdead.toml` to suppress debug traces.

### 2.3. Window Focus and Controller Inputs
- **Issue:** When clicking outside the NeverDead window or Alt-Tabbing, controller inputs may stop registering until the window is re-focused.
- **Root Cause:** Default SDL3 input event processing filters focus loss events to prevent background inputs.
- **Workaround:** Keep the NeverDead game window focused. A borderless fullscreen option is planned for roadmap milestone P2.
