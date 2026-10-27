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
import atexit
import csv
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

kernel32 = ctypes.windll.kernel32
kernel32.CreateMutexW.restype = wintypes.HANDLE
ERROR_ALREADY_EXISTS = 183

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

def snapshot_save_writes(path):
    snapshot = {}
    for root, _, files in os.walk(path):
        for name in files:
            if not name.lower().endswith(('.sav', '.header')):
                continue
            file_path = os.path.join(root, name)
            try:
                snapshot[os.path.relpath(file_path, path)] = os.stat(file_path).st_mtime_ns
            except FileNotFoundError:
                pass
    return snapshot

def snapshot_save_files(path):
    snapshot = {}
    for root, _, files in os.walk(path):
        for name in files:
            if not name.lower().endswith(('.sav', '.header')):
                continue
            file_path = os.path.join(root, name)
            try:
                digest = hashlib.sha256()
                with open(file_path, 'rb') as save_file:
                    for chunk in iter(lambda: save_file.read(1024 * 1024), b''):
                        digest.update(chunk)
                stat = os.stat(file_path)
                snapshot[os.path.relpath(file_path, path)] = {
                    'size_bytes': stat.st_size,
                    'modified_ns': stat.st_mtime_ns,
                    'sha256': digest.hexdigest().upper(),
                }
            except (FileNotFoundError, PermissionError):
                pass
    return snapshot

def calculate_percentile(sorted_list, p):
    if not sorted_list:
        return 0.0
    idx = (len(sorted_list) - 1) * p / 100.0
    floor_idx = int(idx)
    ceil_idx = min(floor_idx + 1, len(sorted_list) - 1)
    weight = idx - floor_idx
    return sorted_list[floor_idx] * (1.0 - weight) + sorted_list[ceil_idx] * weight

def linear_slope_per_minute(times, values):
    if len(times) < 2 or len(times) != len(values):
        return 0.0
    mean_time = sum(times) / len(times)
    mean_value = sum(values) / len(values)
    denominator = sum((sample_time - mean_time) ** 2 for sample_time in times)
    if denominator == 0.0:
        return 0.0
    slope_per_second = sum(
        (sample_time - mean_time) * (value - mean_value)
        for sample_time, value in zip(times, values)
    ) / denominator
    return slope_per_second * 60.0

def evaluate_stability_gate(results, requested_seconds):
    actions = results['stability_actions']
    health = results['log_health']
    save_persistence = results['save_persistence']
    final_save_files = save_persistence['final_files']
    checks = {
        'completed_duration': (
            results['measurement_window']['elapsed_seconds'] >= requested_seconds and
            results['measurement_window']['rendered_seconds'] >= requested_seconds * 0.95 and
            results['frames_captured'] >= requested_seconds * 20
        ),
        'pause_resume': actions['pause_resume'] >= max(0, (requested_seconds - 1) // 300),
        'focus_cycles': actions['focus_cycles'] >= max(0, (requested_seconds - 1) // 450),
        'combat': actions['combat'] > 0,
        'checkpoint_saves': (actions['checkpoint_saves'] >= 2
                             if requested_seconds >= 1800 else True),
        'checkpoint_state_persisted': (
            any(name.lower().endswith('.sav') for name in final_save_files) and
            final_save_files != save_persistence['initial_files']
            if requested_seconds >= 1800 else True
        ),
        'audio_xma_active': results['ppc_and_system']['total_xma_frames'] > 0,
        'audio_underruns': results['audio']['buffer_underruns'] == 0,
        'fatal_crashes': health['fatal_crashes'] == 0,
        'd3d12_errors': health['d3d12_errors'] == 0,
        'dred_faults': health['dred_faults'] == 0,
    }
    return {'passed': all(checks.values()), 'checks': checks}

def get_csv_size(path):
    return os.path.getsize(path) if os.path.exists(path) else 0

def measure_bmp(path):
    data = Path(path).read_bytes()
    if data[:2] != b'BM' or len(data) < 54:
        raise ValueError(f"Unsupported BMP: {path}")
    pixel_offset = struct.unpack_from('<I', data, 10)[0]
    width, height = struct.unpack_from('<ii', data, 18)
    bits_per_pixel = struct.unpack_from('<H', data, 28)[0]
    compression = struct.unpack_from('<I', data, 30)[0]
    if width <= 0 or height == 0 or bits_per_pixel not in (24, 32) or compression != 0:
        raise ValueError(f"Unsupported BMP layout: {path}")
    row_stride = ((width * bits_per_pixel + 31) // 32) * 4
    bytes_per_pixel = bits_per_pixel // 8
    height_abs = abs(height)
    luminance_sum = 0.0
    channel_sums = [0, 0, 0]
    non_black = 0
    sampled = 0
    for gx in range(10, 90, 7):
        for gy in range(10, 90, 7):
            x = width * gx // 100
            y = height_abs * gy // 100
            row = height_abs - 1 - y if height > 0 else y
            offset = pixel_offset + row * row_stride + x * bytes_per_pixel
            blue, green, red = data[offset:offset + 3]
            channel_sums[0] += red
            channel_sums[1] += green
            channel_sums[2] += blue
            luminance_sum += 0.299 * red + 0.587 * green + 0.114 * blue
            non_black += red > 15 or green > 15 or blue > 15
            sampled += 1
    return {
        'width': width,
        'height': height_abs,
        'non_black_ratio': non_black / sampled,
        'average_luminance': luminance_sum / sampled,
        'average_rgb': [value / sampled for value in channel_sums],
    }

def compare_bmp(reference_path, candidate_path):
    reference = measure_bmp(reference_path)
    candidate = measure_bmp(candidate_path)
    luminance_delta_pct = abs(candidate['average_luminance'] - reference['average_luminance']) / max(
        reference['average_luminance'], 1.0) * 100.0
    channel_delta = max(abs(a - b) for a, b in zip(
        reference['average_rgb'], candidate['average_rgb']))
    passed = (reference['width'] == candidate['width'] and
              reference['height'] == candidate['height'] and
              luminance_delta_pct <= 10.0 and channel_delta <= 12.0 and
              abs(candidate['non_black_ratio'] - reference['non_black_ratio']) <= 0.1)
    return {
        'passed': passed,
        'reference': str(reference_path),
        'candidate': str(candidate_path),
        'luminance_delta_pct': luminance_delta_pct,
        'maximum_average_channel_delta': channel_delta,
    }

def get_idle_seconds():
    return ((ctypes.windll.kernel32.GetTickCount() - get_last_input_tick()) & 0xFFFFFFFF) / 1000.0

def get_last_input_tick():
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]

    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        raise ctypes.WinError()
    return info.dwTime

def wait_for_idle(required_seconds):
    if required_seconds <= 0:
        return
    print(f"Waiting until Windows has been idle for {required_seconds}s...")
    while get_idle_seconds() < required_seconds:
        time.sleep(5.0)

class UserActivityInterrupted(RuntimeError):
    pass

def run_after_idle(required_seconds, benchmark):
    while True:
        wait_for_idle(required_seconds)
        try:
            return benchmark()
        except UserActivityInterrupted as error:
            if required_seconds <= 0:
                raise
            print(f"{error}; waiting for the next idle window...")

def acquire_profiler_mutex():
    handle = kernel32.CreateMutexW(None, False, "Local\\NeverDeadGameplayProfiler")
    if not handle:
        raise ctypes.WinError()
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        raise RuntimeError("Another NeverDead gameplay profiler is already running")
    return handle

def stop_process_when_user_returns(proc, detected, initial_input_tick, poll_seconds=0.5):
    while proc.poll() is None:
        current_input_tick = get_last_input_tick()
        if current_input_tick != initial_input_tick:
            foreground_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(
                user32.GetForegroundWindow(), ctypes.byref(foreground_pid))
            if foreground_pid.value != proc.pid:
                detected.set()
                proc.terminate()
                return
            initial_input_tick = current_input_tick
        time.sleep(poll_seconds)

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
VK_E = 0x45
VK_Q = 0x51
VK_X = 0x58
VK_ESCAPE = 0x1B

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
    if not hwnd:
        raise RuntimeError("Cannot send targeted input without a game window")
    scan = user32.MapVirtualKeyW(vk, 0)
    extended = 1 if (37 <= vk <= 40) else 0
    l_down = 1 | (scan << 16) | (extended << 24)
    l_up = 1 | (scan << 16) | (extended << 24) | (1 << 30) | (1 << 31)
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, l_down)
    time.sleep(0.08)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, l_up)
    time.sleep(0.05)

def hold_key(hwnd, vk, duration_sec):
    if not hwnd:
        raise RuntimeError("Cannot send targeted input without a game window")
    scan = user32.MapVirtualKeyW(vk, 0)
    extended = 1 if (37 <= vk <= 40) else 0
    l_down = 1 | (scan << 16) | (extended << 24)
    l_up = 1 | (scan << 16) | (extended << 24) | (1 << 30) | (1 << 31)
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, l_down)
    time.sleep(duration_sec)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, l_up)
    time.sleep(0.05)

def run_gameplay_benchmark(scenario, gameplay_duration_sec, exe_path, game_data_root, cache_dir,
                           user_dir, output_dir, artifact_label=None, render_target_path="rov",
                           reference_capture=None, gamma_unorm16=True,
                           snorm16_full_range=True, stability_mode=False,
                           stop_on_user_activity=False, log_level="debug"):
    os.makedirs(output_dir, exist_ok=True)
    artifact_label = artifact_label or f"{scenario}_{render_target_path}"
    run_user_dir = os.path.join(user_dir, f"{artifact_label}-{int(time.time())}")
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

    perf_csv_path = os.path.join(output_dir, f"n13_{artifact_label}_perf_frames.csv")
    runtime_log_path = os.path.join(output_dir, f"n13_{artifact_label}_runtime.log")

    for stale_path in (perf_csv_path, runtime_log_path):
        if os.path.exists(stale_path):
            os.remove(stale_path)

    cmd = [
        exe_path,
        f"--game_data_root={game_data_root}",
        f"--user_data_root={run_user_dir}",
        f"--cache_root={cache_dir}",
        "--mnk_mode=true",
        "--input_background=true",
        "--gpu_allow_invalid_fetch_constants=false",
        f"--render_target_path_d3d12={render_target_path}",
        f"--gamma_render_target_as_unorm16={'true' if gamma_unorm16 else 'false'}",
        f"--snorm16_render_target_full_range={'true' if snorm16_full_range else 'false'}",
        f"--perf_log_csv={perf_csv_path}",
        f"--log_level={log_level}",
        f"--log_file={runtime_log_path}"
    ]

    capture_trigger = Path(exe_path).parent / "capture_trigger.txt"
    capture_trigger.unlink(missing_ok=True)
    runtime_env = os.environ.copy()
    runtime_env["NEVERDEAD_CAPTURE_DIR"] = output_dir

    print(f"[{scenario.upper()}] Launching NeverDead runtime...")
    creationflags = (subprocess.BELOW_NORMAL_PRIORITY_CLASS
                     if stability_mode or stop_on_user_activity else 0)
    proc = subprocess.Popen(cmd, cwd=os.path.dirname(exe_path), env=runtime_env,
                            creationflags=creationflags)
    user_activity_detected = threading.Event()
    h_proc = wintypes.HANDLE(ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0400, False, proc.pid))

    rss_samples = []
    commit_samples = []
    memory_sample_times = []
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

    if not hwnd:
        proc.terminate()
        proc.wait(timeout=5)
        if h_proc:
            kernel32.CloseHandle(h_proc)
        if user_activity_detected.is_set():
            raise UserActivityInterrupted(
                f"{artifact_label} stopped because laptop activity resumed")
        raise RuntimeError(f"{artifact_label} game window was not created")
    print(f"[{scenario.upper()}] Window acquired: 0x{hwnd:X}")
    if stop_on_user_activity:
        # The runtime may update Windows input state while creating its window.
        threading.Thread(target=stop_process_when_user_returns,
                         args=(proc, user_activity_detected, get_last_input_tick()),
                         daemon=True).start()

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
        if h_proc:
            kernel32.CloseHandle(h_proc)
        if user_activity_detected.is_set():
            raise UserActivityInterrupted(
                f"{artifact_label} stopped because laptop activity resumed")
        raise RuntimeError(
            f"{artifact_label} process terminated at title boot (code {proc.returncode})"
        )

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
    for _ in range(8):
        tap_key(hwnd, VK_RETURN)
        time.sleep(0.5)
        tap_key(hwnd, VK_SPACE)  # Confirm skip, or resume if START paused gameplay.
        time.sleep(2.5)
    time.sleep(10.0)

    capture_pattern = f"n13-{artifact_label}-gameplay-*.bmp"
    captures_before = set(Path(output_dir).glob(capture_pattern))
    capture_trigger.write_text(f"n13-{artifact_label}-gameplay", encoding="ascii")
    capture_path = None
    capture_deadline = time.time() + 5.0
    while time.time() < capture_deadline:
        new_captures = set(Path(output_dir).glob(capture_pattern)) - captures_before
        if new_captures:
            capture_path = max(new_captures, key=lambda path: path.stat().st_mtime)
            break
        time.sleep(0.2)
    print(f"[{scenario.upper()}] Stage 6: >>> 3D GAMEPLAY ACTIVE <<< Sampling {gameplay_duration_sec}s of real gameplay...")

    # Exclude boot, menus and cutscenes from every gameplay-only metric.
    gameplay_csv_start = get_csv_size(perf_csv_path)
    rss_samples.clear()
    commit_samples.clear()
    memory_sample_times.clear()
    cpu_samples.clear()
    if h_proc:
        kernel32.GetProcessTimes(h_proc, ctypes.byref(creation_time), ctypes.byref(exit_time),
                                 ctypes.byref(kernel_time_prev), ctypes.byref(user_time_prev))
    time_prev = time.time()

    # Active gameplay interaction loop
    gameplay_monotonic_start = time.monotonic()
    gameplay_start = time.time()
    gameplay_end = gameplay_start + gameplay_duration_sec
    cycle_counter = 0
    stability_actions = {
        'combat': 0,
        'pause_resume': 0,
        'focus_cycles': 0,
        'checkpoint_saves': 0,
    }
    save_write_snapshot = snapshot_save_writes(run_user_dir)
    save_files_initial = snapshot_save_files(run_user_dir)
    next_pause = gameplay_start + 300.0
    next_focus = gameplay_start + 450.0

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
                memory_sample_times.append(time.time() - gameplay_start)

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
        now = time.time()
        if stability_mode and now >= next_pause:
            tap_key(hwnd, VK_RETURN)
            time.sleep(2.0)
            tap_key(hwnd, VK_ESCAPE)
            stability_actions['pause_resume'] += 1
            next_pause += 300.0
        if stability_mode and now >= next_focus:
            user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
            time.sleep(2.0)
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            stability_actions['focus_cycles'] += 1
            next_focus += 450.0

        mod_idx = cycle_counter % 7
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
        elif mod_idx == 5:
            tap_key(hwnd, VK_E)        # Right trigger / primary combat
            stability_actions['combat'] += 1
        elif mod_idx == 6:
            tap_key(hwnd, VK_Q)        # Left trigger / alternate combat
            stability_actions['combat'] += 1

        cycle_counter += 1
        current_save_writes = snapshot_save_writes(run_user_dir)
        if current_save_writes != save_write_snapshot:
            stability_actions['checkpoint_saves'] += 1
            save_write_snapshot = current_save_writes
        time.sleep(0.1)

    gameplay_elapsed_seconds = time.monotonic() - gameplay_monotonic_start
    gameplay_csv_end = get_csv_size(perf_csv_path)

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

    if user_activity_detected.is_set():
        raise UserActivityInterrupted(
            f"{artifact_label} stopped because laptop activity resumed")

    save_files_final = snapshot_save_files(run_user_dir)
    final_cache_files, final_cache_bytes = get_dir_size_and_count(cache_dir)
    new_cache_files = final_cache_files - initial_cache_files
    new_cache_bytes = final_cache_bytes - initial_cache_bytes

    # Parse per-frame CSV
    frame_times_ms = []
    fps_values = []
    swap_cpu_times_ms = []
    gpu_times_ms = []
    present_times_ms = []
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
    audio_latencies_us = []
    audio_queue_depths = []

    if os.path.exists(perf_csv_path) and os.path.getsize(perf_csv_path) > 0:
        with open(perf_csv_path, 'rb') as f:
            csv_bytes = f.read()
            header_end = csv_bytes.find(b'\n') + 1
            gameplay_csv = csv_bytes[:header_end] + csv_bytes[gameplay_csv_start:gameplay_csv_end]
            reader = csv.DictReader(gameplay_csv.decode('utf-8', errors='ignore').splitlines())
            gameplay_rows = list(reader)
            for row in gameplay_rows:
                try:
                    ft_us = float(row.get('frame_time_us', 0))
                    if ft_us > 0:
                        frame_times_ms.append(ft_us / 1000.0)
                    fps = float(row.get('fps', 0))
                    if fps > 0:
                        fps_values.append(fps)
                    swap_cpu_us = float(row.get('swap_cpu_time_us', 0))
                    gpu_us = float(row.get('gpu_time_us', 0))
                    present_us = float(row.get('present_time_us', 0))
                    if swap_cpu_us > 0:
                        swap_cpu_times_ms.append(swap_cpu_us / 1000.0)
                    if gpu_us > 0:
                        gpu_times_ms.append(gpu_us / 1000.0)
                    if present_us > 0:
                        present_times_ms.append(present_us / 1000.0)
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
                    audio_latencies_us.append(int(row.get('audio_frame_latency_us', 0)))
                    audio_queue_depths.append(int(row.get('buffer_queue_depth', 0)))
                except (ValueError, KeyError):
                    continue

    sorted_fts = sorted(frame_times_ms)
    sorted_fps = sorted(fps_values)

    def timing_summary(values):
        sorted_values = sorted(values)
        return {
            'p50': calculate_percentile(sorted_values, 50),
            'p95': calculate_percentile(sorted_values, 95),
            'p99': calculate_percentile(sorted_values, 99),
            'max': sorted_values[-1] if sorted_values else 0.0,
        }

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
    sample_window = min(10, len(rss_samples))
    rss_growth = ((sum(rss_samples[-sample_window:]) - sum(rss_samples[:sample_window])) /
                  sample_window) if sample_window else 0.0
    commit_growth = ((sum(commit_samples[-sample_window:]) - sum(commit_samples[:sample_window])) /
                     sample_window) if sample_window else 0.0
    rss_slope = linear_slope_per_minute(memory_sample_times, rss_samples)
    commit_slope = linear_slope_per_minute(memory_sample_times, commit_samples)
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
    dred_faults = 0
    invalid_tex_warnings = 0
    pipeline_creations = 0
    audio_underruns = 0

    if os.path.exists(runtime_log_path):
        with open(runtime_log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line_lower = line.lower()
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
                if 'dred breadcrumb' in line_lower or 'dred page fault' in line_lower:
                    dred_faults += 1
                if 'underrun' in line_lower or 'drop frame' in line_lower:
                    audio_underruns += 1

    results = {
        'scenario': scenario,
        'run': artifact_label,
        'render_target_path': render_target_path,
        'save_persistence': {
            'user_data_root': run_user_dir,
            'initial_files': save_files_initial,
            'final_files': save_files_final,
        },
        'measurement_window': {
            'gameplay_csv_start_byte': gameplay_csv_start,
            'gameplay_csv_end_byte': gameplay_csv_end,
            'requested_seconds': gameplay_duration_sec,
            'elapsed_seconds': gameplay_elapsed_seconds,
            'rendered_seconds': sum(frame_times_ms) / 1000.0,
        },
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
        'timing_breakdown_ms': {
            'swap_cpu': timing_summary(swap_cpu_times_ms),
            'gpu': timing_summary(gpu_times_ms),
            'present_call': timing_summary(present_times_ms),
        },
        'memory_mb': {
            'peak_rss': peak_rss,
            'avg_rss': avg_rss,
            'peak_commit': peak_commit,
            'rss_growth': rss_growth,
            'commit_growth': commit_growth,
            'rss_slope_mb_per_min': rss_slope,
            'commit_slope_mb_per_min': commit_slope,
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
        'audio': {
            'latency_us_p95': calculate_percentile(sorted(audio_latencies_us), 95),
            'latency_us_max': max(audio_latencies_us) if audio_latencies_us else 0,
            'queue_depth_max': max(audio_queue_depths) if audio_queue_depths else 0,
            'buffer_underruns': audio_underruns,
        },
        'stability_actions': stability_actions,
        'log_health': {
            'fatal_crashes': fatal_errors,
            'd3d12_errors': d3d12_errors,
            'd3d12_warnings': d3d12_warnings,
            'dred_faults': dred_faults,
            'invalid_texture_warnings': invalid_tex_warnings,
        }
    }

    average_draw_calls = sum(draw_calls) / total_frames if total_frames else 0.0
    capture_metrics = measure_bmp(capture_path) if capture_path else None
    results['gameplay_gate'] = {
        'passed': (total_frames >= gameplay_duration_sec * 20 and
                   average_draw_calls >= 100 and capture_metrics is not None and
                   capture_metrics['non_black_ratio'] > 0.75 and
                   capture_metrics['average_luminance'] >= 10.0),
        'average_draw_calls_per_frame': average_draw_calls,
        'minimum_average_draw_calls_per_frame': 100,
        'capture': str(capture_path) if capture_path else None,
        'capture_metrics': capture_metrics,
    }
    results['stability_gate'] = (evaluate_stability_gate(results, gameplay_duration_sec)
                                 if stability_mode else None)
    results['performance_gate'] = {
        'passed': (results['gameplay_gate']['passed'] and fatal_errors == 0 and
                   (results['stability_gate']['passed'] if stability_mode else True) and
                   (stability_mode or (p1_low_fps >= 26.0 and stutter_50ms <= 1))),
        'stability_mode': stability_mode,
        'minimum_1_percent_low_fps': 26.0,
        'maximum_frames_over_50ms': 1,
    }
    results['visual_gate'] = (compare_bmp(reference_capture, capture_path)
                              if reference_capture and capture_path else None)

    json_out = os.path.join(output_dir, f"n13_{artifact_label}_profile.json")
    with open(json_out, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    print(f"[{scenario.upper()}] Results saved to: {json_out}")
    print(f"  Frames Captured: {total_frames} | Median FPS: {median_fps:.1f} | Min FPS: {min_fps:.1f} | 1% Low: {p1_low_fps:.1f}")
    print(f"  Frametime (ms): Mean: {results['frametime_ms']['mean']:.2f} | p50: {p50_ft:.2f} | p95: {p95_ft:.2f} | p99: {p99_ft:.2f} | Max: {results['frametime_ms']['max']:.2f}")
    print(f"  Timing p95 (ms): Swap CPU: {results['timing_breakdown_ms']['swap_cpu']['p95']:.2f} | GPU: {results['timing_breakdown_ms']['gpu']['p95']:.2f} | Present: {results['timing_breakdown_ms']['present_call']['p95']:.2f}")
    print(f"  Stutters: >33ms: {stutter_33ms} | >50ms: {stutter_50ms} | >100ms: {stutter_100ms}")
    print(f"  Memory: Peak RSS: {peak_rss:.1f} MB | Peak Commit: {peak_commit:.1f} MB | CPU Avg: {avg_cpu:.1f}% (Peak {peak_cpu:.1f}%)")
    print(f"  D3D12: Draw Calls: {sum(draw_calls)} | Vertices: {sum(vertices)} | Stalls: {sum(stalls)} | Pipeline Hits: {pipe_hit_rate:.1f}%")

    if not results['gameplay_gate']['passed']:
        capture_metrics = results['gameplay_gate']['capture_metrics'] or {}
        raise RuntimeError(
            f"{scenario} gameplay gate failed: {average_draw_calls:.1f} draw calls/frame, "
            f"luminance {capture_metrics.get('average_luminance', 0.0):.1f}, "
            f"non-black {capture_metrics.get('non_black_ratio', 0.0):.1%}"
        )
    if stability_mode and not results['stability_gate']['passed']:
        failed_checks = [name for name, passed in results['stability_gate']['checks'].items()
                         if not passed]
        raise RuntimeError(f"{artifact_label} stability gate failed: {', '.join(failed_checks)}")
    if not results['performance_gate']['passed']:
        raise RuntimeError(
            f"{artifact_label} performance regression: 1% low {p1_low_fps:.1f} FPS, "
            f"{stutter_50ms} frames over 50 ms"
        )
    if results['visual_gate'] and not results['visual_gate']['passed']:
        raise RuntimeError(
            f"{artifact_label} differs from ROV reference: "
            f"{results['visual_gate']['luminance_delta_pct']:.1f}% luminance delta"
        )

    return results

def main():
    mutex = acquire_profiler_mutex()
    atexit.register(kernel32.CloseHandle, mutex)
    parser = argparse.ArgumentParser(description="NeverDead N13 Real Gameplay Performance Benchmark")
    parser.add_argument("--scenario", choices=["cold", "warm", "both"], default="both")
    parser.add_argument("--duration", type=int, default=30, help="Interactive gameplay sampling duration in seconds")
    parser.add_argument("--runs", type=int, choices=range(1, 6), default=1,
                        help="Number of identical runs per cache scenario (1-5)")
    parser.add_argument("--render-path", choices=["rov", "rtv"], default="rov")
    parser.add_argument("--reference-capture",
                        help="ROV BMP used to gate RTV visual equivalence")
    parser.add_argument("--disable-gamma-unorm16", action="store_true",
                        help="Test RTV without gamma render targets aliased as UNORM16")
    parser.add_argument("--disable-snorm16-full-range", action="store_true",
                        help="Test RTV with fixed16 render targets limited to SNORM -1..1")
    parser.add_argument("--stability", action="store_true",
                        help="Exercise combat, pause/resume and focus changes during a long soak")
    parser.add_argument("--wait-for-idle", type=int, default=0, metavar="SECONDS",
                        help="Wait for this much Windows input idle time before each run")
    parser.add_argument("--log-level", choices=["debug", "trace"], default="debug",
                        help="Runtime log verbosity; trace includes per-resolve formats")
    parser.add_argument("--exe", default=r"C:\projetos\neverdead\build\n2-neverdead\neverdead.exe")
    parser.add_argument("--game-data", default=r"C:\projetos\NeverDeadxex")
    parser.add_argument("--output-dir", default=r"C:\projetos\neverdead\analysis\n13-benchmarks")
    parser.add_argument("--user-dir", default=r"C:\projetos\neverdead\analysis\n13-benchmarks\user_data")
    args = parser.parse_args()

    args.exe = os.path.abspath(args.exe)
    args.game_data = os.path.abspath(args.game_data)
    args.output_dir = os.path.abspath(args.output_dir)
    args.user_dir = os.path.abspath(args.user_dir)
    if args.reference_capture:
        args.reference_capture = os.path.abspath(args.reference_capture)

    cache_dir = os.path.join(args.output_dir, "shader_cache")

    results_by_scenario = {}
    scenarios = ["cold", "warm"] if args.scenario == "both" else [args.scenario]
    for scenario in scenarios:
        scenario_results = []
        for run_index in range(args.runs):
            label_suffix = "_stability" if args.stability else ""
            label = (f"{scenario}_{args.render_path}{label_suffix}" if args.runs == 1 else
                     f"{scenario}_{args.render_path}_{run_index + 1:02}")
            scenario_results.append(run_after_idle(
                args.wait_for_idle,
                lambda: run_gameplay_benchmark(
                    scenario, args.duration, args.exe, args.game_data, cache_dir,
                    args.user_dir, args.output_dir, label, args.render_path,
                    args.reference_capture, not args.disable_gamma_unorm16,
                    not args.disable_snorm16_full_range, args.stability,
                    bool(args.wait_for_idle), args.log_level)))
        results_by_scenario[scenario] = scenario_results
        if args.runs > 1:
            aggregate = {
                'passed': all(result['performance_gate']['passed'] for result in scenario_results),
                'runs': scenario_results,
                'summary': {
                    'minimum_1_percent_low_fps': min(
                        result['fps']['p1_low'] for result in scenario_results),
                    'maximum_frames_over_50ms': max(
                        result['frametime_ms']['stutters_gt_50ms'] for result in scenario_results),
                    'maximum_p95_frametime_ms': max(
                        result['frametime_ms']['p95'] for result in scenario_results),
                },
            }
            aggregate_path = os.path.join(
                args.output_dir, f"n15_{scenario}_{args.render_path}_repeats.json")
            with open(aggregate_path, 'w', encoding='utf-8') as f:
                json.dump(aggregate, f, indent=2)
            print(f"[{scenario.upper()}] Repeat results saved to: {aggregate_path}")

    cold_res = results_by_scenario.get("cold", [None])[0]
    warm_res = results_by_scenario.get("warm", [None])[0]

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
