# NeverDead PC Native Port v0.2.0-alpha (Milestones N0–N8 Complete)

Native PC port of **NeverDead** (Xbox 360, Asura Engine) via static recompilation (PowerPC Xenon → C++20 / x86-64, Xenos GPU → Direct3D 12).

---

### What's New in v0.2.0-alpha

1. **Milestone N7 — Profiling, Frame Pacing & Stutter Mitigation:**
   - 60s Cold Cache vs 60s Warm Cache empirical profiling via `analysis/profile_n7.py`.
   - **Zero memory leaks**: Stable ~550–560 MB RSS RAM and ~1.35 GB Commit Charge.
   - **Zero shader compilation stutter**: 100% shader cache hit rate on warm runs (`4B4E081F.xsh` / `.xpso`).
   - Detailed status and optimization roadmap documented in [`analysis/N7-status.md`](docs/STATUS.md).

2. **Milestone N8 — QA Stability Suite & CI Delivery:**
   - Automated regression test suite [`analysis/qa_smoke_test.py`](analysis/qa_smoke_test.py) checking golden acceptance thresholds.
   - Complete bug taxonomy & stability battery report in [`analysis/N8-qa-report.md`](analysis/N8-qa-report.md).
   - GitHub Actions CI workflow (`.github/workflows/build.yml`) for automated Windows x64 build verification and repository asset sanitization.
   - Comprehensive documentation added:
     - [`docs/STATUS.md`](docs/STATUS.md): Compatibility and feature status breakdown.
     - [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md): Root-cause analyses and workarounds.
     - [`docs/PORT_ROADMAP.md`](docs/PORT_ROADMAP.md): 60 FPS, ultrawide resolutions, modern controls, and modding plans.

3. **Core Gameplay & Engine Invariants:**
   - DualSense / Xbox / Keyboard input handling through SDL3.
   - 48 kHz 8-channel XMA audio decoding and real-time playback.
   - 1120x640 HDR float scene render targets bound seamlessly under Direct3D 12 (`gpu_allow_invalid_fetch_constants = true`).
   - 24,703 PowerPC functions compiled cleanly across 104 shards with 0 fatal guest traps.

---

> [!IMPORTANT]
> **Legal Notice:** This repository contains open-source recompiler tools, compatibility layers, and configurations. It **does NOT** contain game binaries (`default.xex`), encryption keys, or copyrighted assets. Users must provide their own legally acquired copy of the game.
