# NeverDead PC Native Port — Next Alpha Release (Draft)

This draft covers the changes after `v0.2.1-alpha`. The version and release
date remain intentionally unset until the N15 runtime gates pass.

## Verified changes

- ROV remains the default render-target path and restores the HDR gameplay
  scene that is still dark on RTV.
- Three identical warm-cache gameplay benchmarks passed the N15 regression
  gate: 27–28 FPS 1% lows, 35.07–35.52 ms P95 frame time, and zero frames above
  50 ms.
- CPU swap, GPU execution and presentation timings are reported separately.
- Gameplay automation now uses window-targeted input, a single-instance mutex,
  below-normal runtime priority and a Windows-idle watchdog.
- The stability gate checks duration, combat, pause/resume, focus cycles,
  checkpoint writes, memory growth, XMA activity, audio underruns, fatal errors,
  D3D12 failures, DRED reports and shader-cache growth.
- Save validation reopens the exact user-data root and `ND.sav` hash produced by
  the accepted soak. Continue requires a successful save-data read followed by
  the evidence-backed gameplay pause path in the same session.
- Missing NeverDead PPC thunk boundaries found by soak testing are registered.
- Release ZIP inspection now rejects unexpected, empty and unsafe files,
  verifies Windows binary signatures, and requires ROV plus safe fetch
  constants in the packaged config.

## Known limitation

RTV gameplay still fails the automatic image-parity gate. ROV must remain the
default until fixed16 ownership/resolve testing produces a capture within the
10% luminance, 12-point channel-delta and 0.20 luminance-histogram limits.

## Required before publishing

- Pass the 15-minute confirmation and 30-minute stability soak.
- Pass save → close → reopen → continue against the same save root.
- Build a fresh Release package from the final commit.
- Run `analysis/validate_release_zip.ps1` against that package and publish its
  SHA-256 checksum.
