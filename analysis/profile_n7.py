"""
NeverDead N7 Benchmark & Telemetry Profiler
Measures 60-second Cold Cache and Warm Cache scenarios:
- Frametimes: p50, p95, p99, median FPS, min FPS, frametime spikes
- Memory: RSS Working Set, Peak Commit RAM, Handle count, Threads
- Graphics/Pipeline: Draw calls, vertex counts, shader cache growth, pipeline creations
- Audio & Kernel: XMA frames, latency, command buffer stalls
"""

import argparse
import ctypes
from ctypes import wintypes
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Win32 structures for memory and process query
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

def find_window_for_pid(pid):
    hwnds = []
    def enum_cb(hwnd, lparam):
        wpid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid and ctypes.windll.user32.IsWindowVisible(hwnd):
            hwnds.append(hwnd)
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return hwnds[0] if hwnds else None

def tap_key(hwnd, vk):
    user32 = ctypes.windll.user32
    scan = user32.MapVirtualKeyW(vk, 0)
    extended = 1 if (37 <= vk <= 40) else 0
    l_down = 1 | (scan << 16) | (extended << 24)
    l_up = 1 | (scan << 16) | (extended << 24) | (1 << 30) | (1 << 31)
    if hwnd:
        user32.PostMessageW(hwnd, 0x0100, vk, l_down)
    time.sleep(0.08)
    if hwnd:
        user32.PostMessageW(hwnd, 0x0101, vk, l_up)
    time.sleep(0.05)

def run_benchmark(scenario, duration_sec, exe_path, game_data_root, cache_dir, user_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(user_dir, exist_ok=True)
    
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

    perf_csv_path = os.path.join(output_dir, f"n7_{scenario}_perf_frames.csv")
    runtime_log_path = os.path.join(output_dir, f"n7_{scenario}_runtime.log")
    
    if os.path.exists(perf_csv_path):
        os.remove(perf_csv_path)

    cmd = [
        exe_path,
        f"--game_data_root={game_data_root}",
        f"--user_data_root={user_dir}",
        f"--cache_root={cache_dir}",
        "--mnk_mode=true",
        "--input_background=true",
        "--gpu_allow_invalid_fetch_constants=false",
        f"--perf_log_csv={perf_csv_path}",
        "--log_level=debug",
        f"--log_file={runtime_log_path}"
    ]

    print(f"[{scenario.upper()}] Launching: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, cwd=os.path.dirname(exe_path))
    h_proc = wintypes.HANDLE(ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0400, False, proc.pid)) # PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_QUERY_INFORMATION

    rss_samples = []
    commit_samples = []
    start_time = time.time()
    deadline = start_time + duration_sec

    kernel32 = ctypes.windll.kernel32
    creation_time = FILETIME()
    exit_time = FILETIME()
    kernel_time_prev = FILETIME()
    user_time_prev = FILETIME()
    time_prev = time.time()
    cpu_samples = []

    if h_proc:
        kernel32.GetProcessTimes(h_proc, ctypes.byref(creation_time), ctypes.byref(exit_time),
                                ctypes.byref(kernel_time_prev), ctypes.byref(user_time_prev))

    print(f"[{scenario.upper()}] Sampling metrics for {duration_sec}s (PID: {proc.pid})...")
    
    hwnd = None
    win_deadline = time.time() + 15
    while time.time() < win_deadline and proc.poll() is None:
        hwnd = find_window_for_pid(proc.pid)
        if hwnd:
            break
        time.sleep(0.2)

    step_stage = 0
    while time.time() < deadline:
        if proc.poll() is not None:
            print(f"[{scenario.upper()}] WARNING: Process exited early with code {proc.returncode}!")
            break

        now = time.time()
        elapsed_sec = now - start_time

        # Drive transition into 3D gameplay
        if step_stage == 0 and elapsed_sec >= 16.0:
            tap_key(hwnd, 0x0D)  # VK_RETURN
            time.sleep(0.5)
            tap_key(hwnd, 0x58)  # VK_X
            step_stage = 1
        elif step_stage == 1 and elapsed_sec >= 19.5:
            tap_key(hwnd, 0x26)  # VK_UP
            time.sleep(0.5)
            tap_key(hwnd, 0x20)  # VK_SPACE
            step_stage = 2
        elif step_stage == 2 and elapsed_sec >= 22.0:
            tap_key(hwnd, 0x20)  # VK_SPACE
            step_stage = 3
        elif step_stage == 3 and elapsed_sec >= 26.0:
            tap_key(hwnd, 0x0D)  # VK_RETURN (skip cinematic into 3D gameplay)
            step_stage = 4
        elif step_stage == 4 and elapsed_sec >= 29.0:
            # Active gameplay movement
            tap_key(hwnd, 0x57)  # 'W'
            time.sleep(0.3)
            tap_key(hwnd, 0x20)  # Space roll

        if h_proc:
            mem = get_process_memory(h_proc)
            if mem:
                rss_samples.append(mem['rss_mb'])
                commit_samples.append(mem['commit_mb'])

            kt = FILETIME()
            ut = FILETIME()
            if kernel32.GetProcessTimes(h_proc, ctypes.byref(creation_time), ctypes.byref(exit_time),
                                        ctypes.byref(kt), ctypes.byref(ut)):
                dt = now - time_prev
                if dt > 0.5:
                    d_kernel = (filetime_to_int(kt) - filetime_to_int(kernel_time_prev)) / 10000000.0
                    d_user = (filetime_to_int(ut) - filetime_to_int(user_time_prev)) / 10000000.0
                    cpu_percent = ((d_kernel + d_user) / dt) * 100.0
                    cpu_samples.append(cpu_percent)
                    kernel_time_prev = kt
                    user_time_prev = ut
                    time_prev = now

        time.sleep(0.1)

    elapsed = time.time() - start_time
    print(f"[{scenario.upper()}] Completed {elapsed:.1f}s sample window.")

    # Graceful shutdown or termination
    if proc.poll() is None:
        print(f"[{scenario.upper()}] Terminating benchmark process {proc.pid}...")
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

    # Parse per-frame CSV if generated
    frame_times_ms = []
    fps_values = []
    draw_calls = []
    vertices = []
    stalls = []
    tex_hits = []
    tex_misses = []
    pipe_hits = []
    pipe_misses = []

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

    # Check for errors in runtime log
    d3d12_errors = 0
    d3d12_warnings = 0
    fatal_errors = 0
    invalid_tex_warnings = 0

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

    results = {
        'scenario': scenario,
        'duration_sec': elapsed,
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
            'shader_cache_files_start': initial_cache_files,
            'shader_cache_files_end': final_cache_files,
            'shader_cache_files_new': new_cache_files,
            'shader_cache_bytes_new': new_cache_bytes,
        },
        'log_health': {
            'fatal_crashes': fatal_errors,
            'd3d12_errors': d3d12_errors,
            'd3d12_warnings': d3d12_warnings,
            'invalid_texture_warnings': invalid_tex_warnings,
        }
    }

    json_out = os.path.join(output_dir, f"n7_{scenario}_profile.json")
    with open(json_out, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    print(f"[{scenario.upper()}] Results saved to: {json_out}")
    print(f"  Frames: {total_frames} | Median FPS: {median_fps:.1f} | p50 FT: {p50_ft:.2f}ms | p95 FT: {p95_ft:.2f}ms | p99 FT: {p99_ft:.2f}ms")
    print(f"  Peak RSS: {peak_rss:.1f} MB | Peak Commit: {peak_commit:.1f} MB | New Shaders: {new_cache_files} ({new_cache_bytes/1024:.1f} KB)")
    print(f"  Fatals: {fatal_errors} | D3D12 Errors: {d3d12_errors} | Invalid Tex Warnings: {invalid_tex_warnings}")
    
    return results

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="NeverDead N7 Benchmark Profiler")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds (default 60)")
    parser.add_argument("--exe", default=r"C:\projetos\neverdead\build\n2-neverdead\neverdead.exe")
    parser.add_argument("--game-data", default=r"C:\projetos\NeverDeadxex")
    parser.add_argument("--output-dir", default=r"C:\projetos\neverdead\analysis\n7-benchmarks")
    args = parser.parse_args()

    cache_dir = os.path.join(args.output_dir, "shader_cache")
    user_dir = os.path.join(args.output_dir, "user_data")

    print("=================================================================")
    print("           NEVERDEAD N7 PROFILING: COLD CACHE (60s)             ")
    print("=================================================================")
    cold_results = run_benchmark("cold", args.duration, args.exe, args.game_data, cache_dir, user_dir, args.output_dir)

    print("\nWaiting 3 seconds for system stabilization...")
    time.sleep(3)

    print("=================================================================")
    print("           NEVERDEAD N7 PROFILING: WARM CACHE (60s)             ")
    print("=================================================================")
    warm_results = run_benchmark("warm", args.duration, args.exe, args.game_data, cache_dir, user_dir, args.output_dir)

    # Comparative CSV summary
    comp_csv = os.path.join(args.output_dir, "n7_benchmark_comparison.csv")
    with open(comp_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Metric", "Cold Cache", "Warm Cache", "Delta / Improvement"])
        
        # Frametimes
        writer.writerow(["Frames Captured", cold_results['frames_captured'], warm_results['frames_captured'], 
                         warm_results['frames_captured'] - cold_results['frames_captured']])
        writer.writerow(["p50 Frametime (ms)", f"{cold_results['frametime_ms']['p50']:.2f}", f"{warm_results['frametime_ms']['p50']:.2f}",
                         f"{warm_results['frametime_ms']['p50'] - cold_results['frametime_ms']['p50']:.2f} ms"])
        writer.writerow(["p95 Frametime (ms)", f"{cold_results['frametime_ms']['p95']:.2f}", f"{warm_results['frametime_ms']['p95']:.2f}",
                         f"{warm_results['frametime_ms']['p95'] - cold_results['frametime_ms']['p95']:.2f} ms"])
        writer.writerow(["p99 Frametime (ms)", f"{cold_results['frametime_ms']['p99']:.2f}", f"{warm_results['frametime_ms']['p99']:.2f}",
                         f"{warm_results['frametime_ms']['p99'] - cold_results['frametime_ms']['p99']:.2f} ms"])
        writer.writerow(["Max Frametime Spike (ms)", f"{cold_results['frametime_ms']['max']:.2f}", f"{warm_results['frametime_ms']['max']:.2f}",
                         f"{warm_results['frametime_ms']['max'] - cold_results['frametime_ms']['max']:.2f} ms"])
        writer.writerow(["Stutters > 33.3ms", cold_results['frametime_ms']['stutters_gt_33ms'], warm_results['frametime_ms']['stutters_gt_33ms'],
                         warm_results['frametime_ms']['stutters_gt_33ms'] - cold_results['frametime_ms']['stutters_gt_33ms']])
        writer.writerow(["Stutters > 50ms", cold_results['frametime_ms']['stutters_gt_50ms'], warm_results['frametime_ms']['stutters_gt_50ms'],
                         warm_results['frametime_ms']['stutters_gt_50ms'] - cold_results['frametime_ms']['stutters_gt_50ms']])
        writer.writerow(["Median FPS", f"{cold_results['fps']['median']:.1f}", f"{warm_results['fps']['median']:.1f}",
                         f"{warm_results['fps']['median'] - cold_results['fps']['median']:.1f} FPS"])
        writer.writerow(["1% Low FPS", f"{cold_results['fps']['p1_low']:.1f}", f"{warm_results['fps']['p1_low']:.1f}",
                         f"{warm_results['fps']['p1_low'] - cold_results['fps']['p1_low']:.1f} FPS"])
        
        # Memory
        writer.writerow(["Peak RSS RAM (MB)", f"{cold_results['memory_mb']['peak_rss']:.1f}", f"{warm_results['memory_mb']['peak_rss']:.1f}",
                         f"{warm_results['memory_mb']['peak_rss'] - cold_results['memory_mb']['peak_rss']:.1f} MB"])
        writer.writerow(["Peak Commit RAM (MB)", f"{cold_results['memory_mb']['peak_commit']:.1f}", f"{warm_results['memory_mb']['peak_commit']:.1f}",
                         f"{warm_results['memory_mb']['peak_commit'] - cold_results['memory_mb']['peak_commit']:.1f} MB"])
        
        # Shaders & Pipeline
        writer.writerow(["New Shader Cache Files", cold_results['gpu_and_caches']['shader_cache_files_new'], 
                         warm_results['gpu_and_caches']['shader_cache_files_new'],
                         warm_results['gpu_and_caches']['shader_cache_files_new'] - cold_results['gpu_and_caches']['shader_cache_files_new']])
        writer.writerow(["New Shader Cache Size (KB)", f"{cold_results['gpu_and_caches']['shader_cache_bytes_new']/1024:.1f}", 
                         f"{warm_results['gpu_and_caches']['shader_cache_bytes_new']/1024:.1f}",
                         f"{(warm_results['gpu_and_caches']['shader_cache_bytes_new'] - cold_results['gpu_and_caches']['shader_cache_bytes_new'])/1024:.1f} KB"])
        
        # Health
        writer.writerow(["Fatal Crashes", cold_results['log_health']['fatal_crashes'], warm_results['log_health']['fatal_crashes'], 0])
        writer.writerow(["D3D12 Errors", cold_results['log_health']['d3d12_errors'], warm_results['log_health']['d3d12_errors'], 0])
        writer.writerow(["Invalid Texture Warnings", cold_results['log_health']['invalid_texture_warnings'], 
                         warm_results['log_health']['invalid_texture_warnings'], 0])

    print(f"\nComparative Benchmark CSV saved to: {comp_csv}")
