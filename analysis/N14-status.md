# NeverDead N14: Gameplay Lighting & Release Hardening

**Status:** verified on 24 October 2026  
**Test GPU:** NVIDIA GeForce RTX 5060 Laptop GPU  
**Renderer:** Direct3D 12, ROV render-target path

## Result

The dark-gameplay defect is resolved by forcing `render_target_path_d3d12 = "rov"`. The default NVIDIA RTV path presents menus and HUD correctly but loses the HDR 3D scene during EDRAM resolve. Enabling `gpu_allow_invalid_fetch_constants` does not repair that output, so the safe descriptor policy remains enabled with `gpu_allow_invalid_fetch_constants = false`.

The setting is now copied into every build through `src/neverdead.toml` and is also explicit in both launchers and all active validation/profiling commands.

## Reproducible evidence

- `analysis/validate_graphics_n11.ps1` performs a cold-profile boot, completes gamma/autosave/menu setup, skips the prologue, resumes gameplay, and captures movement, camera and action frames.
- The verified run `20261024-222243` captured four gameplay frames with 81.2–95.1% non-black samples and average luminance from 22.9 to 44.0.
- Visual inspection confirms Bryce, the environment, lighting, shadows, tutorial HUD, movement and camera changes.
- Runtime audit: 0 guest traps, 0 D3D12 errors, 0 DRED faults and 0 unexpected invalid-texture warnings.
- A corrected 30-second cold-cache gameplay profile captured 3,953 frames at 30 FPS median and 27 FPS 1% low, with four frametimes above 50 ms, no command-buffer stalls and no graphics errors.
- The equivalent warm run remained at 30 FPS median but recorded a 20 FPS 1% low and eleven frametimes above 50 ms. Shader/pipeline caches were already effectively saturated, so the remaining variance is not a cache-miss problem and no speculative optimization was applied.

## Release policy

ROV is the correctness default for v0.2.x. RTV remains an experimental optimization target and must not become the default until an automated gameplay capture produces the same lit HDR scene.
