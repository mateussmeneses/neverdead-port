# NeverDead N4: Asura data, streaming, and VFS

## Result and scope

The supplied dump was examined read-only. This pass established and tested
bounded layouts for the `LZXTDECODE` segment table, the single-chunk `TXTH`
sample, and the `FCSR` records in `Envs\NeverDead.Xbox360_textures`. It did not
decompress game assets, extract payloads, modify the dump, or establish that the
first scene renders.

**N4 is partially complete.** The current VFS resolves the observed menu text
and loading-GUI requests, and the texture aggregate has validated record
boundaries. The remaining blocker is semantic support for the XPR2/Xenos
texture payloads and unknown Asura tags used by fonts, audio, and scene
streaming. No extra VFS layer was added.

## Evidence and verified facts

### Dump inventory and hashes

`analysis\xex\inventory.json` already contains the per-file SHA-256 inventory;
it was reused rather than hashing the 6.7-GB dump again. The dump inventory
records 429 files totaling 6,711,402,803 bytes.

| File | Size | SHA-256 |
|---|---:|---|
| `Envs\NeverDead.Xbox360_textures` | 1,512,421,920 | `39e34da5717782a00518b30e8dab912a4f2b9d7184b8dbbc872121ede060f727` |
| `GUIMenu\loadingInitial.guiBE` | 171,200 | `bf15a040b1b25cb1d82f87a7c5c293ae8b9839dbc85d20abbfbc4f699e5014d4` |
| `Text\Menu\Menu_En.asrBE` | 81,077 | `b8b218a1b78dcaf0fd002bf962cbdeda96d1892fa4330f6b13f7e4b35fb8f7a2` |
| `Chars\MP_Alex.xbox360` | 23,624,430 | `d51b8cec2b3428ec1d5953fbc28a8a45b846adf3c5301629abd2c60bbc6c4748` |
| `Envs\SP\Asylum.xbox360` | 57,091,462 | `b62c56e57254ad7dc21aa6dec9436fb516c7e6deaba5e5e7387c49a169afc97b` |

### XCTD / Xbox LZX metadata

The local QuickBMS source identifies `0x0FF512ED` as `LZXTDECODE` and parses a
16-byte header with big-endian flags, a segment count, and either 20-bit or
32-bit packed output-size entries (`refs\asura\QuickBMS\src\unz.c:1168-1249`).
It computes the XMem window and segment block sizes at lines 1235-1253 and calls
`XMemDecompressSegmentTD` only in the Windows build path at lines 1293-1300.
The local README lists `XMemDecompress`/`xmemlzx` for the two Xbox compression
identifiers (`refs\asura\QuickBMS\readme.md:1943-1945`).

A streaming header/table scan of the dump found **71** such files. All 71
segment tables fit their files and parsed: 38 use 32-bit entries and 33 use
20-bit entries, for 9,778 declared segments and 38,308 table bytes total.
Summing the declared segment output sizes gives 2,995,974,428 bytes; this is
metadata, **not a decompressed-output measurement**. The compressed inputs total
1,276,644,610 bytes. No decoder was run and no decompressed bytes were written.

For example, `loadingInitial.guiBE` has flags `0x504000a2`, two 32-bit entries,
and a table-declared output size of 1,459,621 bytes. `MP_Alex.xbox360` has 181
32-bit entries totaling 48,827,269 bytes; `Asylum.xbox360` has 436 entries
totaling 155,273,464 bytes. These values are independently reproduced by
`analysis\formats\asura_probe.py`.

The QuickBMS checkout contains source and documentation but no runnable
QuickBMS executable or game-specific `.bms` script was found. Extraction and
XMem decompression were therefore not attempted.

### Asura `TXTH` and `FCSR`

`Text\Menu\Menu_En.asrBE` begins with `Asura   TXTH`. Its big-endian payload
length is 81,053, version is 2, flags are 0, and `24 + payload length` equals
the 81,077-byte file length. This validates the envelope for this sample only;
the text table payload is not decoded. A byte sequence in the payload is
`00 53 00 74 ...`, consistent with UTF-16BE text, not UTF-16LE. This corrects
the earlier preliminary note that called the sample UTF-16LE.

The texture aggregate begins with `Asura   ` followed by `FCSR`. Walking it
using the observed big-endian record size and five big-endian metadata words
validated 7,325 records from offset 8 through offset 1,512,421,916. Each record
has a NUL-terminated ASCII resource name, zero padding to a 4-byte payload
boundary, and a payload whose declared size stays inside the record. The
remaining four bytes at EOF are zero. No payload bytes were copied or
decompressed; only each payload's first four bytes were read:

| Payload signature | Records |
|---|---:|
| `DDS ` | 3,510 |
| `XPR2` | 3,815 |

The stored names mostly end in `.tga`, despite the payload signatures. The
record stream is structurally validated, but the meaning of all metadata
fields, the XPR2 layout, and the full texture decoding path remain unknown.
`Fonts\buttons.asrBE` has a valid first FCSR record but 1,096 trailing bytes
beginning with `TXTT`; it is not treated as the texture aggregate. The
`LFSR` and `STSA` tags in `Fonts\Fonts.asrBE` and
`sounds\StreamingSounds.asrBE` remain unsupported.

### PSP comparison, explicitly bounded

The local RenegadeSquadron-PC code is a PSP reference, not proof of
NeverDead/Xbox 360 compatibility. Its text parser reads little-endian chunk
sizes and `HTXT`/`LTXT` records
(`refs\asura\RenegadeSquadron-PC\work\tools\pcmods\asura_text.py:1-18`).
Its texture tool reads little-endian `RSCF` records and PSP IDX4/IDX8 texture
payloads (`refs\asura\RenegadeSquadron-PC\work\tools\pcmods\texture_dump.py:3,
43-46,96-103`). NeverDead samples instead show big-endian metadata and
`FCSR`/DDS/XPR2 signatures. The PSP parsers were not reused.

## VFS and runtime evidence

`Runtime::SetupVfs` mounts `game_data_root` at
`\Device\Harddisk0\Partition1` and registers `game:` and `D:` symbolic links
(`refs\core\rexglue-sdk\src\system\runtime.cpp:294-318`). The saved N3 trace
records this mount and both links (`logs\n3-run10.log:20-22`), starts
`TextureStreamingThread` (`:608`) and `Asura_AsyncLoader Thread` (`:1162`),
resolves `GAME:\Text` (`:993-995`), and resolves
`GAME:\GUIMenu\loadingInitial.guiBE` with successful XCTD information queries
(`:2055-2066`).

The trace has two VFS misses: `default.xexp` (`:37`) and
`GAME:\default.cam.txt` (`:1172`). The log does not establish whether either is
optional or required. There is no corresponding miss for the observed menu
text or loading GUI. The trace includes 26 distinct `GAME:` create paths for
text, GUI, fonts, sound, and `misc\common.asrBE`; for example, the menu file is
opened successfully (`:4987-5007`), and `StreamingSounds.asrBE` is opened and
read in two chunks (`:9732-9752`). It contains no `GAME:\Envs\...` or
`GAME:\Chars\...` requests. Thus this saved boot trace has not reached
first-scene resource loading. These path and read results do not prove that the
engine decoded or rendered those assets.

## Changes and reproducibility

Added:

- `analysis\formats\asura_probe.py`: read-only CLI for bounded XCTD headers and
  segment tables, the validated TXTH envelope, and FCSR resource records.
  Unsupported tags are reported as unsupported; it does not decompress or
  extract payloads.
- `analysis\formats\test_asura_probe.py`: synthetic tests for 20-bit and
  32-bit segment tables, TXTH boundaries, FCSR record boundaries, and malformed
  inputs.

Commands run:

```powershell
python -m unittest discover -s analysis\formats -p "test_*.py" -v
python analysis\formats\asura_probe.py C:\projetos\NeverDeadxex\Text\Menu\Menu_En.asrBE C:\projetos\NeverDeadxex\GUIMenu\loadingInitial.guiBE C:\projetos\NeverDeadxex\Chars\MP_Alex.xbox360 C:\projetos\NeverDeadxex\Envs\NeverDead.Xbox360_textures
```

The focused suite passed: **7 tests**. The real-file probe reproduced the
envelope/table values above and walked all 7,325 texture records without
reading their payloads. The original dump and the runtime VFS implementation
were not changed.

## Remaining work and acceptance boundary

1. Decode a small legal XPR2 sample with a verified Xbox 360/Xenos-aware
   implementation; compare its dimensions, format, tiling, and mip layout
   against an independent source before implementing a renderer path.
2. Characterize `LFSR`, `STSA`, `TXTT`, and scene/streaming tags from bounded
   samples. Do not generalize the TXTH or FCSR layout to those tags.
3. Trace the first-scene asset requests and distinguish required misses from
   optional configuration/update probes.

The N4 VFS subtask is satisfied for the observed startup/menu paths;
first-scene resource completeness and asset decoding are unresolved. The
objective next milestone is a validated XPR2-to-host texture conversion on a
bounded sample, not a claim of rendering or gameplay.
