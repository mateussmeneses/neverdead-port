"""
NeverDead PC Port — N13: Real Gameplay Performance & Telemetry Profiler

Measures real 3D gameplay performance in Direct3D 12:
- Transitions through boot -> save load -> campaign -> prologue skip -> 3D gameplay
- Samples real interactive gameplay with active player movement, camera yaw, physics roll
- Captures per-frame hardware counters from ReXGlue SDK:
    * Host frametimes (mean, P50, P95, P99, max, spikes)
    * Host FPS (median, min, 1% low)
    * D3D12 Draw calls and vertices processed
    * Pipeline and Texture cache hit rates
    * PPC functions dispatched and interrupt dispatches
    * Audio XMA frames, latency, buffer queue depth
    * Host memory (RSS, Private Commit) and multi-core CPU utilization
"""

import argparse
import csv
import ctypes
from ctypes import wintypes
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Win32 Structures
class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [
        ('cb', wintypes.DWORD),
        ('PageFaultCount', wintypes.DWORD),
        ('PeakWorkingSetSize', ctypes.c_size_t),
        ('WorkingSetSize', ctypes.c_size_t),
        ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
        ('QuotaPagedPoolUsage', ctypes.c_size_t),
        ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
        ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
        ('PagefileUsage', ctypes.c_size_t),
        ('PeakPagefileUsage', ctypes.c_size_t),
        ('PrivateUsage', ctypes.c_size_t),
    ]

class FILETIME(ctypes.Structure):
    _fields_ = [('dwLowDateTime', wintypes.DWORD), ('dwHighDateTime', wintypes.DWORD)]

def filetime_to_int(ft):
    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

def get_process_memory(handle):
    counters = PROCESS_MEMORY_COUNTERS_EX()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
    psapi = ctypes.windll.psapi
    if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        return {
            'rss_mb': counters.WorkingSetSize / (1024 * 1024),
            'peak_rss_mb': counters.PeakWorkingSetSize / (1024 * 1024),
            'commit_mb': counters.PagefileUsage / (1024 * 1024),
            'peak_commit_mb': counters.PeakPagefileUsage / (1024 * 1024),
        }
    return None

def get_dir_size_and_count(path):
    if not os.path.exists(path):
        return 0, 0
    total_bytes = 0
    count = 0
    for root, _, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            total_bytes += os.path.getsize(fp)
            count += 1
    return count, total_bytes

def calculate_percentile(sorted_list, p):
    if not sorted_list:
        return 0.0
    idx = (len(sorted_list) - 1) * p / 100.0
    floor_idx = int(idx)
    ceil_idx = min(floor_idx + 1, len(sorted_list) - 1)
    weight = idx - floor_idx
    return sorted_list[floor_idx] * (1.0 - weight) + sorted_list[ceil_idx] * weight

# Win32 Window & Input Helpers
user32 = ctypes.windll.user32
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_RETURN = 0x0D
VK_SPACE = 0x20
VK_UP = 0x26
VK_DOWN = 0x28
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_W = 0x57
VK_A = 0x41
VK_S = 0x53
VK_D = 0x44
VK_X = 0x58

def find_window_for_pid(pid):
    hwnds = []
    def enum_cb(hwnd, lparam):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid and user32.IsWindowVisible(hwnd):
            hwnds.append(hwnd)
        return True
    
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return hwnds[0] if hwnds else None

def tap_key(hwnd, vk):
    scan = user32.MapVirtualKeyW(vk, 0)
    extended = 1 if (37 <= vk <= 40) else 0
    l_down = 1 | (scan << 16) | (extended << 24)
    l_up = 1 | (scan << 16) | (extended << 24) | (1 << 30) | (1 << 31)
    if hwnd:
        user32.PostMessageW(hwnd, WM_KEYDOWN, vk, l_down)
    time.sleep(0.08)
    if hwnd:
        user32.PostMessageW(hwnd, WM_KEYUP, vk, l_up)
    time.sleep(0.05)

def hold_key(hwnd, vk, duration_sec):
    scan = user32.MapVirtualKeyW(vk, 0)
    extended = 1 if (37 <= vk <= 40) else 0
    l_down = 1 | (scan << 16) | (extended << 24)
    l_up = 1 | (scan << 16) | (extended << 24) | (1 << 30) | (1 << 31)
    if hwnd:
        user32.PostMessageW(hwnd, WM_KEYDOWN, vk, l_down)
    time.sleep(duration_sec)
    if hwnd:
        user32.PostMessageW(hwnd, WM_KEYUP, vk, l_up)
    time.sleep(0.05)

def run_gameplay_benchmark(scenario, gameplay_duration_sec, exe_path, game_data_root, cache_dir, user_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    run_user_dir = os.path.join(user_dir, f"{scenario}-{int(time.time())}")
    os.makedirs(run_user_dir, exist_ok=True)

    if scenario == "cold":
        print(f"[{scenario.upper()}] Resetting shader cache directory: {cache_dir}")
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir, ignore_errors=True)
        os.makedirs(cache_dir, exist_ok=True)
    else:
        print(f"[{scenario.upper()}] Reusing existing shader cache directory: {cache_dir}")
        os.makedirs(cache_dir, exist_ok=True)

    initial_cache_files, initial_cache_bytes = get_dir_size_and_count(cache_dir)
    print(f"[{scenario.upper()}] Initial cache state: {initial_cache_files} files, {initial_cache_bytes / 1024:.1f} KB")

    perf_csv_path = os.path.join(output_dir, f"n13_{scenario}_perf_frames.csv")
    runtime_log_path = os.path.join(output_dir, f"n13_{scenario}_runtime.log")

    if os.path.exists(perf_csv_path):
        os.remove(perf_csv_path)

    cmd = [
        exe_path,
        f"--game_data_root={game_data_root}",
        f"--user_data_root={run_user_dir}",
        f"--cache_root={cache_dir}",
        "--mnk_mode=true",
        "--input_background=true",
        "--gpu_allow_invalid_fetch_constants=false",
        "--render_target_path_d3d12=rov",
        f"--perf_log_csv={perf_csv_path}",
        "--log_level=debug",
        f"--log_file={runtime_log_path}"
    ]

    capture_trigger = Path(exe_path).parent / "capture_trigger.txt"
    capture_trigger.unlink(missing_ok=True)
    runtime_env = os.environ.copy()
    runtime_env["NEVERDEAD_CAPTURE_DIR"] = output_dir

    print(f"[{scenario.upper()}] Launching NeverDead runtime...")
    proc = subprocess.Popen(cmd, cwd=os.path.dirname(exe_path), env=runtime_env)
    h_proc = wintypes.HANDLE(ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0400, False, proc.pid))

    rss_samples = []
    commit_samples = []
    cpu_samples = []
    kernel32 = ctypes.windll.kernel32
    creation_time = FILETIME()
    exit_time = FILETIME()
    kernel_time_prev = FILETIME()
    user_time_prev = FILETIME()
    time_prev = time.time()

    if h_proc:
        kernel32.GetProcessTimes(h_proc, ctypes.byref(creation_time), ctypes.byref(exit_time),
                                 ctypes.byref(kernel_time_prev), ctypes.byref(user_time_prev))

    # Wait for window
    hwnd = None
    win_deadline = time.time() + 15
    while time.time() < win_deadline and proc.poll() is None:
        hwnd = find_window_for_pid(proc.pid)
        if hwnd:
            break
        time.sleep(0.2)

    if hwnd:
        print(f"[{scenario.upper()}] Window acquired: 0x{hwnd:X}")
        user32.SetForegroundWindow(hwnd)

    print(f"[{scenario.upper()}] Stage 1: Waiting 55s for intro & title screen...")
    for _ in range(550):
        if proc.poll() is not None:
            break
        if h_proc:
            mem = get_process_memory(h_proc)
            if mem:
                rss_samples.append(mem['rss_mb'])
                commit_samples.append(mem['commit_mb'])
        time.sleep(0.1)

    if proc.poll() is not None:
        print(f"[{scenario.upper()}] Process terminated prematurely at title boot!")
        return None

    # Fresh profile route: title -> gamma -> autosave -> main menu -> difficulty -> prologue.
    print(f"[{scenario.upper()}] Stage 2: Tapping START (Return / X) to enter setup...")
    tap_key(hwnd, VK_RETURN)
    time.sleep(0.5)
    tap_key(hwnd, VK_X)
    time.sleep(3.0)

    print(f"[{scenario.upper()}] Stage 3: Accepting gamma and autosave notice...")
    tap_key(hwnd, VK_SPACE)
    time.sleep(2.0)
    tap_key(hwnd, VK_SPACE)
    time.sleep(2.0)

    print(f"[{scenario.upper()}] Stage 4: Selecting Single Player and difficulty...")
    tap_key(hwnd, VK_SPACE)
    time.sleep(2.0)
    tap_key(hwnd, VK_SPACE)
    time.sleep(2.0)
    tap_key(hwnd, VK_SPACE)
    time.sleep(6.0)

    print(f"[{scenario.upper()}] Stage 5: Skipping Prologue cutscenes (START)...")
    for _ in range(5):
        tap_key(hwnd, VK_RETURN)
        time.sleep(3.0)
    tap_key(hwnd, VK_SPACE)  # Resume if the final START paused gameplay.
    time.sleep(10.0)

    capture_trigger.write_text(f"n13-{scenario}-gameplay", encoding="ascii")
    time.sleep(2.0)
    print(f"[{scenario.upper()}] Stage 6: >>> 3D GAMEPLAY ACTIVE <<< Sampling {gameplay_duration_sec}s of real gameplay...")
    
    # Active gameplay interaction loop
    gameplay_start = time.time()
    gameplay_end = gameplay_start + gameplay_duration_sec
    cycle_counter = 0

    while time.time() < gameplay_end:
        if proc.poll() is not None:
            print(f"[{scenario.upper()}] Process exited during gameplay (code {proc.returncode})!")
            break

        # Sample memory & CPU
        if h_proc:
            mem = get_process_memory(h_proc)
            if mem:
                rss_samples.append(mem['rss_mb'])
                commit_samples.append(mem['commit_mb'])

            kt = FILETIME()
            ut = FILETIME()
            if kernel32.GetProcessTimes(h_proc, ctypes.byref(creation_time), ctypes.byref(exit_time),
                                        ctypes.byref(kt), ctypes.byref(ut)):
                now = time.time()
                dt = now - time_prev
                if dt > 0.5:
                    d_kernel = (filetime_to_int(kt) - filetime_to_int(kernel_time_prev)) / 10000000.0
                    d_user = (filetime_to_int(ut) - filetime_to_int(user_time_prev)) / 10000000.0
                    cpu_percent = ((d_kernel + d_user) / dt) * 100.0
                    cpu_samples.append(cpu_percent)
                    kernel_time_prev = kt
                    user_time_prev = ut
                    time_prev = now

        # Active player inputs to exercise Havok collision, character ragdoll, and D3D12 view frustum
        mod_idx = cycle_counter % 5
        if mod_idx == 0:
            hold_key(hwnd, VK_W, 1.2)  # Walk forward into environment
        elif mod_idx == 1:
            hold_key(hwnd, VK_D, 0.6)  # Turn camera / yaw
        elif mod_idx == 2:
            tap_key(hwnd, VK_SPACE)    # Dodge roll / jump (triggers physics)
            time.sleep(0.5)
        elif mod_idx == 3:
            hold_key(hwnd, VK_A, 0.8)  # Strafe left
        elif mod_idx == 4:
            hold_key(hwnd, VK_S, 0.8)  # Step back

        cycle_counter += 1
        time.sleep(0.1)

    print(f"[{scenario.upper()}] Gameplay sampling finished. Terminating process...")
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    if h_proc:
        kernel32.CloseHandle(h_proc)

    final_cache_files, final_cache_bytes = get_dir_size_and_count(cache_dir)
    new_cache_files = final_cache_files - initial_cache_files
    new_cache_bytes = final_cache_bytes - initial_cache_bytes

    # Parse per-frame CSV
    frame_times_ms = []
    fps_values = []
    draw_calls = []
    vertices = []
    stalls = []
    tex_hits = []
    tex_misses = []
    pipe_hits = []
    pipe_misses = []
    funcs_dispatched = []
    interrupt_dispatches = []
    active_threads = []
    crit_contentions = []
    xma_frames = []

    if os.path.exists(perf_csv_path) and os.path.getsize(perf_csv_path) > 0:
        with open(perf_csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ft_us = float(row.get('frame_time_us', 0))
                    if ft_us > 0:
                        frame_times_ms.append(ft_us / 1000.0)
                    fps = float(row.get('fps', 0))
                    if fps > 0:
                        fps_values.append(fps)
                    draw_calls.append(int(row.get('draw_calls', 0)))
                    vertices.append(int(row.get('vertices_processed', 0)))
                    stalls.append(int(row.get('command_buffer_stalls', 0)))
                    tex_hits.append(int(row.get('texture_cache_hits', 0)))
                    tex_misses.append(int(row.get('texture_cache_misses', 0)))
                    pipe_hits.append(int(row.get('pipeline_cache_hits', 0)))
                    pipe_misses.append(int(row.get('pipeline_cache_misses', 0)))
                    funcs_dispatched.append(int(row.get('functions_dispatched', 0)))
                    interrupt_dispatches.append(int(row.get('interrupt_dispatches', 0)))
                    active_threads.append(int(row.get('active_threads', 0)))
                    crit_contentions.append(int(row.get('critical_region_contentions', 0)))
                    xma_frames.append(int(row.get('xma_frames_decoded', 0)))
                except (ValueError, KeyError):
                    continue

    sorted_fts = sorted(frame_times_ms)
    sorted_fps = sorted(fps_values)

    total_frames = len(frame_times_ms)
    p50_ft = calculate_percentile(sorted_fts, 50)
    p95_ft = calculate_percentile(sorted_fts, 95)
    p99_ft = calculate_percentile(sorted_fts, 99)
    median_fps = calculate_percentile(sorted_fps, 50)
    min_fps = sorted_fps[0] if sorted_fps else 0.0
    p1_low_fps = calculate_percentile(sorted_fps, 1)

    # Frame spikes (stutters)
    stutter_33ms = sum(1 for ft in frame_times_ms if ft > 33.33)
    stutter_50ms = sum(1 for ft in frame_times_ms if ft > 50.0)
    stutter_100ms = sum(1 for ft in frame_times_ms if ft > 100.0)

    # Memory summary
    peak_rss = max(rss_samples) if rss_samples else 0.0
    avg_rss = sum(rss_samples) / len(rss_samples) if rss_samples else 0.0
    peak_commit = max(commit_samples) if commit_samples else 0.0
    avg_cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0.0
    peak_cpu = max(cpu_samples) if cpu_samples else 0.0

    # Cache hit rates
    total_tex_lookups = sum(tex_hits) + sum(tex_misses)
    tex_hit_rate = (sum(tex_hits) / total_tex_lookups * 100.0) if total_tex_lookups > 0 else 0.0
    total_pipe_lookups = sum(pipe_hits) + sum(pipe_misses)
    pipe_hit_rate = (sum(pipe_hits) / total_pipe_lookups * 100.0) if total_pipe_lookups > 0 else 0.0

    # Log health check
    d3d12_errors = 0
    d3d12_warnings = 0
    fatal_errors = 0
    invalid_tex_warnings = 0
    pipeline_creations = 0

    if os.path.exists(runtime_log_path):
        with open(runtime_log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if '[critical]' in line or '[FATAL]' in line:
                    fatal_errors += 1
                if '[gpu]' in line and '[error]' in line:
                    d3d12_errors += 1
                if '[gpu]' in line and '[warning]' in line:
                    d3d12_warnings += 1
                if 'Texture fetch constant' in line and 'invalid' in line:
                    invalid_tex_warnings += 1
                if 'Creating graphics pipeline' in line:
                    pipeline_creations += 1

    results = {
        'scenario': scenario,
        'frames_captured': total_frames,
        'frametime_ms': {
            'mean': (sum(frame_times_ms) / total_frames) if total_frames > 0 else 0.0,
            'p50': p50_ft,
            'p95': p95_ft,
            'p99': p99_ft,
            'max': sorted_fts[-1] if sorted_fts else 0.0,
            'stutters_gt_33ms': stutter_33ms,
            'stutters_gt_50ms': stutter_50ms,
            'stutters_gt_100ms': stutter_100ms,
        },
        'fps': {
            'median': median_fps,
            'min': min_fps,
            'p1_low': p1_low_fps,
        },
        'memory_mb': {
            'peak_rss': peak_rss,
            'avg_rss': avg_rss,
            'peak_commit': peak_commit,
        },
        'cpu': {
            'avg_percent': avg_cpu,
            'peak_percent': peak_cpu,
        },
        'gpu_and_caches': {
            'total_draw_calls': sum(draw_calls),
            'total_vertices': sum(vertices),
            'command_buffer_stalls': sum(stalls),
            'texture_cache_hit_rate_pct': tex_hit_rate,
            'pipeline_cache_hit_rate_pct': pipe_hit_rate,
            'pipeline_creations_logged': pipeline_creations,
            'shader_cache_files_start': initial_cache_files,
            'shader_cache_files_end': final_cache_files,
            'shader_cache_files_new': new_cache_files,
            'shader_cache_bytes_new': new_cache_bytes,
        },
        'ppc_and_system': {
            'total_functions_dispatched': sum(funcs_dispatched),
            'total_interrupt_dispatches': sum(interrupt_dispatches),
            'max_active_threads': max(active_threads) if active_threads else 0,
            'max_critical_contentions': max(crit_contentions) if crit_contentions else 0,
            'total_xma_frames': sum(xma_frames)
        },
        'log_health': {
            'fatal_crashes': fatal_errors,
            'd3d12_errors': d3d12_errors,
            'd3d12_warnings': d3d12_warnings,
            'invalid_texture_warnings': invalid_tex_warnings,
        }
    }

    json_out = os.path.join(output_dir, f"n13_{scenario}_profile.json")
    with open(json_out, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    print(f"[{scenario.upper()}] Results saved to: {json_out}")
    print(f"  Frames Captured: {total_frames} | Median FPS: {median_fps:.1f} | Min FPS: {min_fps:.1f} | 1% Low: {p1_low_fps:.1f}")
    print(f"  Frametime (ms): Mean: {results['frametime_ms']['mean']:.2f} | p50: {p50_ft:.2f} | p95: {p95_ft:.2f} | p99: {p99_ft:.2f} | Max: {results['frametime_ms']['max']:.2f}")
    print(f"  Stutters: >33ms: {stutter_33ms} | >50ms: {stutter_50ms} | >100ms: {stutter_100ms}")
    print(f"  Memory: Peak RSS: {peak_rss:.1f} MB | Peak Commit: {peak_commit:.1f} MB | CPU Avg: {avg_cpu:.1f}% (Peak {peak_cpu:.1f}%)")
    print(f"  D3D12: Draw Calls: {sum(draw_calls)} | Vertices: {sum(vertices)} | Stalls: {sum(stalls)} | Pipeline Hits: {pipe_hit_rate:.1f}%")

    return results

def main():
    parser = argparse.ArgumentParser(description="NeverDead N13 Real Gameplay Performance Benchmark")
    parser.add_argument("--scenario", choices=["cold", "warm", "both"], default="both")
    parser.add_argument("--duration", type=int, default=30, help="Interactive gameplay sampling duration in seconds")
    parser.add_argument("--exe", default=r"C:\projetos\neverdead\build\n2-neverdead\neverdead.exe")
    parser.add_argument("--game-data", default=r"C:\projetos\NeverDeadxex")
    parser.add_argument("--output-dir", default=r"C:\projetos\neverdead\analysis\n13-benchmarks")
    parser.add_argument("--user-dir", default=r"C:\projetos\neverdead\analysis\n13-benchmarks\user_data")
    args = parser.parse_args()

    cache_dir = os.path.join(args.output_dir, "shader_cache")

    cold_res = None
    warm_res = None

    if args.scenario in ["cold", "both"]:
        cold_res = run_gameplay_benchmark("cold", args.duration, args.exe, args.game_data, cache_dir, args.user_dir, args.output_dir)

    if args.scenario in ["warm", "both"]:
        warm_res = run_gameplay_benchmark("warm", args.duration, args.exe, args.game_data, cache_dir, args.user_dir, args.output_dir)

    # Generate comparison CSV if both ran
    if cold_res and warm_res:
        comp_csv = os.path.join(args.output_dir, "n13_benchmark_comparison.csv")
        with open(comp_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Metric", "Cold Cache", "Warm Cache", "Delta", "Unit"])
            
            def add_row(metric, cold_val, warm_val, unit=""):
                delta = warm_val - cold_val
                writer.writerow([metric, f"{cold_val:.2f}", f"{warm_val:.2f}", f"{delta:+.2f}", unit])

            add_row("Frames Captured", cold_res['frames_captured'], warm_res['frames_captured'], "frames")
            add_row("Median FPS", cold_res['fps']['median'], warm_res['fps']['median'], "fps")
            add_row("Min FPS", cold_res['fps']['min'], warm_res['fps']['min'], "fps")
            add_row("1% Low FPS", cold_res['fps']['p1_low'], warm_res['fps']['p1_low'], "fps")
            add_row("Mean Frametime", cold_res['frametime_ms']['mean'], warm_res['frametime_ms']['mean'], "ms")
            add_row("P50 Frametime", cold_res['frametime_ms']['p50'], warm_res['frametime_ms']['p50'], "ms")
            add_row("P95 Frametime", cold_res['frametime_ms']['p95'], warm_res['frametime_ms']['p95'], "ms")
            add_row("P99 Frametime", cold_res['frametime_ms']['p99'], warm_res['frametime_ms']['p99'], "ms")
            add_row("Max Frametime", cold_res['frametime_ms']['max'], warm_res['frametime_ms']['max'], "ms")
            add_row("Stutters >33ms", cold_res['frametime_ms']['stutters_gt_33ms'], warm_res['frametime_ms']['stutters_gt_33ms'], "count")
            add_row("Stutters >50ms", cold_res['frametime_ms']['stutters_gt_50ms'], warm_res['frametime_ms']['stutters_gt_50ms'], "count")
            add_row("Stutters >100ms", cold_res['frametime_ms']['stutters_gt_100ms'], warm_res['frametime_ms']['stutters_gt_100ms'], "count")
            add_row("Peak RSS", cold_res['memory_mb']['peak_rss'], warm_res['memory_mb']['peak_rss'], "MB")
            add_row("Peak Commit", cold_res['memory_mb']['peak_commit'], warm_res['memory_mb']['peak_commit'], "MB")
            add_row("Avg CPU", cold_res['cpu']['avg_percent'], warm_res['cpu']['avg_percent'], "%")
            add_row("Total Draw Calls", cold_res['gpu_and_caches']['total_draw_calls'], warm_res['gpu_and_caches']['total_draw_calls'], "calls")
            add_row("Command Stalls", cold_res['gpu_and_caches']['command_buffer_stalls'], warm_res['gpu_and_caches']['command_buffer_stalls'], "stalls")
            add_row("Pipeline Cache Hit Rate", cold_res['gpu_and_caches']['pipeline_cache_hit_rate_pct'], warm_res['gpu_and_caches']['pipeline_cache_hit_rate_pct'], "%")
            add_row("Pipeline Creations", cold_res['gpu_and_caches']['pipeline_creations_logged'], warm_res['gpu_and_caches']['pipeline_creations_logged'], "creations")

        print(f"\n[BENCHMARK] Comparison written to: {comp_csv}")

if __name__ == '__main__':
    main()
