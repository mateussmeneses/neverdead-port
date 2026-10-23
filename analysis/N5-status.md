# NeverDead N5: Xenos-to-PC renderer bring-up

## Result and acceptance boundary

**The right-edge crop was a screenshot-capture artifact, not a demonstrated
renderer defect.** A direct D3D12 guest-output readback at the title screen
contains the complete “NEVERDEAD” logo and copyright. A separate capture of
the actual physical game-client rectangle also shows the complete title frame.
The physical host client is 16:9; the captured 1120x640 guest texture is
slightly narrower and is scaled to fit.

The earlier `PrintWindow` images were taken at DPI-virtualized window bounds.
At 125% Windows scaling, the requested 1280x720 logical client is a 1600x900
physical client. The older 1294x758 window capture therefore was not a reliable
pixel-for-pixel representation of the physical DXGI client and falsely
suggested clipping. A 4:3 diagnostic run was also unnecessary to fix the
issue; no renderer crop/overscan workaround was added.

N5's first visible-frame gate is now satisfied, but N5 is not fully complete.
No RenderDoc/PIX capture or shader/state replay test was run, and D3D12
debug/DRED output has not been exhaustively reviewed. The remaining replay
item is a real blocker: no RenderDoc or PIX capture/replay executable was
available in the local environment, and `ctest --test-dir build\n2-neverdead
-N` reports zero project tests. The runtime log shows D3D12 debug/DRED enabled
but does not record InfoQueue messages; the provider filters informational
messages and selected compatibility IDs, and break-on-warning is not enabled
by the project config. Therefore the existing log is not evidence of a clean
validation pass. Keep this item blocked rather than treating the title frame
or absence of logged D3D12 errors as replay/validation acceptance.

D3D12 remains the evidence-based backend for this attempt: the configured
Windows build has D3D12 enabled and Vulkan disabled, and the Xenos plugin
selected D3D12. This establishes backend availability, not correctness of all
Xenos state translation.

## Runtime evidence

`build\n2-neverdead\logs\neverdead_009.log` records D3D12 initialization,
36 shaders translated from storage, and 28 graphics pipelines created from
storage. It also records unresolved filesystem/HLE messages for
`\Device\Image` and `game:\FMV\CESA.bik`; their necessity is not established by
this run. Later runs `neverdead_011.log` through `neverdead_015.log` exercised
the diagnostic guest readback; no new fatal PPC target was observed in the
inspected intervals. The clean-plugin smoke run `neverdead_016.log` initialized
the runtime and remained responsive during its 22-second check.

The paired title-frame evidence is:

| File | Image size | SHA-256 | Capture |
|---|---:|---|---|
| `build\n2-neverdead\logs\n5-guest-output-paired.png` | 1120x640 | `D95D4E02556A0CF39CE7B2359AF2A9C87037AA4732BAC83116B3099478D373AB` | D3D12 guest-output readback |
| `build\n2-neverdead\logs\n5-window-client-physical-1600x900.png` | 1600x900 | `9BF037E7A9EC990C4B1A2B22744C8A1F38929D66EB4AAB1495ADA677B0E73022` | Physical client rectangle, DPI-aware |
| `build\n2-neverdead\logs\n5-window-paired-014.png` | 1294x758 | `014D760D3B3A472793286200AE1FF18BBF16674752A819E5FDB4DB66F14795F2` | DPI-virtualized `PrintWindow`; not acceptance evidence |

The guest texture is 1120x640; the actual client is 1600x900. Their pixel
dimensions differ because the guest output is scaled for the host window, not
because either capture omits the logo.

The first run that displayed the title later trapped at `0x8234ED30` (log
`neverdead_007.log`). After registering that observed thunk, the latest run
remained at the title screen without another observed PPC trap during the
inspected interval. This does not establish gameplay or long-term stability.

## PPC blocker investigation and changes

Three observed call targets were absent from the generated function table and
were added as explicit boundaries in `src\neverdead_config.toml`:

```toml
"0x827318E8" = { name = "sub_827318E8", size = 0x58 }
"0x827318D0" = { name = "sub_827318D0", size = 0x8 }
"0x8234ED30" = { name = "sub_8234ED30", size = 0x8 }
```

For `0x827318E8`, the guest routine ends in `bctr` at `0x8273193C`; the observed
extent ends before the next thunk at `0x82731940`. The other two targets were
observed as 8-byte adjustor thunks. ReXGlue regenerated the declarations,
registration, partition data, and PPC shards, and the affected shards were
compiled. The first recorded codegen invocation was:

```powershell
& refs\core\rexglue-sdk\out\win-amd64\rexglue.exe --log-level info --log-file logs\n5-codegen-manual-target.log --force codegen src\neverdead_manifest.toml
```

## Build recovery

The ordinary Ninja build initially encountered 15 Windows checkout placeholders
for libmspack sources. The corresponding real files already existed in the
nested local libmspack checkout. They were temporarily materialized as hard
links for the Ninja build; the host/runtime, Xenos plugin, and changed PPC
shards built successfully. All 15 placeholder files were restored and
byte-verified afterward. No dependency was downloaded and no submodule was
updated.

## Files and remaining limits

- `src\neverdead_config.toml` — the three evidence-based PPC boundaries.
- `src\generated\default\` — regenerated declarations, registration,
  partition map, and PPC shards.
- `src\src\neverdead_app.h` — selects `gpu_plugin = "xenos"`.
- `build\n2-neverdead\neverdead.toml` — diagnostic Xenos, D3D12 debug, marker,
  and shader-dump settings.
- `build\n2-neverdead\n5-shaders\` — shader artifacts from the initial
  diagnostic run.
- `build\n2-neverdead\logs\neverdead_007.log` through
  `neverdead_016.log` — runtime evidence; `logs\n5-codegen-manual-target*.log`
  — codegen evidence.
- `build\n2-neverdead\logs\n5-window.png` and
  `n5-window-720p.png` — earlier DPI-virtualized `PrintWindow` captures; do not
  use them to assess physical client output.
- The temporary guest-readback instrumentation in the SDK's
  `graphics\d3d12\command_processor.cpp` was removed after capture. That source
  file is restored; the clean Xenos plugin was rebuilt and staged with matching
  SDK/build SHA-256 `AE4633622BCEA4455D9222C89F79F0D26376812867779258EF123E3B643158EA`.

The next gate is a supported shader/state replay test and captured D3D12
InfoQueue output using a local PIX/RenderDoc workflow. The identifiable title
frame is verified, but texture conversion across formats, render-target/state
correctness outside this frame, exhaustive validation, and gameplay remain
unverified.
