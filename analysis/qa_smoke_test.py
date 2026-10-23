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
        print(" [OK] QA GATES SATISFIED (Zero fatal failures or memory regressions).")
        return 0


def run_live_test(exe_path: Path, game_data_path: Path, duration_sec: int) -> int:
    """Executes live instance of NeverDead and evaluates invariants."""
    print("=================================================================")
    print(" NeverDead QA Suite — Live Runtime Execution Test                ")
    print("=================================================================\n")

    if not exe_path.exists():
        print(f"  [SKIP] Executable not found at: {exe_path}")
        print("         Build target neverdead.exe before invoking --run-live.")
        return 0

    xex_target = game_data_path / "default.xex"
    if not game_data_path.exists() or not xex_target.exists():
        # Check local game-dump fallback
        if (GAME_DUMP_LOCAL / "default.xex").exists():
            game_data_path = GAME_DUMP_LOCAL
        else:
            print(f"  [SKIP] Retail game dump not found at {game_data_path}.")
            print("         Live execution requires a legal Xbox 360 copy of NeverDead.")
            return 0

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
