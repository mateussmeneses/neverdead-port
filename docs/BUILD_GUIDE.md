# NeverDead Native PC Port — Complete Build & Setup Guide

This guide details the step-by-step procedure to bootstrap the workspace, apply necessary compatibility patches to the ReXGlue SDK, execute PowerPC→C++ static codegen, and build the native Windows x64 executable of **NeverDead**.

---

## 1. Prerequisites & Environment

Ensure the following tools are installed on Windows 10/11 x64:
- **C++ Compiler**: Clang 18+ (LLVM) or MSVC 2022 (v143+ with C++20 / C++23 support)
- **Build System**: [CMake](https://cmake.org/) (version 3.28 or higher) and [Ninja](https://ninja-build.org/)
- **Scripting**: [Python](https://www.python.org/) 3.10+ and PowerShell 7+
- **Version Control**: Git for Windows
- **DirectX**: Windows 10/11 SDK (Direct3D 12 Agility SDK / Windows SDK 10.0.22621+)
- **Game Dump**: A legally acquired copy of *NeverDead* for Xbox 360, extracted to a local directory (e.g., `C:\projetos\NeverDeadxex` or `./game-dump`) containing `default.xex` and Asura `.zar` archives.

> [!IMPORTANT]
> **Legal Notice:** This repository contains open-source recompiler tools, compatibility layers, and configurations. It **does NOT** contain game binaries (`default.xex`), encryption keys, or copyrighted assets. Users must provide their own legally acquired copy of the game.

---

## 2. Workspace Setup & Reference Repositories

Clone the project repository:
```powershell
git clone https://github.com/mateussmeneses/neverdead-port.git C:\projetos\neverdead
cd C:\projetos\neverdead
```

The 13 reference repositories are tracked in [`references.csv`](references.csv). To clone the required ReXGlue SDK core toolchain:
```powershell
New-Item -ItemType Directory -Path refs\core -Force
git clone https://github.com/rexglue/rexglue-sdk.git refs\core\rexglue-sdk
git -C refs\core\rexglue-sdk checkout c94f5ebdcb3c9d1a460ca48e04f9758448f8d518
```

---

## 3. Applying the Required ReXGlue SDK Patches

*NeverDead* requires 4 targeted compatibility extensions in ReXGlue to operate stably:
1. **`XFileXctdCompressionInformation` Support**: Queries file compression headers (`0x0FF512ED`) during VFS initialization.
2. **Crash & Indirect Branch Diagnostics**: Emits guest `LR` and `SP` upon encountering invalid function traps.
3. **Lazy CSV Performance Counter Initialization**: Prevents null pointer crashes when profiling frames via `--perf_log_csv`.
4. **Performance Counter Compilation**: Enables `REXGLUE_ENABLE_PERF_COUNTERS` unconditionally across build configurations.

Apply the unified patch file located at [`analysis/patches/rexglue_sdk_neverdead.patch`](../analysis/patches/rexglue_sdk_neverdead.patch):
```powershell
git -C refs\core\rexglue-sdk apply ..\..\analysis\patches\rexglue_sdk_neverdead.patch
```

---

## 4. Building the ReXGlue SDK Toolchain

### 4.1. The Windows Git Symlink Workaround (`libmspack`)
Git on Windows checks out Unix symbolic links inside `libmspack/cabextract/mspack` as text placeholders unless Developer Mode native symlinks are enabled.
Always invoke Ninja builds of the SDK using [`analysis/Invoke-BuildWithSymlinks.ps1`](../analysis/Invoke-BuildWithSymlinks.ps1), which materializes hardlinks during compilation and cleanly restores text placeholders in a `finally` block:

```powershell
# Configure SDK with Ninja Multi-Config
cmake -B build\n2-sdk-multi -S refs\core\rexglue-sdk -G "Ninja Multi-Config" -DREXGLUE_ENABLE_PERF_COUNTERS=ON

# Compile the ReXGlue CLI tool and Catch2 unit test suite safely
powershell -ExecutionPolicy Bypass -File analysis\Invoke-BuildWithSymlinks.ps1 -Command "ninja -C build\n2-sdk-multi -f build-Release.ninja rexglue unit_tests"
```

Verify that all 214 unit tests pass:
```powershell
& refs\core\rexglue-sdk\out\win-amd64\Release\unit_tests.exe
```

---

## 5. PowerPC → C++20 Static Recompilation (Codegen)

Configure the path to your extracted NeverDead dump in [`src/neverdead_manifest.toml`](../src/neverdead_manifest.toml):
```toml
[project]
name = "neverdead"
sdk_version = "0.10.0"
game_root = "C:/projetos/NeverDeadxex"

[entrypoint]
file_path = "C:/projetos/NeverDeadxex/default.xex"
out_directory_path = "generated/default"
includes = ["neverdead_config.toml"]
```

Execute codegen with the compiled `rexglue.exe` binary:
```powershell
& refs\core\rexglue-sdk\out\win-amd64\Release\rexglue.exe codegen src\neverdead_manifest.toml
```
*Output*: Generates 24,703 C++ function implementations across 104 shards in `src/generated/default/`.

---

## 6. Building the Native Game Executable (`neverdead.exe`)

Configure and compile the native Windows x64 executable:
```powershell
cmake -B build\n2-neverdead -S src -G Ninja -DCMAKE_BUILD_TYPE=Release
powershell -ExecutionPolicy Bypass -File analysis\Invoke-BuildWithSymlinks.ps1 -Command "ninja -C build\n2-neverdead neverdead"
```

---

## 7. Configuration & Running the Port

Create or verify `build/n2-neverdead/neverdead.toml`:
```toml
log_level = "info"
gpu_allow_invalid_fetch_constants = false
mnk_mode = true
```

> [!NOTE]
> As of Milestone N11, `gpu_allow_invalid_fetch_constants = true` is no longer required. The ReXGlue Xenos pipeline has been enhanced with `texture_util::IsValidHdrRenderTargetDescriptor`, which specifically identifies and validates the Asura Engine's 1120x640 HDR floating-point render targets (`k_16_16_16_16_FLOAT` and `k_16_16_FLOAT`) without leaving the texture cache vulnerable to arbitrary uninitialized registers.

Launch the port:
```powershell
cd build\n2-neverdead
.\neverdead.exe --game_data_root="C:\projetos\NeverDeadxex"
```

---

## 8. Quality Assurance & Regression Verification

Run the automated QA test suite:

- **Offline Telemetry & Regression Verification** (Validates benchmark baselines and repository hygiene without requiring game dump):
  ```powershell
  python analysis\qa_smoke_test.py --verify-recent
  ```

- **Live Execution Test** (Runs game for N seconds, verifies zero fatal traps, zero D3D12 errors, and memory ceilings):
  ```powershell
  python analysis\qa_smoke_test.py --run-live --seconds 15
  ```
