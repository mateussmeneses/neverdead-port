# NeverDead Native PC Port — Known Issues & Troubleshooting

This document tracks known issues, their root causes, and verified workarounds for the *NeverDead* native PC static recompilation port.

---

## 1. Resolved Issues & Verified Fixes

### 1.1. Black 3D Scene / HDR Render Target Fetch Descriptors (Resolved in N11)
- **Issue:** The screen remained mostly black when entering 3D cutscenes and gameplay, despite audio and in-game pause menus being active.
- **Root Cause:** The Asura Engine configures its primary 1120x640 HDR float scene render target (`k_16_16_16_16_FLOAT`, format `0x20`) using descriptor `(88C04954 1F318060 004FE45F 00A80D11 00000003 00000200)` and secondary HDR buffer (`k_16_16_FLOAT`, format `0x1F`) with fetch type 0 (`kInvalidTexture`). With the default emulator policy, the texture cache refused to bind these descriptors because `SQ_TEX_VALID_TEXTURE` bit was clear.
- **Interim Workaround (N6–N10):** Enabled global `gpu_allow_invalid_fetch_constants = true`. However, this posed cache security risks by also accepting genuine uninitialized garbage descriptors.
- **Permanent Fix (N11):** Implemented targeted descriptor validation via `texture_util::IsValidHdrRenderTargetDescriptor` in `refs/core/rexglue-sdk/include/rex/graphics/pipeline/texture/util.h` and `cache.cpp`. The texture cache now validates specific Asura HDR floating-point parameters (tiled, formats `0x20` / `0x1F`, base page non-zero, within 8192 dimension bounds) and binds them safely even with `gpu_allow_invalid_fetch_constants = false`, while continuing to reject uninitialized and out-of-bounds registers. Verified by automated Catch2 tests (219/219) and live D3D12 gameplay frame captures.

### 1.2. Fatal Guest Trap at `0x825E04F0` (C++ Virtual Dispatch)
- **Issue:** Early development builds aborted with a fatal guest trap at `0x825E04F0` (`LR=0x826389D8`, `SP=0x7018F790`).
- **Root Cause:** NeverDead’s engine utilizes 24-byte (0x18-byte) virtual method dispatch thunks. Automated PPC basic block analysis did not detect them as entry points due to indirect branching through guest vtables.
- **Fix / Workaround:** Registered 11 verified function boundary ranges in `src/neverdead_config.toml` (`0x825E0478` through `0x825E0564` and `0x825E05E0`). This instructs the recompiler to emit full C++ function bodies with correct prologues and epilogues.

### 1.3. `libmspack` Symlink Placeholders on Windows Git
- **Issue:** Re-running CMake or Ninja after cloning can cause compilation errors: `fatal error C1189: #error: placeholder for ...`.
- **Root Cause:** Windows Git clones Unix symbolic links as 30-byte text files pointing to relative paths (`../../libmspack/mspack/lzxd.c`) unless developer mode / native symlinks are enabled with administrative privileges.
- **Fix / Workaround:** Build using [`analysis/Invoke-BuildWithSymlinks.ps1`](file:///C:/projetos/neverdead/analysis/Invoke-BuildWithSymlinks.ps1). The script safely hardlinks the source files into `cabextract/mspack` before invoking Ninja, and cleanly restores the original text placeholders in a `finally` block upon completion.

### 1.4. Window Focus Loss and Background Input Handling (Resolved in N12)
- **Issue:** When the game window lost focus (e.g. during desktop switching, background automation, or dual-monitor traversal), controller and keyboard inputs were zeroed out, preventing seamless input delivery.
- **Root Cause:** `MnkInputDriver` and `SDLInputDriver` unconditionally zeroed device state upon focus loss (`has_focus_ = false`), and `WindowedAppContextSDL` dropped key events when `windowID == 0`.
- **Permanent Fix (N12):** Added the `--input_background` configuration CVar in `rex::input`. When enabled, keyboard and gamepad inputs continue processing across focus shifts. Furthermore, `WindowedAppContextSDL` now provides single-window fallback routing for message dispatch, and `WindowSDL` falls back to translating keys via `SDL_GetScancodeFromKey`.

### 1.5. Function Dispatch Mutex Contention & Frametime Spikes (Resolved in N13)
- **Issue:** During intense 3D scenes with multi-threaded Asura task workers (up to 34 concurrent threads), maximum frametime spikes reached 83.5 ms and heavy stutters (>50 ms) occurred periodically.
- **Root Cause:** `FunctionDispatcher::GetFunction` held a `std::recursive_mutex` (`dispatch_mutex_`) and performed a hash table lookup in `std::unordered_map` on every indirect function resolution and dispatch call. With over 18,000 dispatches per 30 seconds across 30+ threads, mutex contention triggered Windows kernel context switches.
- **Permanent Fix (N13):** Implemented a lock-free flat module dispatch table fast-path in `FunctionDispatcher` utilizing the direct memory table allocated at `image_base + image_size`. Guest addresses within the primary module are indexed in O(1) time without acquiring any lock. This reduced max frametime spikes by 22.1% (83.5 ms → 65.1 ms), reduced heavy stutters by 71.4% (7 → 2), and increased minimum frame rate floor by +36.4% (11.0 → 15.0 FPS).

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
