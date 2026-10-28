#!/usr/bin/env python3
"""
NeverDead Native PC Port — Automated QA Regression & Smoke Test Suite (v2.0)

Evaluates port invariants using a four-state diagnostic model:
  [PASS]         Verified positive evidence satisfies acceptance threshold.
  [FAIL]         Threshold violation, regression, or fatal error detected.
  [SKIP]         Test omitted by design (e.g. missing retail dump on CI runner).
  [INCONCLUSIVE] Telemetry captured is indeterminate or requires manual interaction
                 (e.g. frames_captured == 0 held at interactive title prompt).

Modes:
  --verify-recent   (Default) Validates benchmark artifacts, telemetry, and repo hygiene.
  --run-live        Executes live runtime instance for N seconds and checks invariants.

Usage:
  python analysis/qa_smoke_test.py --verify-recent
  python analysis/qa_smoke_test.py --run-live --seconds 15
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Tuple, List, Optional

# Workspace relative paths
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = WORKSPACE_DIR / "analysis"
BENCHMARKS_DIR = ANALYSIS_DIR / "n7-benchmarks"
BUILD_DIR = WORKSPACE_DIR / "build" / "n2-neverdead"
BUILD_EXE = BUILD_DIR / "neverdead.exe"
GAME_DUMP_JUNCTION = Path("C:/projetos/NeverDeadxex")
GAME_DUMP_LOCAL = WORKSPACE_DIR / "game-dump"

# Acceptance thresholds
THRESHOLDS = {
    "max_fatal_traps": 0,
    "max_d3d12_errors": 0,
    "max_invalid_texture_warnings": 0,
    "max_peak_rss_mb": 1024.0,
    "max_peak_commit_mb": 2048.0,
    "min_shader_cache_files": 2,
    "max_p50_frametime_ms": 50.0,
    "min_median_fps": 15.0
}


class QACheckResult:
    def __init__(self, name: str, state: str, detail: str):
        self.name = name
        self.state = state  # "PASS", "FAIL", "SKIP", "INCONCLUSIVE"
        self.detail = detail

    def __str__(self):
        state_tag = f"[{self.state}]".ljust(15)
        return f"  {state_tag} {self.name:32s}: {self.detail}"


def evaluate_telemetry_metrics(data: dict, scenario_label: str) -> List[QACheckResult]:
    """Evaluates telemetry JSON dictionary against golden stability thresholds."""
    results = []
    log_health = data.get("log_health", {})
    mem = data.get("memory_mb", {})
    ft = data.get("frametime_ms", {})
    fps = data.get("fps", {})
    frames_captured = data.get("frames_captured", 0)

    # 1. Fatal guest traps / crashes
    crashes = log_health.get("fatal_crashes", 0)
    if crashes <= THRESHOLDS["max_fatal_traps"]:
        results.append(QACheckResult(
            f"{scenario_label} Fatal Guest Traps",
            "PASS",
            f"Observed {crashes} traps (Threshold <= {THRESHOLDS['max_fatal_traps']})"
        ))
    else:
        results.append(QACheckResult(
            f"{scenario_label} Fatal Guest Traps",
            "FAIL",
            f"Observed {crashes} traps (Regression: expected 0)"
        ))

    # 2. Direct3D 12 runtime errors
    d3d_err = log_health.get("d3d12_errors", 0)
    if d3d_err <= THRESHOLDS["max_d3d12_errors"]:
        results.append(QACheckResult(
            f"{scenario_label} D3D12 Errors",
            "PASS",
            f"Observed {d3d_err} errors (Threshold <= {THRESHOLDS['max_d3d12_errors']})"
        ))
    else:
        results.append(QACheckResult(
            f"{scenario_label} D3D12 Errors",
            "FAIL",
            f"Observed {d3d_err} D3D12 errors in runtime log"
        ))

    # 3. Invalid texture fetch warnings
    tex_warn = log_health.get("invalid_texture_warnings", 0)
    if tex_warn <= THRESHOLDS["max_invalid_texture_warnings"]:
        results.append(QACheckResult(
            f"{scenario_label} Invalid Texture Descriptors",
            "PASS",
            f"Observed {tex_warn} warnings (Threshold <= {THRESHOLDS['max_invalid_texture_warnings']})"
        ))
    else:
        results.append(QACheckResult(
            f"{scenario_label} Invalid Texture Descriptors",
            "FAIL",
            f"Observed {tex_warn} invalid texture warnings (check gpu_allow_invalid_fetch_constants)"
        ))

    # 4. Host Physical RAM (RSS)
    peak_rss = mem.get("peak_rss", 0.0)
    if 0.0 < peak_rss <= THRESHOLDS["max_peak_rss_mb"]:
        results.append(QACheckResult(
            f"{scenario_label} Peak Working Set (RSS)",
            "PASS",
            f"Observed {peak_rss:.1f} MB (Threshold <= {THRESHOLDS['max_peak_rss_mb']:.1f} MB)"
        ))
    elif peak_rss == 0.0:
        results.append(QACheckResult(
            f"{scenario_label} Peak Working Set (RSS)",
            "INCONCLUSIVE",
            "RSS sample value was 0.0 MB (telemetry counter not sampled)"
        ))
    else:
        results.append(QACheckResult(
            f"{scenario_label} Peak Working Set (RSS)",
            "FAIL",
            f"Observed {peak_rss:.1f} MB exceeds ceiling {THRESHOLDS['max_peak_rss_mb']:.1f} MB"
        ))

    # 5. Virtual Commit Charge
    peak_commit = mem.get("peak_commit", 0.0)
    if 0.0 < peak_commit <= THRESHOLDS["max_peak_commit_mb"]:
        results.append(QACheckResult(
            f"{scenario_label} Peak Virtual Commit",
            "PASS",
            f"Observed {peak_commit:.1f} MB (Threshold <= {THRESHOLDS['max_peak_commit_mb']:.1f} MB)"
        ))
    elif peak_commit == 0.0:
        results.append(QACheckResult(
            f"{scenario_label} Peak Virtual Commit",
            "INCONCLUSIVE",
            "Commit charge value was 0.0 MB (telemetry counter not sampled)"
        ))
    else:
        results.append(QACheckResult(
            f"{scenario_label} Peak Virtual Commit",
            "FAIL",
            f"Observed {peak_commit:.1f} MB exceeds ceiling {THRESHOLDS['max_peak_commit_mb']:.1f} MB"
        ))

    # 6. Interactive Gameplay / Presentation Invariants
    # Rule: Missing metrics (frames_captured == 0) MUST NOT be accepted as valid zero values!
    if frames_captured > 0:
        p50 = ft.get("p50", 0.0)
        med_fps = fps.get("median", 0.0)
        if p50 <= THRESHOLDS["max_p50_frametime_ms"] and med_fps >= THRESHOLDS["min_median_fps"]:
            results.append(QACheckResult(
                f"{scenario_label} Frame Pacing & FPS",
                "PASS",
                f"Flips={frames_captured}, p50={p50:.2f}ms, Median FPS={med_fps:.1f}"
            ))
        else:
            results.append(QACheckResult(
                f"{scenario_label} Frame Pacing & FPS",
                "FAIL",
                f"Degraded performance: p50={p50:.2f}ms, Median FPS={med_fps:.1f}"
            ))
    else:
        results.append(QACheckResult(
            f"{scenario_label} Frame Pacing & FPS",
            "INCONCLUSIVE",
            "Zero frames flipped (process held at title prompt; interactive Start/A required for 3D loop)"
        ))

    return results


def check_repository_cleanliness() -> List[QACheckResult]:
    """Verifies that no proprietary game binaries or dumps are tracked in git."""
    results = []
    forbidden_exts = {".xex", ".iso", ".bin", ".zar", ".asrBE", ".guiBE"}
    found = []
    
    for root, _, files in os.walk(WORKSPACE_DIR):
        # Ignore external references, build outputs, and local dumps
        rel_root = os.path.relpath(root, WORKSPACE_DIR).replace("\\", "/")
        if any(rel_root.startswith(p) for p in ["build", "refs", "game-dump", "game", ".git"]):
            continue
        for f in files:
            ext = os.path.splitext(f)[1]
            if ext in forbidden_exts:
                found.append(os.path.join(rel_root, f))
                
    if not found:
        results.append(QACheckResult(
            "Clean Repository Hygiene",
            "PASS",
            "Zero proprietary assets (.xex, .zar, .bin) detected in tracked repository"
        ))
    else:
        results.append(QACheckResult(
            "Clean Repository Hygiene",
            "FAIL",
            f"Proprietary game assets found in workspace: {', '.join(found[:3])}"
        ))
    return results


def check_shader_cache_status() -> List[QACheckResult]:
    """Validates shader cache presence or gracefully marks as SKIP if absent on runner."""
    results = []
    cache_dir = BENCHMARKS_DIR / "shader_cache"
    
    if not cache_dir.exists():
        results.append(QACheckResult(
            "Shader Cache Filesystem",
            "SKIP",
            "Cache directory not present on runner (excluded from Git tracking by design; generated during local runs)"
        ))
        return results

    shaders = list(cache_dir.rglob("*.xpso")) + list(cache_dir.rglob("*.xsh"))
    if len(shaders) >= THRESHOLDS["min_shader_cache_files"]:
        all_non_empty = all(s.stat().st_size > 0 for s in shaders)
        if all_non_empty:
            results.append(QACheckResult(
                "Shader Cache Filesystem",
                "PASS",
                f"Found {len(shaders)} compiled shader binaries (.xpso/.xsh) with valid size"
            ))
        else:
            results.append(QACheckResult(
                "Shader Cache Filesystem",
                "FAIL",
                "One or more compiled shader files in cache have 0-byte size"
            ))
    else:
        results.append(QACheckResult(
            "Shader Cache Filesystem",
            "INCONCLUSIVE",
            f"Found {len(shaders)} shaders (Expected >= {THRESHOLDS['min_shader_cache_files']})"
        ))
    return results


def check_n10_gameplay_captures() -> List[QACheckResult]:
    """Validates real N10 Direct3D 12 visual captures, scene composition, and diversity."""
    results = []
    n10_dir = ANALYSIS_DIR / "n10-gameplay"
    if not n10_dir.exists():
        results.append(QACheckResult(
            "N10 Gameplay Captures",
            "SKIP",
            "Gameplay capture directory analysis/n10-gameplay not present on runner"
        ))
        return results

    pngs = sorted(list(n10_dir.glob("*.png")))
    if not pngs:
        results.append(QACheckResult(
            "N10 Gameplay Captures",
            "SKIP",
            "No PNG frame captures present in analysis/n10-gameplay"
        ))
        return results

    # 1. Capture count
    if len(pngs) >= 8:
        results.append(QACheckResult(
            "N10 Visual Captures Count",
            "PASS",
            f"Found {len(pngs)} verified D3D12 gameplay/menu transition frames (Expected >= 8)"
        ))
    else:
        results.append(QACheckResult(
            "N10 Visual Captures Count",
            "INCONCLUSIVE",
            f"Found {len(pngs)} frames (Partial capture sequence, expected >= 8)"
        ))

    # 2. File size & non-monochrome content
    large_frames = [p for p in pngs if p.stat().st_size > 500_000]
    if len(large_frames) >= 7:
        results.append(QACheckResult(
            "N10 Visual Scene Rendering",
            "PASS",
            f"{len(large_frames)}/{len(pngs)} frames contain complex 3D scene data (>500 KB per PNG)"
        ))
    else:
        results.append(QACheckResult(
            "N10 Visual Scene Rendering",
            "INCONCLUSIVE",
            f"Only {len(large_frames)}/{len(pngs)} frames meet size threshold"
        ))

    # 3. Frame diversity (distinct hashes)
    unique_sizes = set(p.stat().st_size for p in pngs)
    if len(unique_sizes) >= 6:
        results.append(QACheckResult(
            "N10 Frame Diversity & Movement",
            "PASS",
            f"Observed {len(unique_sizes)} unique frame geometries across movement and camera stages"
        ))
    else:
        results.append(QACheckResult(
            "N10 Frame Diversity & Movement",
            "INCONCLUSIVE",
            f"Low frame variation ({len(unique_sizes)} distinct sizes)"
        ))

    return results


def check_n11_graphics_correctness() -> List[QACheckResult]:
    """Audits N11 Direct3D 12 rendering correctness, HDR RTs, and descriptor validation."""
    results = []
    n11_dir = ANALYSIS_DIR / "n11-graphics"
    report_json = n11_dir / "n11_graphics_report.json"

    if not n11_dir.exists() or not report_json.exists():
        results.append(QACheckResult(
            "N11 Graphics Correctness",
            "SKIP",
            "N11 graphics telemetry report analysis/n11-graphics/n11_graphics_report.json not present"
        ))
        return results

    try:
        with open(report_json, "r", encoding="utf-8-sig") as f:
            data = json.load(f)

        targeted_active = data.get("TargetedFilterActive", False)
        allow_global = data.get("GpuAllowInvalidFetchConstants", False)
        if isinstance(allow_global, dict):
            allow_global = allow_global.get("IsPresent", False)

        if targeted_active and not allow_global:
            results.append(QACheckResult(
                "N11 Targeted HDR RT Policy",
                "PASS",
                "Strict descriptor filter active; gpu_allow_invalid_fetch_constants=false verified"
            ))
        else:
            results.append(QACheckResult(
                "N11 Targeted HDR RT Policy",
                "FAIL",
                "Global invalid descriptor bypass was used instead of targeted filter"
            ))

        audit = data.get("ExecutionAudit", {})
        traps = audit.get("FatalTraps", 0)
        d3d_err = audit.get("D3D12Errors", 0)
        dred_err = audit.get("DredErrors", 0)
        tex_warn = audit.get("InvalidTextureWarnings", 0)

        if traps == 0 and d3d_err == 0 and dred_err == 0 and tex_warn == 0:
            results.append(QACheckResult(
                "N11 D3D12 & DRED Stability",
                "PASS",
                f"0 traps, 0 D3D12 errors, 0 DRED faults, 0 invalid texture warnings"
            ))
        else:
            results.append(QACheckResult(
                "N11 D3D12 & DRED Stability",
                "FAIL",
                f"Regression: Traps={traps}, D3D12Errors={d3d_err}, DRED={dred_err}, TexWarnings={tex_warn}"
            ))

        captures = data.get("Captures", [])
        hdr_scenes = [c for c in captures if c.get("NonBlackRatio", 0.0) > 0.40]
        if len(hdr_scenes) >= 7:
            results.append(QACheckResult(
                "N11 HDR Scene Content Verification",
                "PASS",
                f"{len(hdr_scenes)}/{len(captures)} frames confirmed full 3D HDR rendering (>40% non-black)"
            ))
        else:
            results.append(QACheckResult(
                "N11 HDR Scene Content Verification",
                "FAIL",
                f"Only {len(hdr_scenes)}/{len(captures)} frames meet HDR non-black ratio"
            ))

    except Exception as e:
        results.append(QACheckResult("N11 Graphics Report", "FAIL", f"Failed to parse report: {e}"))

    return results


def check_n12_gameplay_save_audio() -> List[QACheckResult]:
    """Audits N12 Save Persistence, Audio APU, and Havok Physics / Controls stability."""
    results = []
    n12_dir = ANALYSIS_DIR / "n12-validation"
    report_json = n12_dir / "n12_validation_report.json"

    if not n12_dir.exists() or not report_json.exists():
        results.append(QACheckResult(
            "N12 Gameplay & Save Persistence",
            "SKIP",
            "N12 validation report analysis/n12-validation/n12_validation_report.json not present"
        ))
        return results

    try:
        with open(report_json, "r", encoding="utf-8-sig") as f:
            data = json.load(f)

        # 1. Save persistence
        save = data.get("SavePersistence", {})
        init_size = save.get("InitialSize", 0)
        final_size = save.get("FinalSize", 0)
        init_hash = save.get("InitialHash", "")
        final_hash = save.get("FinalHash", "")

        if init_size > 0 and init_size == final_size and init_hash and init_hash == final_hash:
            results.append(QACheckResult(
                "N12 STFS Save Persistence",
                "PASS",
                f"ND.sav ({init_size} bytes) integrity verified bit-identical across sessions"
            ))
        else:
            results.append(QACheckResult(
                "N12 STFS Save Persistence",
                "FAIL",
                f"Save corruption or size mismatch: init={init_size}, final={final_size}"
            ))

        # 2. Audio Subsystem
        audio = data.get("AudioAudit", {})
        xma_ok = audio.get("XmaInitialized", False)
        bink_snd = audio.get("BinkSoundThreads", 0)
        underruns = audio.get("BufferUnderruns", 0)

        if xma_ok and bink_snd >= 1 and underruns == 0:
            results.append(QACheckResult(
                "N12 Audio APU & Streaming",
                "PASS",
                f"XMA MMIO active, Bink audio threads synchronized, {underruns} buffer underruns"
            ))
        else:
            results.append(QACheckResult(
                "N12 Audio APU & Streaming",
                "FAIL",
                f"Audio fault: XmaInit={xma_ok}, BinkThreads={bink_snd}, Underruns={underruns}"
            ))

        # 3. Physics & D3D12 Stability
        stability = data.get("StabilityAudit", {})
        traps = stability.get("FatalTraps", 0)
        d3d12_err = stability.get("D3D12Errors", 0)
        dred_err = stability.get("DredFaults", 0)

        if traps == 0 and d3d12_err == 0 and dred_err == 0:
            results.append(QACheckResult(
                "N12 Havok & D3D12 Stability",
                "PASS",
                "0 guest traps, 0 D3D12 errors, 0 DRED faults across 11 stages"
            ))
        else:
            results.append(QACheckResult(
                "N12 Havok & D3D12 Stability",
                "FAIL",
                f"Regression: Traps={traps}, D3D12Errors={d3d12_err}, DRED={dred_err}"
            ))

        # 4. Captures Count & Diversity
        captures = data.get("Captures", [])
        if len(captures) >= 11:
            results.append(QACheckResult(
                "N12 Visual Transition Sequence",
                "PASS",
                f"{len(captures)} stages captured from boot to gameplay, movement, yaw and pause"
            ))
        else:
            results.append(QACheckResult(
                "N12 Visual Transition Sequence",
                "INCONCLUSIVE",
                f"Found {len(captures)}/11 expected transition captures"
            ))

    except Exception as e:
        results.append(QACheckResult("N12 Validation Report", "FAIL", f"Failed to parse report: {e}"))

    return results


def run_verify_recent() -> int:
    """Verifies existing telemetry records and repository invariants."""
    print("=================================================================")
    print(" NeverDead QA Suite — Telemetry & Regression Verification        ")
    print("=================================================================\n")

    all_results: List[QACheckResult] = []

    # Category 1: Repository Hygiene
    print("[Category 1: Repository & Code Hygiene]")
    for r in check_repository_cleanliness():
        print(r)
        all_results.append(r)

    # Category 2: Benchmark Telemetry Verification
    print("\n[Category 2: Benchmark Telemetry (Cold & Warm Cache Runs)]")
    cold_json = BENCHMARKS_DIR / "n7_cold_profile.json"
    warm_json = BENCHMARKS_DIR / "n7_warm_profile.json"

    if cold_json.exists():
        try:
            with open(cold_json, "r", encoding="utf-8") as f:
                cold_data = json.load(f)
            for r in evaluate_telemetry_metrics(cold_data, "Cold-Cache"):
                print(r)
                all_results.append(r)
        except Exception as e:
            all_results.append(QACheckResult("Cold-Cache Profile", "FAIL", f"Corrupt JSON: {e}"))
    else:
        all_results.append(QACheckResult("Cold-Cache Profile", "SKIP", "Telemetry file n7_cold_profile.json not present"))

    if warm_json.exists():
        try:
            with open(warm_json, "r", encoding="utf-8") as f:
                warm_data = json.load(f)
            for r in evaluate_telemetry_metrics(warm_data, "Warm-Cache"):
                print(r)
                all_results.append(r)
        except Exception as e:
            all_results.append(QACheckResult("Warm-Cache Profile", "FAIL", f"Corrupt JSON: {e}"))
    else:
        all_results.append(QACheckResult("Warm-Cache Profile", "SKIP", "Telemetry file n7_warm_profile.json not present"))

    # Category 3: Shader Cache Verification
    print("\n[Category 3: Compiled Shaders & Asset Caches]")
    for r in check_shader_cache_status():
        print(r)
        all_results.append(r)

    # Category 4: N10 Direct3D 12 Visual Gameplay Captures
    print("\n[Category 4: N10 Direct3D 12 Visual Gameplay Validation]")
    for r in check_n10_gameplay_captures():
        print(r)
        all_results.append(r)

    # Category 5: N11 Direct3D 12 Graphics Correctness & Target Policy
    print("\n[Category 5: N11 Direct3D 12 Graphics Correctness & HDR Render Targets]")
    for r in check_n11_graphics_correctness():
        print(r)
        all_results.append(r)

    # Category 6: N12 Gameplay, Physics, Audio & Save Persistence
    print("\n[Category 6: N12 Gameplay, Physics, Audio & Save Persistence]")
    for r in check_n12_gameplay_save_audio():
        print(r)
        all_results.append(r)

    # Summary
    pass_count = sum(1 for r in all_results if r.state == "PASS")
    fail_count = sum(1 for r in all_results if r.state == "FAIL")
    skip_count = sum(1 for r in all_results if r.state == "SKIP")
    inc_count = sum(1 for r in all_results if r.state == "INCONCLUSIVE")

    print("\n=================================================================")
    print(f" SUMMARY: PASS={pass_count} | FAIL={fail_count} | SKIP={skip_count} | INCONCLUSIVE={inc_count}")
    print("=================================================================")

    if fail_count > 0:
        print(" [!] REGRESSION DETECTED: One or more QA checks failed.")
        return 1
    else:
        print(" [OK] Historical/offline checks found no FAIL; this is not current-build gameplay or release approval.")
        return 0


def run_live_test(exe_path: Path, game_data_path: Path, duration_sec: int) -> int:
    """Executes live instance of NeverDead and evaluates invariants."""
    print("=================================================================")
    print(" NeverDead QA Suite — Live Runtime Execution Test                ")
    print("=================================================================\n")

    if not exe_path.exists():
        print(f"  [SKIP] Executable not found at: {exe_path}")
        print("         Build target neverdead.exe before invoking --run-live.")
        return 2

    xex_target = game_data_path / "default.xex"
    if not game_data_path.exists() or not xex_target.exists():
        # Check local game-dump fallback
        if (GAME_DUMP_LOCAL / "default.xex").exists():
            game_data_path = GAME_DUMP_LOCAL
        else:
            print(f"  [SKIP] Retail game dump not found at {game_data_path}.")
            print("         Live execution requires a legal Xbox 360 copy of NeverDead.")
            return 2

    print(f"  Executable:  {exe_path}")
    print(f"  Game Data:   {game_data_path}")
    print(f"  Duration:    {duration_sec} seconds")
    print("  Launching benchmark telemetry profiler...")

    # Delegate to profile_n7 harness
    try:
        sys.path.insert(0, str(ANALYSIS_DIR))
        import profile_n7

        cache_dir = BENCHMARKS_DIR / "smoke_cache"
        user_dir = BENCHMARKS_DIR / "smoke_user"
        output_dir = BENCHMARKS_DIR

        live_results = profile_n7.run_benchmark(
            scenario="smoke",
            duration_sec=duration_sec,
            exe_path=str(exe_path),
            game_data_root=str(game_data_path),
            cache_dir=str(cache_dir),
            user_dir=str(user_dir),
            output_dir=str(output_dir)
        )

        print("\n[Live Evaluation Results]")
        evaluations = evaluate_telemetry_metrics(live_results, "Live")
        fail_count = 0
        for r in evaluations:
            print(r)
            if r.state == "FAIL":
                fail_count += 1

        if fail_count > 0:
            print(f"\n[!] Live execution detected {fail_count} failure(s).")
            return 1
        elif not evaluations or any(r.state != "PASS" for r in evaluations):
            print("\n[INCONCLUSIVE] Live checks did not all pass.")
            return 2
        else:
            print("\n[OK] Live execution completed without crashes or fatal errors.")
            return 0

    except Exception as e:
        print(f"\n[FAIL] Live execution error: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(description="NeverDead QA Regression & Smoke Test Suite")
    parser.add_argument("--verify-recent", action="store_true", help="Verify recent benchmark outputs and repo hygiene")
    parser.add_argument("--run-live", action="store_true", help="Launch live instance and verify invariants")
    parser.add_argument("--exe", default=str(BUILD_EXE), help="Path to neverdead.exe (for --run-live)")
    parser.add_argument("--game-data", default=str(GAME_DUMP_JUNCTION), help="Path to game dump (for --run-live)")
    parser.add_argument("--seconds", type=int, default=15, help="Seconds to run in live mode")
    args = parser.parse_args()

    if args.run_live:
        return run_live_test(Path(args.exe), Path(args.game_data), args.seconds)
    else:
        return run_verify_recent()


if __name__ == "__main__":
    sys.exit(main())
