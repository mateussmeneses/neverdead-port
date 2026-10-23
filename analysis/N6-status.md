# NeverDead N6: input, audio, saves, and gameplay systems

## Entry state

The verified D3D12 title frame satisfies the N6 prerequisite to begin
input/audio/persistence investigation. This is not a gameplay acceptance
result. No code changes to the SDK adapters are justified yet: the existing
ReXGlue checkout already contains SDL input, SDL audio, XMA, and XContent
implementations; the remaining work is to prove which paths NeverDead
exercises and where the current implementation is insufficient.

### Current user-observed state (2026-10-21)

The user reports a repeatable route through the prologue into gameplay:
the display is already mostly black before pressing A; A advances to a
cutscene, Start advances to another cutscene, and a further Start enters
gameplay. Audio is audible and reported normal, the in-game menu opens, and
the game continues running noticeably slower than expected. The image remains
mostly black, with some details visible. This confirms scene progression and
some menu/input response, but not a correctly rendered 3D frame, full
controller mapping, or a complete gameplay cycle.

The active default-settings run `20261021-181459-613` was responsive at the
last process check, but NeverDead was not the foreground window, so no
screen capture was taken to avoid capturing another application over it.
Its log had 4,642 warnings for the same invalid texture fetch descriptor
(`88C04954 1F318060 004FE45F 00A80D11 00000003 00000200`).
The warning comes from `refs\core\rexglue-sdk\src\graphics\pipeline\texture\cache.cpp:909-923`:
with `gpu_allow_invalid_fetch_constants=false`, `kInvalidTexture` returns
without binding a texture. Setting the CVar true bypasses that check and
continues interpreting the descriptor; this is a diagnostic experiment only,
not an established fix, because it may permit invalid descriptor data.

## Verified observations

| Area | Evidence | What is established | What is not established |
|---|---|---|---|
| Controller discovery | `build\n2-neverdead\logs\neverdead_016.log:16,29-30`; `n6-input-diag-027.log`; `n6-input-diag-029.log`; `n6-xam-input-diag-031.log`; current user report | SDL input initializes and enumerates a DualSense controller. Temporary diagnostics prove synthetic MNK Start/A reaches guest user 0. The user now reports opening the in-game menu and progressing through scenes with Start/A. | The active run has no simultaneous physical-input/XAM/UI capture; camera, axis mapping, vibration, and action response remain unverified. |
| Audio output | `build\n2-neverdead\logs\neverdead_016.log:28`; current user report | SDL audio opened an 8-channel, 48 kHz host endpoint; the user reports audible, normal-sounding audio in the prologue/cutscenes/gameplay. | Timing, spatial mix, decoded sample correctness, and long-run stability have not been measured. |
| XAudio/XMA | `build\n2-neverdead\logs\neverdead_007.1.log:25,109-110,136,141-145`; `refs\core\rexglue-sdk\src\audio\xma_decoder.cpp:339-353` | The XMA decoder thread and XAudio render-driver callbacks ran. The decoder source explicitly notes writes to register `0x0601` (`0x1804`) around a lock operation; it stores/logs the register but has no dedicated behavior for it. | Successful decoding or audible samples are not established. The observed register writes alone do not prove a decoder defect; correlate with decoded/output-buffer state before changing behavior. |
| Save/content APIs | `src\generated\default\neverdead_funcs.h:24443-24449`; `build\n2-neverdead\logs\neverdead_007.log:26254,27030-27047` | The image imports XamContent create/delete/close/get-creator/enumeration and related APIs. Runtime tracing confirms one enumerator returned one existing item and two “Search for DLC” enumerators returned zero. The SDK implements content creation/opening and a content manager (`refs\core\rexglue-sdk\src\kernel\xam\xam_content.cpp:61-64,191-216`; `refs\core\rexglue-sdk\src\system\xam\content_manager.cpp:191-287`). | These observations are enumeration, not save writes or a durable round-trip. `XamContentResolve` is exported by the SDK but is not present in the generated NeverDead imports; it is not currently demonstrated as a NeverDead dependency. |
| Achievements/profile | `src\generated\default\neverdead_funcs.h:24430-24441,24653-24659`; `build\n2-neverdead\logs\neverdead_007.1.log:60` | Achievement/profile/voice imports are present, and the runtime loaded 42 achievement-store entries. | No game achievement unlock, profile flow, or voice-chat use is proven by this log. |
| NeverDead mechanics | Current user report: the sequence reaches gameplay, where the image is mostly black and performance is slow; audio and the menu remain available. | Gameplay scene progression and menu access are user-confirmed. | Dismemberment, reattachment, member physics, particles, ragdoll, collision, animation/state transitions, and checkpoint persistence remain untested. |

The SDK's SDL gamepad implementation already manages SDL device-added,
axis, and button events; XAM input calls route into the shared input system.
The Windows XInput backend is also present. Do not add another input backend
or change button semantics until a gameplay trace identifies a concrete gap.
Five existing SDK tests passed for device capabilities, guest keystroke
delivery, shared guest-user assignment, achievement persistence, and
achievement notifications. This verifies selected SDK components, not
NeverDead gameplay behavior.

## Reproducible test matrix

| Test | Setup/action | Acceptance evidence | Status |
|---|---|---|---|
| Controller mapping | In the current gameplay scene, record one button, each stick axis, triggers, and D-pad through both SDL and XAM call traces. | Guest state matches the physical action and expected in-game action; no repeat/lost input across focus changes. | Partial: the user reports menu access and scene progression, but no simultaneous physical-input/XAM/action trace exists. |
| Camera and vibration | In a stable gameplay scene, move both sticks independently; trigger a known damage/weapon event. | Camera responds on the intended axis; XamInputSetState produces expected motor output or reports a traced unsupported path. | Gameplay entry reported, but the scene darkened and froze before input effects were verified. |
| Audio | In a stable scene with known effects/music, correlate XMA contexts, decoded PCM submission, and host endpoint output. | Audible, correctly timed output; no unexplained unknown-register writes or buffer underruns. | Partial: user reports normal audible audio; decoder correctness and timing remain unmeasured. |
| Save round-trip | Reach the first legitimate save/checkpoint; create/save, exit normally, relaunch, and load. | Same checkpoint/state returns; guest content files and metadata are preserved; checksums/logged offsets are reproducible. | Not tested; current scene is not stable enough to reach a confirmed checkpoint. |
| Achievement/profile | Trigger a known in-game event while tracing XAM calls. | Unlock result, persisted state, and notification match the event; unsupported UI paths fail explicitly. | Gameplay entry reported; no event or achievement unlock verified. |
| Dismemberment and reattachment | In a reproducible combat scene, record detach, physics, reattach, and subsequent state transitions. | A repeatable sequence with no stuck/missing body parts, collision, animation, or effects; compare logs and captures. | Gameplay entry reported, but no combat interaction has been tested. |
| Ragdoll/collision/checkpoint | Repeat a reproducible hit/death/reload sequence. | Stable collision/ragdoll transition and reload from the expected checkpoint. | Not tested; no stable gameplay cycle/checkpoint verified. |

## Current limits and next gate

The latest clean N5 run stopped at the title screen. N6 follow-up runs
`neverdead_019.log` through `neverdead_023.log` no longer report the PPC trap
at `0x82524498` after its observed 16-byte thunk was registered. A temporary,
debug-only instrumentation pass in the local SDK then established that the
focused game window received Return (`vk=13`) with `mnk_mode=true`, and the
MNK driver produced `X_INPUT_GAMEPAD_START` (`0x10`) and A (`0x1000`) state.
`input_system.cpp` assigns synthetic devices to guest user 0, so this reached
the guest input system rather than only the host window. A second temporary
XAM-boundary log confirmed `XamInputGetState user=0 flags=0x1 buttons=0x10`;
see `build\n2-neverdead\logs\n6-input-diag-027.log`,
`n6-input-diag-029.log`, and `n6-xam-input-diag-031.log`.

Despite those states, `n6-after-input-027.png` and
`n6-after-input-029.png` still show the title screen with “Press START”.
Therefore the keyboard-to-MNK/XAM adapter path is functioning, but no gameplay
transition is proven. The XAM-boundary confirmation was a separate run and
did not include a usable screen capture. Both temporary diagnostic changes
were removed and the runtime was rebuilt cleanly; no permanent SDK
diagnostics were retained. One later 45-second attempt lost desktop focus to
another application; its full-desktop screenshot was discarded and is not
used as evidence.

The XAM-boundary diagnostic used the existing runtime with:

```powershell
build\n2-neverdead\neverdead.exe `
  --game_data_root=C:\projetos\NeverDeadxex `
  --user_data_root=C:\projetos\neverdead\build\n2-neverdead\n6-input-diag-user `
  --cache_root=C:\projetos\neverdead\build\n2-neverdead\n6-input-diag-cache `
  --mnk_mode=true --log_level=debug `
  --log_file=C:\projetos\neverdead\build\n2-neverdead\logs\n6-xam-input-diag-031.log
```

The exact post-cleanup build command was
`cmake --build build\n2-neverdead --target neverdead -j 4`; it succeeded after
both diagnostic source edits were removed.

### Focus-verified follow-up run

Run `n6-focused-input-035.log` started the existing runtime with a fresh
user-data/cache pair. The test located the visible top-level window by the
runtime PID, confirmed it was foreground, waited for title initialization,
then sent a Return down/up through Windows `SendInput`. Focus was still on
NeverDead one second later. The client screenshot at
`build\n2-neverdead\logs\n6-focused-input-035.png` was captured about eight
seconds after the tap and still shows “Press START”; its right edge is clipped,
so it is diagnostic only and not N5 frame-acceptance evidence. Its SHA-256 is
`02495F7C88BFAB61476B807B3AA1A035AA8F7F9A54D32255EE61B3225A52629F`
(1536x960). This run did not instrument the XAM boundary, so it does not
simultaneously prove the guest state and frame. Earlier runs 031/032 separately
prove the XAM Start state, but the joined input-to-transition question remains
unresolved. The process was stopped by its exact PID after capture.

Do not make another input-adapter change without evidence of a mismatch. The
remaining blocker is now game-level: determine why the title logic does not
transition after XAM receives the Start state, or verify the behavior with a
real controller interaction in the focused app. Once a gameplay scene is
entered, collect real controller, audio, and save-system traces before
implementing any target-specific adapter. The existing logs and SDK-only unit
tests cannot prove the required action cycle.

### Follow-up static input trace

The generated `sub_823C6940` path does more than poll connectivity: it reads
the `X_INPUT_STATE` returned by `XamInputGetState`, then converts the Start bit
(`0x10`) into its internal per-controller state
(`src\generated\default\neverdead_recomp.21.cpp:12533,12822`). This supports
the conclusion that the state path carries Start into the game's input
representation, but it does not identify which consumer handles the title UI
or prove the title reacts to that state.

The same function also polls `XamInputGetKeystrokeEx` with `flags=2`
(`neverdead_recomp.21.cpp:13005-13015,13119-13124`). The local XAM
implementation sets `XINPUT_FLAG_GAMEPAD` to `1` and rejects nonzero low-byte
flags lacking that bit (`refs\core\rexglue-sdk\src\kernel\xam\xam_input.cpp:34,
161-168`). Consequently, feeding the MNK keystroke queue would not affect this
call under the current HLE behavior. A read-only comparison with Xenia's
upstream [`src/xenia/kernel/xam/xam_input.cc`](https://raw.githubusercontent.com/xenia-project/xenia/master/src/xenia/kernel/xam/xam_input.cc)
shows the same flag guard and behavior, so this is not evidence of a
ReXGlue-specific regression. This comparison documents implementation parity,
not an independent Xbox 360 specification for flag `2`. The PPC caller treats
the nonzero result as "nothing to process" and continues through the
state-polling path. Do not
change the MNK keystroke queue or XAM validation based on this observation.
The menu's actual state consumer and the reason it remains on the title screen
are still unknown.

The REA session inventory reports no native Windows UI/runtime observation
provider; its native UI capture route is macOS-only. Thus the connected REA
tools cannot currently supply the missing simultaneous in-process call and
screen trace on this Windows host.

No permanent input-adapter changes were made during this follow-up.
REA `open_binary` rejected the supplied `default.xex` as an unsupported binary
format, so no REA analysis session was opened. The title-function explanation
remains unknown; the evidence here is limited to generated PPC C++ and runtime
logs, and the REA rejection is not evidence of a game/runtime defect.

The N5 shader/state replay item remains blocked separately: neither PIX nor
RenderDoc capture/replay tooling was available, and the configured build has
no CTest tests. The separate SDK build exposes 218 unit tests: 217 pass, while
the unrelated `Depfile escapes characters make treats as syntax` test fails
because its expected-string literals do not encode backslashes correctly
(`refs\core\rexglue-sdk\tests\unit\codegen\output_stamp_test.cpp:227-228`).
The 217 other tests pass when that case is excluded. N6 may proceed because
the first visible-frame prerequisite is met, but this does not waive N5's
renderer-validation gap.

### Combined focused-run attempt 038

A temporary, uniquely tagged XAM trace was added at the `XamInputGetState`
boundary and the runtime compiled successfully. The paired-input/capture
attempt was then aborted by its focus guard: the game window could not be
confirmed as the foreground window, so **no key was sent** and no before/after
capture was accepted. This does not reproduce the game-level title-screen
symptom and supplies no new evidence about the guest's response. The temporary
trace and launcher script were removed, and the clean runtime target rebuilt
successfully. Existing unrelated SDK worktree changes were left untouched.

Static profile inspection found that `UserProfile::signin_state()` returns
`1` (`refs\core\rexglue-sdk\include\rex\system\xam\user_profile.h:221`).
Generated helpers call `XamShowSigninUI` and then query sign-in state, but the
available trace does not establish that these helpers control the title
screen. Sign-in remains an unverified possibility, not a diagnosed cause.

### Physical-controller runs 039/040 and newly decoded PPC target

Run `n6-controller-live-039.log` records successful `XamInputGetState`
responses for Start (`buttons=0x0010`) at 16:31:20.301 and A
(`buttons=0x1000`) at 16:31:23.301, both for guest user 0 with flags `0x1`.
This proves the guest XAM boundary received those button states in one
execution. The trace did not capture the UI simultaneously, so it does not
establish which screen followed them or that gameplay was entered.

The same run then failed at 16:31:41.952 with
`Call to invalid or unregistered function at guest address 0x8253A650
(LR=0x822587C4, SP=0x7018F230)`. Generated `sub_82258700` shows that LR is the
return site of an indirect virtual call (`mtctr`/`bctrl`); the method pointer
is loaded from vtable offset 116. The failed target lies between registered
four-instruction thunks at `0x8253A640` and `0x8253A660`. An explicit
`0x10`-byte boundary was added to `src\neverdead_config.toml`, then ReXGlue
decoded it as:

```text
lwz r11,-4(r3)
subf r3,r11,r3
addi r3,r3,-160
b 0x825143A0
```

This confirms `0x8253A650` is a real adjustor thunk with semantics that forward
to the generated `sub_825143A0`, not an invented success stub. ReXGlue
regenerated six outputs; `neverdead_recomp.0.cpp`, registration, declarations,
and `neverdead_init.cpp` now include it. The exact generation log is
`logs\n6-codegen-target-039.log`.

The rebuilt runtime compiled successfully. Follow-up run
`build\n2-neverdead\logs\n6-controller-live-040.log` launched with an isolated
profile/cache. It remained responsive for over two minutes with no controller
button changes and no repeat of the invalid-function trap; this is not a
valid regression verdict because no post-fix Start/A press was observed. A
focus-guarded keyboard fallback also produced no XAM button change. The
interactive prompt reported that the user was unavailable, so the new target
still needs a physical Start/A retest before it can be claimed to unblock
gameplay.

Temporary XAM tracing was removed after these runs, and the clean runtime was
rebuilt. The function boundary and generated PPC implementation are the only
permanent code changes in this attempt. Run logs/profiles are retained under
`build\n2-neverdead\` for audit. The N5 renderer replay item remains
independently blocked.

### Single-player loading runs 041-044

Run `n6-singleplayer-crash-041.log` reproduced the loading failure after
Start/A reached XAM user 0. The runtime trapped at `0x8225B0E8`
(`LR=0x82238F80`). ReXGlue decoded the 16-byte target as an adjustor thunk
that adds 180 to the adjusted `r3` and branches to `sub_82258700`; this
boundary was retained in `src\neverdead_config.toml` and the generated runtime
compiled.

Run `n6-singleplayer-crash-042.log` then trapped at `0x82537E50`
(`LR=0x824CA4AC`) during the virtual dispatch in generated
`neverdead_recomp.61.cpp`. ReXGlue decoded the 16-byte boundary as:

```text
lwz r11,-4(r3)
subf r3,r11,r3
addi r3,r3,-296
b 0x8250bea8
```

The generated thunk forwards to `sub_8250BEA8`; the runtime build succeeded.

Run `n6-singleplayer-crash-043.log` recorded Start (`0x0010`) and repeated A
(`0x1000`) transitions at `XamInputGetState`, then the user reported that the
runtime closed. The fatal log entry confirms another invalid guest target:
`0x825DC960` with `LR=0x822A87A8` (line 15805). The call site in
`neverdead_recomp.27.cpp` loads a virtual method from vtable offset 16 and
executes `bctrl`. The target is exactly between registered adjustor thunks
`0x825DC950` and `0x825DC970`. ReXGlue decoded the candidate as:

```text
lwz r11,-4(r3)
subf r3,r11,r3
b 0x825db3a0
```

This establishes a real adjustor thunk forwarding to `sub_825DB3A0`, rather
than a fabricated success stub. The boundary was added to
`src\neverdead_config.toml`, generated, and compiled successfully.

Run `n6-singleplayer-crash-044.log` did receive the physical sequence: Start
(`0x0010`) followed by multiple A (`0x1000`) presses were recorded at the XAM
boundary. The user confirmed that the runtime closed. The log identifies the
next fatal as `0x82299E48` with `LR=0x8229F8F0` (line 27351), a virtual call in
the generated iterator routine `sub_8229F838`. ReXGlue decoded the target
within the gap before the next registered function at `0x82299E70` as:

```text
lwz r11,96(r3)
cmplwi cr6,r11,0
beq 0x82299e68
rotlwi r3,r11,0
lwz r11,0(r3)
lwz r10,64(r11)
mtctr r10
bctr
```

This is a valid PPC virtual-dispatch wrapper, not a guessed thunk or stub.
The `0x28`-byte boundary was added to `src\neverdead_config.toml`, generated,
and the runtime compiled successfully. Run 044 therefore proves the prior
`0x825DC960` target no longer trapped during this sequence, but does not yet
prove that gameplay can be entered. The next runtime retest must use the
resulting build and record the next fatal target, if any.

The temporary `[DEBUG-N6-CRASH43]` XAM button trace remains in
`refs\core\rexglue-sdk\src\kernel\xam\xam_input.cpp` to correlate that retest
and must be removed, followed by a clean rebuild, after input evidence is
collected. Logs for runs 041-044 are under `build\n2-neverdead\logs\`.

Run `n6-singleplayer-crash-045.log` was launched after compiling the
`0x82299E48` function. At the latest check its process was responsive, but no
Start/A edges or fatal entry were present. The game was not the foreground
window (foreground PID differed from the game's PID), so no synthetic keyboard
input was sent. This run is waiting for a focused physical-controller retest;
it supplies no pass/fail evidence for the new boundary.

Correction from the user's subsequent report and preserved log: run 045 did
receive physical Start (`0x0010`) and repeated A (`0x1000`) transitions at
`XamInputGetState`, then closed. The fatal at line 20165 is an invalid guest
target `0x82292C78` (`LR=0x82292544`). The call site in
`neverdead_recomp.101.cpp` is a virtual call through the vtable method slot at
offset 16. The target lies between registered 16-byte adjustor thunks at
`0x82292C68` and `0x82292C88`. ReXGlue decoded the exact 16-byte target as:

```text
lwz r11,-4(r3)
subf r3,r11,r3
b 0x82292788
```

This confirms a real adjustor thunk forwarding to `sub_82292788`. Its
configuration boundary was added and the generated runtime compiled
successfully. The failure advanced past the previous `0x82299E48` trap; a
gameplay scene is still not verified. Run 046 is the next retest required to
determine whether another missing PPC boundary or a different failure remains.

The N5 shader/frame replay and D3D12 validation item remains independently
blocked. All gameplay-dependent N6 test-matrix entries remain blocked until
a reproducible gameplay scene is reached.

### Run 046 and faster retest loop

Run `n6-singleplayer-crash-046.log` received repeated XAM A (`0x1000`) edges,
then trapped at `0x8252FCF8` (`LR=0x82510540`, line 15323). The call site in
`neverdead_recomp.80.cpp` is an indirect dispatch with floating-point state
live across the call. The address is a 16-byte gap between registered
functions at `0x8252FCE8` and `0x8252FD08`. ReXGlue decoded it as:

```text
lwz r11,-4(r3)
subf r3,r11,r3
addi r3,r3,-288
b 0x8250bea8
```

This is a real adjustor thunk forwarding to `sub_8250BEA8`; its boundary was
added and the runtime compiled successfully.

To reduce repeated manual setup, `analysis\run-n6-cycle.ps1` now performs the
verified CMake build, launches one runtime with unique user/cache/log paths,
waits for its exit, and reports XAM button edges plus the last invalid-function
fatal target/LR. It intentionally sends no keyboard/controller input, refuses
to start a second NeverDead process, and does not add guessed PPC boundaries.
The summary parser was exercised against run 046 and reported 12 XAM button
edges, A (`0x1000`), fatal target `0x8252FCF8`, and LR `0x82510540`, matching
the preserved log.

The first full runner invocation completed its incremental build and opened a
responsive process (PID 30656). Its run ID is
`20261021-171815-092`, with log
`build\n2-neverdead\logs\n6-cycle-20261021-171815-092.log`. At the latest
inspection the fresh log had not recorded button edges or a fatal yet; the
runner is waiting for the physical Start/A attempt and process exit.

Runner and input validation:

- Run `20261021-172338-663` confirmed the focus guard, but Windows rejected
  the first key event because the x64 `INPUT` union was undersized. The
  structure was corrected to include the full mouse-input union size.
- Run `20261021-172434-818` logged Start and A at XAM, but the verifier
  incorrectly searched only the last 500 lines. The high-volume renderer log
  pushed the input edges outside that window; the test process was stopped
  after this parser defect was found.
- Run `20261021-172605-041` logged and confirmed Start and the first A. The
  game lost foreground before the next A, so remaining input was cancelled
  and the verification process was stopped. The runner now requests the
  game's foreground again before each tap and still sends nothing unless the
  foreground PID is verified.
- Run `20261021-172704-476` ended at
  `0x82537E90` (`LR=0x8223EF68`, line 31770) after Start/A XAM states. The
  user clarified that the actions advancing the game were manual and that no
  gameplay was automated; the XAM log records button values but not their
  source. Treat the input source as user-reported manual, and do not count
  these transitions as proof that automated controls advanced the game.
  The user observed a crash while loading the prologue; gameplay was not
  reached.

The new fatal target lies between registered functions at `0x82537E80` and
`0x82537EA0`. ReXGlue decoded the configured 16-byte boundary as:

```text
lwz r11,-4(r3)
subf r3,r11,r3
addi r3,r3,-8
b 0x82524ec8
```

The target is a valid adjustor thunk forwarding to `sub_82524EC8`; the
generated function was added and the runtime build succeeded. The runner now
defaults to manual controller input (`analysis\run-n6-cycle.ps1`). The
`-AutoInput` option remains opt-in; it requests the game window's foreground
and checks XAM button edges before continuing, but its output alone does not
prove visible menu navigation.

The runtime was rebuilt with `0x82537E90` and relaunched in default manual
mode as run `20261021-173039-937` (PID 31316), using isolated user/cache
directories and log `build\n2-neverdead\logs\n6-cycle-20261021-173039-937.log`.
This run received Start/A XAM states and closed during loading with fatal
target `0x82536F78` (`LR=0x822412D8`, line 22625). The indirect call site is in
`neverdead_recomp.45.cpp` and dispatches through vtable offset 20. The target
is between existing entries `0x82536F58` and `0x82536F88`; ReXGlue decoded
the 16-byte function as:

```text
lwz r11,-4(r3)
subf r3,r11,r3
b 0x825312d0
```

This is a verified adjustor thunk forwarding to `sub_825312D0`. The boundary
was added to the config and the runtime build passed. No gameplay scene was
reached. The next manual run is required to verify this fix and expose any
subsequent blocker.

Run `20261021-173536-142` closed after receiving XAM states for A (`0x1000`),
Start (`0x0010`), and Back (`0x0020`). Its fatal was `0x82603520`
(`LR=0x825E73F0`, line 17133), an indirect call in `neverdead_recomp.46.cpp`
through a function pointer read from offset 160. The next registered code
entry is `0x82603528`. ReXGlue decoded the 8-byte gap as:

```text
lwz r3,48(r3)
b 0x82380680
```

This is a real PPC wrapper forwarding to `sub_82380680`; it was added to the
config and the runtime build passed. The run still stopped during loading;
gameplay remains unverified. Another manual cycle is needed to confirm this
target and identify any later blocker.

Run `20261021-174040-425` received XAM states for Start (`0x0010`) and A
(`0x1000`). The user reported that the game reached a scene, then crashed after
the second Start press. The fatal was `0x8254A690` (`LR=0x822412D8`), a
vtable-dispatched PPC target. The target lies in the 16-byte gap between
`0x8254A680` and `0x8254A6A0`. ReXGlue decoded it as an adjustor thunk:

```text
lwz r11,-4(r3)
subf r3,r11,r3
addi r3,r3,-32
b 0x825312d0
```

This validates `0x8254A690` as a real PPC wrapper forwarding to
`sub_825312D0`; the boundary was added to `src\neverdead_config.toml`. The
user-observed scene is a meaningful advance, but no gameplay systems or
playability are verified. The runtime is being rebuilt and relaunched in
manual-input mode to check whether this boundary clears the crash.

Run `20261021-174325-475` rebuilt successfully with the validated
`0x8254A690` wrapper. The user reported reaching a scene; the runtime then
closed after the second Start press. The fatal was `0x82536FE8`
(`LR=0x825ED6B0`), called indirectly from `neverdead_recomp.61.cpp` through
the function pointer at object offset 16. It lies in the 16-byte gap between
registered entries `0x82536FD8` and `0x82536FF8`. ReXGlue decoded it as:

```text
lwz r11,-4(r3)
subf r3,r11,r3
b 0x82531200
```

This confirms a real adjustor thunk to `sub_82531200`; the config boundary was
added and the runtime build passed. The run had 92 XAM button edges, including
Start/A states, but these logs do not identify the physical input source.
The user's report confirms a scene was reached; no gameplay cycle is yet
verified. The runtime has been relaunched for another manual retest.

Run `20261021-180249-290` ended with fatal target `0x8252FDA8`
(`LR=0x8251397C`). The caller is `neverdead_recomp.72.cpp` and dispatches
through a vtable function pointer at offset 60. The target lies between
registered entries `0x8252FD98` and `0x8252FDB8`; ReXGlue decoded the
16-byte entry as:

```text
lwz r11,-4(r3)
subf r3,r11,r3
b 0x82524760
```

This validates the target as an adjustor thunk forwarding to
`sub_82524760`. It was added to `src\neverdead_config.toml`; codegen and the
runtime build passed. The run recorded 22 XAM edges, including Start/A. No
new visual scene observation was reported for this run. Another manual
retest is needed to determine whether this was a new execution path or a
scene transition regression.

Run `20261021-180554-377` ended with fatal `0x82537EE0`, again at
`LR=0x8251397C` through vtable offset 60. The target is in the 0x30-byte gap
between registered entries `0x82537ED0` and `0x82537F00`. ReXGlue decoded
the configured 0x20-byte function as:

```text
lwz r11,-4(r3)
subf r3,r11,r3
addi r3,r3,-8
b 0x82524760
```

The target is a valid adjustor thunk to `sub_82524760`; it is now configured
and the runtime build passed. The run recorded 36 XAM edges, including
Start/A, then closed. The next manual retest will check whether this further
vtable implementation clears the failure.

Run `20261021-180733-183` ended at `0x8264A728` (`LR=0x82643FCC`) after the
user reported reaching gameplay, seeing a very dark screen, and then a freeze.
The indirect caller at `neverdead_recomp.67.cpp` dispatches through vtable
offset 32. The target lies between registered entries `0x8264A718` and
`0x8264A740`; ReXGlue decoded a real PPC wrapper that loads an argument and
calls `sub_8237A248`, rather than a bare adjustor thunk:

```text
lis r4,-10676
lwz r3,4(r3)
li r5,0
ori r4,r4,34263
b 0x8237a248
```

The `0x8264A728` boundary is configured with size `0x18`; the runtime build
passed. The log shows sustained Xenos render-target/pipeline creation through
the fatal, but it does not prove that the dark image was caused by the GPU;
the target fatal remains the first actionable stop in this run. Gameplay entry
is now user-confirmed, while stable rendering, input response, sound, saves,
and gameplay mechanics remain unverified. The earlier “no gameplay scene”
statements in this status file are superseded by this run.

Run `20261021-181020-606` closed at `0x825E05F8` (`LR=0x8265D6CC`), an
indirect call through a function pointer at object offset 160. ReXGlue
decoded the 0x18-byte entry between `0x825E05C8` and `0x825E0610` as a PPC
function that loads arguments and dispatches through another vtable at
offset 224. The boundary is configured and the runtime build passed.

At the user's request, run `20261021-181215-714` used the runner's guarded
automatic sequence: XAM confirmed Start and three A presses, after which the
process ran unattended and closed at `0x82247F70` (`LR=0x8224054C`). The
target is a valid 16-byte adjustor thunk forwarding to `sub_82247350`, lying
between registered entries `0x82247F60` and `0x82247F80`. It is configured
and the runtime build passed. The automatic sequence establishes XAM input
delivery, not which menus were visibly selected; the previously reported
dark gameplay/freeze remains a separate user observation.

Run `20261021-181459-613` completed the same authorized automatic sequence
(Start, A x3), all confirmed at XAM, and remained alive/responsive at the last
check. Its log continued to emit repeated invalid texture-fetch-constant
warnings during rendering. This is a concrete renderer lead for the dark
image, not proof of the cause; do not enable the suggested global bypass as a
fix. No visual capture or gameplay control response was obtained unattended.

### Follow-up on Run 613, resolution of 0x825E04F0 fatal crash and invalid texture constant fix

Audit of the complete log for run `20261021-181459-613` (which continued executing past initial status recording until 18:43:11) revealed two critical findings:

1. **Fatal Unregistered Target Crash**:
   At timestamp `18:43:11.618`, run 613 crashed with:
   `[critical] [core] [t41772] [FATAL] Call to invalid or unregistered function at guest address 0x825E04F0 (LR=0x826389D8, SP=0x7018F790)`
   Disassembly of `neverdead-image.bin` at `0x825E04F0` using Capstone identified a contiguous family of 11 virtual dispatch wrapper functions between `0x825E0478` and `0x825E0564`, plus `0x825E05E0` (sister routines to previously added `0x825E05F8` and `0x825E05C8`). Each function is exactly 6 PPC instructions (0x18 bytes):
   `	ext
   lwz r4, 8(r3)
   lwz r3, 12(r3)
   lwz r11, 0(r3)
   lwz r10, OFFSET(r11)
   mtctr r10
   bctr
   `
   Offsets span `0xB8` through `0xE8`. All 11 verified boundaries (`0x825E0478`, `0x825E0490`, `0x825E04A8`, `0x825E04C0`, `0x825E04D8`, `0x825E04F0`, `0x825E0508`, `0x825E0520`, `0x825E0538`, `0x825E0550`, `0x825E05E0`) were configured in `src\neverdead_config.toml`. ReXGlue codegen regenerated affected shards in 21.2s, registering 24,703 functions total.

2. **Resolution of Dark Gameplay / Invalid Texture Fetch Warnings**:
   Analysis of the 4,642 warnings for descriptor `(88C04954 1F318060 004FE45F 00A80D11 00000003 00000200)` confirmed that it represents the primary 1120x640 HDR floating point scene render target (`k_16_16_16_16_FLOAT`, format 0x20, tiled, pitch 35) at base address `0x1F318000`. The game samples this surface during post-processing/tonemapping passes with `FetchConstantType::kInvalidTexture` (type 0). Under the default ReXGlue/Xenia policy, `TextureCache::BindingInfoFromFetchConstant` rejected the texture constant and returned `kInvalidTexture`, forcing shaders to sample black.
   Setting `gpu_allow_invalid_fetch_constants = true` in `build\n2-neverdead\neverdead.toml` and `--gpu_allow_invalid_fetch_constants=true` in `analysis\run-n6-cycle.ps1` allows the texture cache to bind the valid render target.

3. **Verification in Run `20261023-010050-545`**:
   The rebuilt runtime (PID 14604) executed continuously across multiple log rotations (>17 MB of log data) with over 11 minutes of CPU time:
   - **Invalid texture fetch warnings**: 0 (reduced from 4,642 to 0).
   - **Fatal function traps**: 0 (the fatal crash at `0x825E04F0` was completely eliminated).
   - **D3D12 GPU pipelines**: Active and running on NVIDIA RTX GPU.
   - **SDL audio engine**: Active, streaming audio frames continuously.
