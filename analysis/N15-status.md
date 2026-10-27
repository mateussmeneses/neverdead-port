# N15 — ROV Performance, RTV Parity and Long-Run Stability

**Status:** IN PROGRESS  
**Updated:** 2026-10-26

## 1. ROV gameplay regression gate

Three identical 30-second warm-cache gameplay runs passed the gameplay and
performance gates. Measurements are sliced from the CSV at the exact start and
end of interactive gameplay, excluding boot, menus and cinematics.

| Run | Frames | 1% low | P95 frame | Max frame | >50 ms | GPU P95 | Swap CPU P95 | Present P95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 922 | 28 FPS | 35.07 ms | 36.98 ms | 0 | 13.29 ms | 0.37 ms | 0.16 ms |
| 2 | 923 | 27 FPS | 35.52 ms | 37.08 ms | 0 | 15.11 ms | 0.42 ms | 0.17 ms |
| 3 | 924 | 27 FPS | 35.21 ms | 36.82 ms | 0 | 14.94 ms | 0.39 ms | 0.16 ms |

The previous warm result of 20 FPS at the 1% low and 11 frames above 50 ms was
not reproduced after restricting analysis to gameplay frames. The current gate
requires proven 3D gameplay, at least 26 FPS at the 1% low and no more than one
frame above 50 ms. Aggregate evidence is in
[`n15_warm_rov_repeats.json`](n13-benchmarks/n15_warm_rov_repeats.json).

## 2. RTV lighting parity

RTV is still blocked by the automatic image gate. The brightest captured RTV
sample has average luminance 11.41 and a 43.1% non-black ratio, versus 55.79 and
94.4% for the selected ROV reference. The comparison reports a 79.54% luminance
delta and a maximum average channel delta of 58.65, well outside the 10% and
12-point limits. The structured result is in
[`n15_rtv_visual_gate.json`](n13-benchmarks/n15_rtv_visual_gate.json).

The affected Asura chain samples 1120x640 `k_16_16_16_16_FLOAT` and
`k_16_16_FLOAT` scene surfaces, but the RTV log also creates the main EDRAM
targets repeatedly as guest format 5 (`k_16_16_16_16`, fixed16). Disabling gamma
aliasing did not restore the image. The profiler can now isolate
`snorm16_render_target_full_range=false` in the next RTV capture.

The full-range trace captured 92,621 resolves. Of those, 16,304 convert fixed16
`k_16_16_16_16` into `k_16_16_16_16_FLOAT`, including 5,784 resolves of the
main 1120x640 surface. No resolve has `k_8_8_8_8_GAMMA` as its source. The
capture is nearly black (average luminance 0.41, 99.26% below ROV), so the
remaining A/B is now narrowly scoped to the fixed16 32x range remap. Structured
counts are in
[`n15_rtv_resolve_trace.json`](n13-benchmarks/n15_rtv_resolve_trace.json).

Comparison against Xenia revisions `95a5c3e` (2026-02-18) and `291f0c9`
(2026-10-25) found the same integer ownership-transfer formats for FLOAT16
targets. Xenia's ownership-transfer RT cache originated in `913e1e9`
(2021-04-26), but the upstream NeverDead reports still describe RTV as dark and
ROV as the working path:

- [Xenia compatibility issue 1097](https://github.com/xenia-project/game-compatibility/issues/1097)
- [Xenia Canary compatibility issue 486](https://github.com/xenia-canary/game-compatibility/issues/486)

ROV therefore remains the default. RTV must not be enabled until the image gate
passes; a brightness multiplier would hide the EDRAM ownership/resolve defect
rather than fix it.

`direct_host_resolve` is not a useful isolation switch in this ReXGlue revision:
`TryResolveCopyDirectly` still ends by calling `DumpRenderTargets`, which is the
same fallback used when the option is disabled. Testing both values would
therefore execute the same resolve path.

The upstream comparison identified Xenia commit
`067641668f1fba4ef89bf1796a555f74b0cc3469`, which fixes MIN/MAX blending with
source factors on host render targets. However, parsing NeverDead's 136 cached
RTV pipeline descriptions found 281 bound render targets and every color and
alpha blend operation is ADD. None uses MIN/MAX, so the provisional port was
removed without spending a build/test cycle on an unreachable path. The parsed
counts are recorded in
[`n15_rtv_pipeline_usage.json`](n13-benchmarks/n15_rtv_pipeline_usage.json).

Commit `2912da02f` repairs cross-format transfer to gamma targets backed by
`R16G16B16A16_UNORM`; disabling that backing did not fix NeverDead, so it is not
the primary suspect. Commit `4cc584f47` maps constant-alpha blending to D3D12
Options13 and provides a legacy fallback, but the same cache inspection found
no constant blend-factor use, so it is also outside the failing workload.

The pipeline cache does expose a more direct fixed16 hazard. Of 100 bound
`k_16_16_16_16` targets, 30 use alpha-dependent blend factors: 28 color-source
factors are `SRC_ALPHA`, and 15 color-destination factors are `INV_SRC_ALPHA`.
The RTV full-range workaround divides all fixed16 shader outputs, including
alpha, by 32 before D3D12 fixed-function blending. Therefore those passes can
receive roughly 1/32 of the intended source contribution. This is an
evidence-backed explanation for the dark RTV output, but the limited-range A/B
must confirm it before changing storage or blend semantics.

The affected combinations are not one isolated state: 14 are conventional
`SRC_ALPHA/INV_SRC_ALPHA` blends and 14 are additive `SRC_ALPHA/ONE` blends.
Xenia [documents full-range RTV](https://github.com/xenia-canary/xenia-canary/wiki/Options)
as trading away blending correctness, and its current implementation has no
compensation to port. If the limited-range A/B
restores lighting, limited range still must not become the final path because
it clips the fixed16 HDR channels to -1..1. The corrective branch should keep
RGB full-range while preserving semantic alpha for fixed-function blending and
adjusting alpha ownership transfer/resolve consistently.

`run_n15_rtv_fixed16_ab.ps1` now makes that isolation reproducible. It runs the
full-range and limited-range variants against the same ROV reference, requires
15 minutes of Windows input idle before each run, rejects stale profiles and
writes `n15_rtv_fixed16_ab.json`. It is prepared but intentionally not armed
while the laptop is in active use.

Canary commit `534aeb6` (2026-10-23) quantizes PWL gamma after MSAA averaging.
NeverDead does create format 1 (`k_8_8_8_8_GAMMA`) pipelines, so the change is
relevant to general gamma fidelity. It is not a candidate for the path-specific
darkness, however: RTV dumps its host targets to the EDRAM buffer and then uses
the same resolve shader as ROV. A shared post-dump quantization change cannot
explain why the ROV reference is lit while the RTV capture is dark.

Fixed16 is tested separately. Xenia commit `42c2b880e` replaces the old
`32/32767` approximation with the hardware's ten fractional bits (`1/1024`) in
command constants, packing and unpacking. ReXGlue still has the old scale, but
the numerical difference is only about 0.003%, far too small to explain the
79.54% luminance loss. More importantly, the ReXGlue resolve shader disassembly
already packs fixed16 resolve destinations as UNORM with a 65535 multiplier,
so it does not contain the roughly 64x crushing bug corrected by `16d2cc05c`.
The full-range toggle remains useful only to isolate which ownership-transfer
branch is faulty; neither upstream change should be ported speculatively.

## 3. Long-run stability

The first soak exposed missing PPC thunk boundaries during repeated pause/resume
paths. The evidence-backed functions are now registered in
`src/neverdead_config.toml`, including the eight-instruction tail thunk at
`0x8253B640`.

The first laptop-safe attempt reached gameplay and wrote 9,188 frame samples,
then the user-activity watchdog stopped it before the first five-minute pause;
the runtime log contains no crash, missing-function or DRED signature. The
controller now treats this as a recoverable interruption: it terminates the
game, waits for another 15-minute Windows idle period and repeats the same run
without manual re-arming. The watchdog is armed after runtime window creation,
so synthetic startup input is ignored, and later input resets are ignored only
while the runtime itself owns the foreground; activity in another application
still terminates the game. Sixteen unit tests cover the profiler and controller.
Input is sent only to the game window, the game runs below normal priority, and a named
mutex prevents concurrent profilers. Unattended runs now require a 15-minute
idle window; the queue is intentionally stopped while the laptop is in active
use. A successful 15-minute confirmation will be followed by the full 30-minute
soak and the save → close → reopen → continue cycle. The stability gate now
requires the requested duration, combat, scheduled pause/resume and focus
cycles, active XMA decoding, zero audio underruns, and zero fatal, D3D12 or DRED
faults. Memory evidence includes peak, start/end growth and linear RSS/commit
slopes in MB/min. The 30-minute run additionally requires at least two
`.sav`/`.header` write events after gameplay starts, providing direct evidence
of multiple checkpoint saves. Completion requires both the minimum frame count
and the full requested monotonic wall-clock duration, with accumulated frame
times covering at least 95% of that window. This prevents an early exit at high
FPS or a frozen tail from passing the soak gate.

The older N12 report proves that an existing `ND.sav` is enumerated and remains
byte-identical after relaunch, but it does not close the N15 save gate: its
captured route enters the difficulty screen, the save hash is unchanged during
the run, and there is no evidence that a `Continue` entry loaded a recorded
checkpoint. The N15 reopen cycle must therefore reuse the exact user-data root
from a soak that records checkpoint writes and verify resumed gameplay from
that state.

## 4. Remaining acceptance checks

- [x] Three repeatable ROV gameplay benchmarks.
- [x] CPU/GPU/swap/presentation timings separated.
- [x] Gameplay-backed regression and image gates.
- [x] RTV compared with current upstream behavior; ROV retained as fallback.
- [ ] Confirm the second pause path with `0x8253B640` at runtime.
- [ ] Complete a 30-minute stability soak with memory, cache, audio and DRED audit.
- [ ] Verify save → close → reopen → continue on the same user-data root.
- [ ] Build and inspect the release ZIP after all runtime gates pass.

Release inspection is now automated by `validate_release_zip.ps1`. It rejects
extra, missing, duplicate or empty files and unsafe traversal paths, verifies
the PE signature of every packaged executable and DLL, and requires the config
to retain ROV plus safe fetch-constant validation. The existing v0.2.1 archive
passes these checks, but a fresh package is still required after the runtime
gates and current commits.
