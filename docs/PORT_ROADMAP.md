# NeverDead Native PC Port — Development Roadmap

This roadmap outlines upcoming milestones, performance enhancements, and quality-of-life features planned for future releases of the *NeverDead* native PC port.

## Immediate priority: launcher and ROV alpha release

This delivery track takes priority over the future phases below. N15 remains
in progress: shipping an alpha with ROV does not mean RTV parity is complete.

1. **Small Windows launcher**: select and remember the extracted game folder,
   validate required files before launch, start with ROV and safe fetch-constant
   validation, and provide buttons to open saves and logs. Use stable writable
   user-data paths across upgrades. Never overwrite existing saves. Report
   missing files and launch failures with actionable messages.
2. **Runtime acceptance**: complete the pause/resume confirmation and a minimum
   30-minute gameplay soak covering movement, camera, combat, focus changes,
   multiple checkpoints, memory/cache growth, audio and DRED. Reopen the exact
   saved state and prove Continue reaches gameplay. Short benchmark results
   alone do not satisfy this gate.
3. **Release package**: include the launcher, port binaries, configuration and
   instructions; exclude commercial game files, saves, caches and local logs.
   Update the archive allowlist for the launcher, validate the final ZIP and
   publish its SHA-256 checksum. Test folder paths containing spaces.
4. **GitHub prerelease**: publish only after the runtime and package gates pass,
   with installation instructions and explicit RTV and other known limitations.

Implementation scope excludes an updater, account system, mod manager and new
graphics settings. ROV stays the release default. RTV work continues separately
until automatic visual comparison passes.

Current evidence and remaining gates: [N15 status](../analysis/N15-status.md)
and [release draft](../analysis/release-next-notes.md).

---

## Phase 1: Core Performance & Xenon Vectorization (v0.2.x)

- [ ] **Basic Block Dispatch Inlining:**
  - Transition recompiled Xenon basic block execution from indirect dispatcher thunks to direct relative jumps and tail-call inlining.
  - Estimated gain: 15–25% reduction in CPU overhead across complex combat encounters.
- [ ] **AVX2 / SSE4.1 Vector Intrinsics for VMX128:**
  - Map Xenon PowerPC AltiVec / VMX128 vector instructions (`vaddfp`, `vmr`, `vsplat`, `vmulx`, dot products) directly to x86 AVX2 intrinsics.
  - Accelerates real-time vertex skinning, ragdoll deformation, and Bryce’s dismemberment physics.
- [ ] **Direct Texture Descriptor Binding:**
  - Cache and pre-classify Asura HDR float render targets to bypass runtime constant checking.

---

## Phase 2: High Refresh Rates, Modern Resolutions & Display Settings (v0.3.x)

- [ ] **60 FPS / Unlocked Frametime Support:**
  - Decouple Asura Engine physics integration timestep (`dt`) from the original 30 FPS console render loop.
  - Add interpolation for character animations, camera rotation, and particle emitters.
- [ ] **Ultrawide & Arbitrary Resolutions:**
  - Implement dynamic aspect ratio scaling (16:10, 21:9, 32:9) for the camera projection matrix.
  - Anchor UI elements (health, ammunition, weapon selector, and dialogue subtitles) to safe display zones.
- [ ] **Native Resolution Scaling (1440p / 4K):**
  - Allow rendering 3D scene buffers at native PC display resolutions rather than the original 1120x640 Xbox 360 framebuffer.
- [ ] **Windowing Options:**
  - Add borderless windowed mode, exclusive fullscreen toggle, and VSync options in `neverdead.toml`.

---

## Phase 3: Input, Audio & Quality of Life (v0.4.x)

- [ ] **Native PC Mouse & Keyboard Control:**
  - Full mouse camera aiming with configurable sensitivity, raw input, and zero smoothing/acceleration.
  - In-game customizable keyboard keybindings for rolling, jumping, shooting, and limb detachment.
- [ ] **Haptic Feedback & Controller Rumble:**
  - Translate Xbox 360 `XInputSetState` motor frequency packets into modern SDL3 haptic rumble curves (DualSense, Xbox Series X|S, DualShock 4).
- [ ] **Surround Sound & Audio Panning:**
  - Full 5.1 and 7.1 surround sound positioning with host HRTF spatial audio.

---

## Phase 4: Modding & Asset Replacement (v1.0.0+)

- [ ] **Loose File VFS Injection:**
  - Support loading uncompressed modded files from a `mods/` directory, overriding files packaged inside `.zar` archives.
- [ ] **HD Texture Replacement:**
  - Direct3D 12 texture replacement via texture hash interception, allowing community 4K texture packs and remastered UI art.
- [ ] **Custom Game Rules & Gameplay Mods:**
  - Hooks to modify dismemberment thresholds, enemy spawning counts, and weapon balance parameters.
