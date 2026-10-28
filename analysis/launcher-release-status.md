# Launcher alpha delivery status

Updated: 2026-10-28

The launcher and packaging integration are implemented. Windows PowerShell
folder/argument tests and all 24 profiler unit tests pass locally. CI now runs
the launcher tests without game assets. Offscreen layout inspection confirms
button and label placement, but is not interactive UI acceptance.

## Local package rehearsal

Archive: `build/launcher-package-check-20261028-000149/neverdead-launcher-candidate.zip`

SHA-256: `6D03DF463C4FBE8E572919027D1BD57FE03AE35A3D118F4C5BF25AC3C6015840`

`validate_release_zip.ps1` passed: exactly seven allowed files, nonempty entries,
binary MZ headers, N15 evidence strings, ROV and safe fetch configuration.
Files: `Play.cmd`, `launcher.ps1`, `README.md`, `neverdead.toml`,
`neverdead.exe`, `rexruntime.dll`, `rexgpu-xenos.dll`. No commercial assets,
saves, cache or local logs are included.

This rehearsal copies the existing October 27 binaries and current launcher;
it is not a fresh final build, code-signing validation, or runtime certification.
Do not publish this candidate as the accepted release.

## Remaining acceptance

- Interactive launcher selection, launch, and saves/logs buttons.
- Real launch from a path containing spaces with the packaged binaries.
- Pause/resume confirmation, 30-minute stability run, and exact-save Continue.
- Final build/package provenance, ZIP validation and checksum publication.
- GitHub prerelease with installation instructions and RTV limitations.

Interactive work is awaiting availability of the laptop; the user requested
work that does not interfere with active use. No interactive test is armed.
N15 remains incomplete and ROV remains the default.
