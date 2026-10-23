# NeverDead — Native PC Port (Xbox 360 Static Recompilation)

A native Windows x64 port of **NeverDead** (Xbox 360, Asura Engine) via static recompilation:
- **CPU**: PowerPC (Xenon 3 cores / 6 threads) recompiled to native C++20 / x86-64.
- **GPU**: Xenos command processor translated to Direct3D 12 and Vulkan.
- **OS / Runtime**: High-Level Emulation (HLE) of Xbox 360 kernel (`xboxkrnl`), XAM, XMA audio decoding, and SDL3 input/presentation.

> [!NOTE]
> This repository contains open-source porting tools, engine compatibility layers, and configurations. It **does NOT** contain game binaries (`default.xex`), encrypted keys, or copyrighted assets. Users must provide their own legally acquired copy of the game.

---

## Current Status & Milestones

| Milestone | Scope | Status | Notes |
|---|---|---|---|
| **N0** | Workspace Audit & Reference Inventory | ✅ Completed | 13 reference repositories inventoried and verified. |
| **N1** | XEX Parsing & Architecture Mapping | ✅ Completed | Title ID `0x4B4E081F`, entry `0x826D1288`, 15 sections, 269 imports mapped. |
| **N2** | PowerPC → C++ Recompilation & Shard Build | ✅ Completed | 24,703 functions mapped, 104 shards generated and compiled. |
| **N3** | Kernel / XAM HLE & Initial Boot | ✅ Completed | Memory arena, TLS, threads, events, VFS, and file queries operational. |
| **N4** | Asura Engine Asset & File Layout | ✅ Completed | Big-endian containers and VFS bindings verified against game dump. |
| **N5** | Xenos → D3D12 Renderer & First Frames | ✅ Completed | D3D12 pipeline active; title screen and in-game presentation verified. |
| **N6** | Input, Audio & Gameplay In-Flight | 🟡 Advanced | In-game scene reached; DualSense/MNK input functional; audio operational; invalid texture constants resolved. |
| **N7** | Profiling, Frame Pacing & Optimization | ⏳ Planned | Tracy integration, latency profiling, and micro-stutter reduction. |
| **N8** | Campaign QA Suite & Release Delivery | ⏳ Planned | Automated milestones tests and smoke tests. |

---

## Technical Highlights & Fixes

1. **Virtual Dispatch Adjustor Thunk Discovery**:
   - Resolved guest traps during virtual method dispatches by registering verified 0x18-byte PPC wrapper thunks (`0x825E0478` through `0x825E0564`, `0x825E05E0`, etc.) in `src/neverdead_config.toml`.
2. **HDR Scene Buffer & Texture Cache Binding**:
   - NeverDead binds its primary 1120x640 HDR floating-point scene render target (`k_16_16_16_16_FLOAT`, format 0x20) with fetch constant type 0 (`kInvalidTexture`).
   - Enabled `gpu_allow_invalid_fetch_constants = true` to prevent the texture cache from dropping valid render surfaces, resolving the black scene rendering in gameplay.
3. **Audio Subsystem**:
   - SDL audio driver handles host output (48 kHz); XMA decoder handles guest audio packet processing.

---

## Prerequisites

- **OS**: Windows 10/11 x64
- **Toolchain**: LLVM/Clang (or MSVC with C++20 support), CMake 3.28+, Ninja
- **GPU**: Direct3D 12 Feature Level 11_0+ (NVIDIA, AMD, or Intel)
- **Game Dump**: Extracted Xbox 360 copy of NeverDead containing `default.xex`

---

## Building from Source

1. Clone this repository:
   ```powershell
   git clone https://github.com/mateussmeneses/neverdead-port.git
   cd neverdead-port
   ```

2. Generate recompiled C++ sources using ReXGlue CLI:
   ```powershell
   & refs/core/rexglue-sdk/out/win-amd64/rexglue.exe codegen src/neverdead_manifest.toml
   ```

3. Configure and build the runtime:
   ```powershell
   cmake -B build/neverdead -S src -G Ninja -DCMAKE_BUILD_TYPE=Release
   cmake --build build/neverdead --target neverdead -j 4
   ```

4. Run NeverDead:
   ```powershell
   build/neverdead/neverdead.exe --game_data_root="<path-to-game-dump>"
   ```

---

## Legal & Attribution

- NeverDead is a trademark of Konami Digital Entertainment / Rebellion Developments.
- This project is a clean-room static recompilation port for preservation and research.
- Built with [ReXGlue SDK](https://github.com/rexglue/rexglue-sdk), [Xenia](https://github.com/xenia-project/xenia), and [360tools](https://github.com/sp00nznet/360tools).
