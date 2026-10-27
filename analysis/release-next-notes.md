# NeverDead PC Native Port — Next Alpha Release (Draft)

This draft covers the 31 commits after `v0.2.1-alpha`. The version and release
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
  D3D12 failures and DRED reports.
- Save validation can close, reopen and continue from the same persistent user
  data root.
- Missing NeverDead PPC thunk boundaries found by soak testing are registered.
- Release ZIP inspection now rejects unexpected files and unsafe paths and
  verifies that the packaged config retains ROV and safe fetch constants.

## Known limitation

RTV gameplay still fails the automatic image-parity gate. ROV must remain the
default until fixed16 ownership/resolve testing produces a capture within the
10% luminance and 12-point channel-delta limits.

## Required before publishing

- Pass the 15-minute confirmation and 30-minute stability soak.
- Pass save → close → reopen → continue against the same save root.
- Build a fresh Release package from the final commit.
- Run `analysis/validate_release_zip.ps1` against that package and publish its
  SHA-256 checksum.
