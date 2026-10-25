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
| **N6** | Input, Audio & Gameplay Systems | ✅ Completed | In-game scene reached; DualSense/MNK functional; 48 kHz XMA audio; HDR textures resolved. |
| **N7** | Profiling, Memory & Stutter Mitigation | ✅ Completed | 60s Cold/Warm benchmarks; 550 MB RSS / 1.35 GB Commit; 0 crashes, 100% warm shader cache hit. |
| **N8** | QA Regression Suite & CI Delivery | ✅ Completed | Automated regression test suite (`qa_smoke_test.py`), GitHub Actions CI, complete documentation. |
| **N9** | Build Reproducibility & QA v2.0 | ✅ Completed | 4-state diagnostic QA model (PASS/FAIL/SKIP/INCONCLUSIVE), unified SDK patches, build guide. |
| **N10** | Real Gameplay Validation (D3D12) | ✅ Completed | Boot-to-gameplay validated in D3D12; 8 stages captured via direct GPU readback; character movement & camera verified; zero guest traps. |
| **N11** | Xenos/D3D12 Graphics Correctness | ✅ Completed | Targeted Asura HDR descriptor filter; safe default `gpu_allow_invalid_fetch_constants=false`; verified render targets, depth, blending & MSAA; zero D3D12 errors. |
| **N12** | Gameplay, Physics & Save Persistence | ✅ Completed | STFS/XContent save persistence verified (`ND.sav` 3.14 MB); Havok 3D collision & animations; DualSense & Xbox controllers; focus switching (`--input_background=true`); 0 audio underruns. |
| **N13** | Real Gameplay Performance & Optimization | ✅ Completed | Automated 3D gameplay benchmark; lock-free flat PPC function table; -22.1% max frametime spike (83.5ms → 65.1ms); -71.4% stutters >50ms (7 → 2); 0.1% min FPS +36.4% (11 → 15 FPS); 24/24 QA pass. |
| **N14** | Gameplay Lighting & Release Hardening | ✅ Completed | D3D12 ROV path restores the HDR scene; real gameplay, movement and camera captures verified; launchers and validation harnesses default to the safe path. |

---

## Documentation

- [Complete Build & Setup Guide](docs/BUILD_GUIDE.md)
- [Project Status & Compatibility Matrix](docs/STATUS.md)
- [Known Issues & Workarounds](docs/KNOWN_ISSUES.md)
- [Development Roadmap](docs/PORT_ROADMAP.md)
- [N7 Profiling & Benchmark Report](analysis/N7-status.md)
- [N8 QA Stability & Regression Report](analysis/N8-qa-report.md)
- [N9 Build Reproducibility & QA Consolidation](analysis/N9-status.md)
- [N10 Real Gameplay Validation & D3D12 Report](analysis/N10-status.md)
- [N11 Graphics Correctness & D3D12 Report](analysis/N11-status.md)
- [N12 Gameplay, Physics & Save Persistence Report](analysis/N12-status.md)
- [N13 Real Gameplay Performance Report](analysis/N13-status.md)
- [N14 Gameplay Lighting & Release Hardening](analysis/N14-status.md)

---

## Technical Highlights & Fixes

1. **Virtual Dispatch Adjustor Thunk Discovery**:
   - Resolved guest traps during virtual method dispatches by registering verified 0x18-byte PPC wrapper thunks (`0x825E0478` through `0x825E0564`, `0x825E05E0`, etc.) in `src/neverdead_config.toml`.
2. **HDR Scene Buffer & Targeted Descriptor Filter**:
   - NeverDead's Asura Engine binds its primary 1120x640 HDR floating-point scene render targets (`k_16_16_16_16_FLOAT`, format 0x20 and `k_16_16_FLOAT`, format 0x1F) with fetch constant type 0 (`kInvalidTexture`).
   - Replaced global invalid descriptor acceptance (`gpu_allow_invalid_fetch_constants = true`) with a targeted filter (`texture_util::IsValidHdrRenderTargetDescriptor`) in `rexgpu-xenos`. This ensures safe execution with `gpu_allow_invalid_fetch_constants = false` while binding valid HDR surfaces and protecting the cache from garbage memory.
   - Uses the D3D12 ROV render-target path because the faster RTV EDRAM resolve drops NeverDead's HDR scene contribution and leaves only HUD elements visible.
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
