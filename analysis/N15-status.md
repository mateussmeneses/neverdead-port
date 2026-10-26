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

The affected Asura chain uses 1120x640 `k_16_16_16_16_FLOAT` and
`k_16_16_FLOAT` scene surfaces. Disabling gamma aliasing did not restore it, and
`snorm16_render_target_full_range` applies to fixed16 host targets rather than
these primary FLOAT16 surfaces.

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

The upstream comparison did identify one applicable post-baseline correction:
Xenia commit `067641668f1fba4ef89bf1796a555f74b0cc3469` fixes MIN/MAX blending
with source factors on host render targets. D3D12 ignores those factors for
MIN/MAX, while Xenos applies them. The RT0 `SrcAlpha`/`One` case has been ported
to ReXGlue without changing the ROV shader path; compilation and an RTV visual
gate are pending the next idle test window.

Two later corrections remain separate follow-up candidates rather than being
mixed into that isolation run. Commit `2912da02f` repairs cross-format transfer
to gamma targets backed by `R16G16B16A16_UNORM`; disabling that backing did not
fix NeverDead, so it is not yet the primary suspect. Commit `4cc584f47` maps
constant-alpha blending to D3D12 Options13 and provides a legacy fallback. It
is applicable to the old RTV backend, but should be tested only if the smaller
MIN/MAX correction fails the image gate so the cause remains attributable.

## 3. Long-run stability

The first soak exposed missing PPC thunk boundaries during repeated pause/resume
paths. The evidence-backed functions are now registered in
`src/neverdead_config.toml`, including the eight-instruction tail thunk at
`0x8253B640`.

The first laptop-safe attempt reached gameplay and wrote 9,188 frame samples,
then the user-activity watchdog stopped it before the first five-minute pause;
the runtime log contains no crash, missing-function or DRED signature. The
controller now treats this as a recoverable interruption: it terminates the
game, waits for another five-minute Windows idle period and repeats the same run
without manual re-arming. Input is sent only to the game window, the game runs
below normal priority, and a named mutex prevents concurrent profilers. A
successful 15-minute confirmation will be followed by the full 30-minute soak
and the save → close → reopen → continue cycle.

## 4. Remaining acceptance checks

- [x] Three repeatable ROV gameplay benchmarks.
- [x] CPU/GPU/swap/presentation timings separated.
- [x] Gameplay-backed regression and image gates.
- [x] RTV compared with current upstream behavior; ROV retained as fallback.
- [ ] Confirm the second pause path with `0x8253B640` at runtime.
- [ ] Complete a 30-minute stability soak with memory, cache, audio and DRED audit.
- [ ] Verify save → close → reopen → continue on the same user-data root.
- [ ] Build and inspect the release ZIP after all runtime gates pass.
