import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import analysis.profile_n13 as profile
from analysis.profile_n13 import compare_bmp, measure_bmp


def write_bmp(path, red, green, blue, alternate_rgb=None):
    width = height = 8
    row_stride = width * 3
    colors = ((red, green, blue), alternate_rgb)
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            color = colors[(x + y) % 2] if alternate_rgb else colors[0]
            pixels.extend((color[2], color[1], color[0]))
    header = (b"BM" + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54) +
              struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0,
                          len(pixels), 0, 0, 0, 0))
    path.write_bytes(header + bytes(pixels))


class BmpGateTests(unittest.TestCase):
    def test_measures_and_rejects_dark_regression(self):
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.bmp"
            dark = Path(directory) / "dark.bmp"
            write_bmp(reference, 100, 80, 60)
            write_bmp(dark, 20, 16, 12)

            self.assertAlmostEqual(measure_bmp(reference)['average_rgb'][0], 100)
            self.assertTrue(compare_bmp(reference, reference)['passed'])
            self.assertFalse(compare_bmp(reference, dark)['passed'])

    def test_rejects_different_luminance_distribution_with_same_average(self):
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.bmp"
            pattern = Path(directory) / "pattern.bmp"
            write_bmp(reference, 96, 96, 96)
            write_bmp(pattern, 32, 32, 32, alternate_rgb=(160, 160, 160))

            result = compare_bmp(reference, pattern)
            self.assertFalse(result['passed'])
            self.assertGreater(result['luminance_histogram_distance'], 0.2)


class StabilityGateTests(unittest.TestCase):
    def test_memory_slope_is_reported_per_minute(self):
        self.assertAlmostEqual(
            profile.linear_slope_per_minute([0.0, 30.0, 60.0], [100.0, 110.0, 120.0]),
            20.0,
        )

    def test_accepts_exercised_run_and_rejects_dred_fault(self):
        results = {
            'frames_captured': 36000,
            'measurement_window': {'elapsed_seconds': 1800.0, 'rendered_seconds': 1800.0},
            'memory_mb': {'rss_growth': 92.0, 'commit_growth': 97.0,
                          'rss_slope_mb_per_min': 3.1, 'commit_slope_mb_per_min': 3.2},
            'gpu_and_caches': {'shader_cache_files_new': 2, 'shader_cache_bytes_new': 80000},
            'save_persistence': {
                'initial_files': {'ND.sav': {'sha256': 'A'}},
                'final_files': {'ND.sav': {'sha256': 'B'}},
            },
            'stability_actions': {
                'combat': 1,
                'pause_resume': 5,
                'focus_cycles': 3,
                'checkpoint_saves': 2,
            },
            'ppc_and_system': {'total_xma_frames': 1},
            'audio': {'buffer_underruns': 0},
            'log_health': {'fatal_crashes': 0, 'd3d12_errors': 0, 'dred_faults': 0},
        }
        self.assertTrue(profile.evaluate_stability_gate(results, 1800)['passed'])
        results['log_health']['dred_faults'] = 1
        self.assertFalse(profile.evaluate_stability_gate(results, 1800)['passed'])
        results['log_health']['dred_faults'] = 0
        results['audio']['buffer_underruns'] = 1
        self.assertFalse(profile.evaluate_stability_gate(results, 1800)['passed'])
        results['audio']['buffer_underruns'] = 0
        results['stability_actions']['checkpoint_saves'] = 1
        self.assertFalse(profile.evaluate_stability_gate(results, 1800)['passed'])
        results['stability_actions']['checkpoint_saves'] = 2
        results['memory_mb']['rss_slope_mb_per_min'] = 8.1
        self.assertFalse(profile.evaluate_stability_gate(results, 1800)['checks']['bounded_memory_growth'])
        results['memory_mb']['rss_slope_mb_per_min'] = 3.1
        results['gpu_and_caches']['shader_cache_bytes_new'] = 64 * 1024 * 1024 + 1
        self.assertFalse(profile.evaluate_stability_gate(results, 1800)['checks']['bounded_cache_growth'])

    def test_rejects_early_exit_even_with_enough_frames(self):
        results = {
            'frames_captured': 36000,
            'measurement_window': {'elapsed_seconds': 1200.0, 'rendered_seconds': 1200.0},
            'memory_mb': {'rss_growth': 0.0, 'commit_growth': 0.0,
                          'rss_slope_mb_per_min': 0.0, 'commit_slope_mb_per_min': 0.0},
            'gpu_and_caches': {'shader_cache_files_new': 0, 'shader_cache_bytes_new': 0},
            'save_persistence': {
                'initial_files': {'ND.sav': {'sha256': 'A'}},
                'final_files': {'ND.sav': {'sha256': 'B'}},
            },
            'stability_actions': {
                'combat': 1,
                'pause_resume': 5,
                'focus_cycles': 3,
                'checkpoint_saves': 2,
            },
            'ppc_and_system': {'total_xma_frames': 1},
            'audio': {'buffer_underruns': 0},
            'log_health': {'fatal_crashes': 0, 'd3d12_errors': 0, 'dred_faults': 0},
        }
        gate = profile.evaluate_stability_gate(results, 1800)
        self.assertFalse(gate['checks']['completed_duration'])
        self.assertFalse(gate['passed'])

    def test_rejects_frozen_tail_despite_elapsed_time_and_frame_count(self):
        results = {
            'frames_captured': 36000,
            'measurement_window': {'elapsed_seconds': 1800.0, 'rendered_seconds': 1200.0},
            'memory_mb': {'rss_growth': 0.0, 'commit_growth': 0.0,
                          'rss_slope_mb_per_min': 0.0, 'commit_slope_mb_per_min': 0.0},
            'gpu_and_caches': {'shader_cache_files_new': 0, 'shader_cache_bytes_new': 0},
            'save_persistence': {
                'initial_files': {'ND.sav': {'sha256': 'A'}},
                'final_files': {'ND.sav': {'sha256': 'B'}},
            },
            'stability_actions': {
                'combat': 1,
                'pause_resume': 5,
                'focus_cycles': 3,
                'checkpoint_saves': 2,
            },
            'ppc_and_system': {'total_xma_frames': 1},
            'audio': {'buffer_underruns': 0},
            'log_health': {'fatal_crashes': 0, 'd3d12_errors': 0, 'dred_faults': 0},
        }
        gate = profile.evaluate_stability_gate(results, 1800)
        self.assertFalse(gate['checks']['completed_duration'])
        self.assertFalse(gate['passed'])

    def test_rejects_checkpoint_events_without_persisted_save_state(self):
        results = {
            'frames_captured': 36000,
            'measurement_window': {'elapsed_seconds': 1800.0, 'rendered_seconds': 1800.0},
            'memory_mb': {'rss_growth': 0.0, 'commit_growth': 0.0,
                          'rss_slope_mb_per_min': 0.0, 'commit_slope_mb_per_min': 0.0},
            'gpu_and_caches': {'shader_cache_files_new': 0, 'shader_cache_bytes_new': 0},
            'save_persistence': {'initial_files': {}, 'final_files': {}},
            'stability_actions': {
                'combat': 1,
                'pause_resume': 5,
                'focus_cycles': 3,
                'checkpoint_saves': 2,
            },
            'ppc_and_system': {'total_xma_frames': 1},
            'audio': {'buffer_underruns': 0},
            'log_health': {'fatal_crashes': 0, 'd3d12_errors': 0, 'dred_faults': 0},
        }
        gate = profile.evaluate_stability_gate(results, 1800)
        self.assertFalse(gate['checks']['checkpoint_state_persisted'])
        self.assertFalse(gate['passed'])

    def test_rejects_rewritten_save_with_unchanged_content(self):
        results = {
            'frames_captured': 36000,
            'measurement_window': {'elapsed_seconds': 1800.0, 'rendered_seconds': 1800.0},
            'memory_mb': {'rss_growth': 0.0, 'commit_growth': 0.0,
                          'rss_slope_mb_per_min': 0.0, 'commit_slope_mb_per_min': 0.0},
            'gpu_and_caches': {'shader_cache_files_new': 0, 'shader_cache_bytes_new': 0},
            'save_persistence': {
                'initial_files': {'ND.sav': {'sha256': 'A', 'modified_ns': 1}},
                'final_files': {'Renamed.sav': {'sha256': 'A', 'modified_ns': 2}},
            },
            'stability_actions': {
                'combat': 1,
                'pause_resume': 5,
                'focus_cycles': 3,
                'checkpoint_saves': 2,
            },
            'ppc_and_system': {'total_xma_frames': 1},
            'audio': {'buffer_underruns': 0},
            'log_health': {'fatal_crashes': 0, 'd3d12_errors': 0, 'dred_faults': 0},
        }
        gate = profile.evaluate_stability_gate(results, 1800)
        self.assertFalse(gate['checks']['checkpoint_state_persisted'])
        self.assertFalse(gate['passed'])

    def test_observes_save_file_writes_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save = root / 'ND.sav'
            ignored = root / 'cache.bin'
            save.write_bytes(b'one')
            ignored.write_bytes(b'one')
            before = profile.snapshot_save_writes(root)
            save.write_bytes(b'two')
            os.utime(save, ns=(before['ND.sav'] + 1_000_000_000,) * 2)
            ignored.write_bytes(b'two')
            after = profile.snapshot_save_writes(root)
        self.assertNotEqual(before, after)
        self.assertEqual(list(after), ['ND.sav'])

    def test_save_manifest_hashes_only_persistent_save_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'ND.sav').write_bytes(b'save data')
            (root / 'ND.header').write_bytes(b'header data')
            (root / 'cache.bin').write_bytes(b'ignored')
            manifest = profile.snapshot_save_files(root)

        self.assertEqual(set(manifest), {'ND.sav', 'ND.header'})
        self.assertEqual(manifest['ND.sav']['size_bytes'], 9)
        self.assertEqual(
            manifest['ND.sav']['sha256'],
            'AFC86DA5FE946F7F46A082D79B228D23E0EA0EA4014EDBB7031AE453FBD9DEF4',
        )
        self.assertEqual(profile.get_save_content_hashes(manifest), {
            'ND.sav': 'AFC86DA5FE946F7F46A082D79B228D23E0EA0EA4014EDBB7031AE453FBD9DEF4'
        })


class TargetedInputTests(unittest.TestCase):
    def test_save_harness_does_not_use_global_input(self):
        harness = (Path(profile.__file__).parent / 'test_n12_gameplay_save_audio.ps1').read_text()
        self.assertNotIn('SetForegroundWindow', harness)
        self.assertNotIn('SendInput', harness)
        self.assertIn('WaitForIdleSeconds = 300', harness)
        self.assertIn('laptop activity resumed', harness)
        self.assertIn('exit 75', harness)
        self.assertIn('$script:watchdogArmed = $true', harness)
        self.assertIn('[N12InputBridge]::IsForegroundProcess($proc.Id)', harness)
        self.assertIn('Where-Object LastWriteTimeUtc -ge $captureStartedUtc', harness)
        self.assertIn('Local\\NeverDeadGameplayProfiler', harness)
        self.assertIn("$saveReadMarker = 'Read save file:'", harness)
        self.assertIn('SaveFileReadsAfterCampaign = $saveReadsAfterCampaign', harness)
        self.assertIn("$pauseThunkMarker = 'N15 gameplay pause thunk 0x8253B640 reached'", harness)
        self.assertIn('GameplayPauseThunkCallsAfterCampaign = $pauseThunkCallsAfterCampaign',
                      harness)

    def test_save_reopen_runner_uses_soak_user_data_root(self):
        runner = (Path(profile.__file__).parent / 'test_n15_save_reopen.ps1').read_text()
        self.assertIn('$LASTEXITCODE -eq 75', runner)
        self.assertIn('$LASTEXITCODE -ne 0', runner)
        self.assertIn('$soak.save_persistence.user_data_root', runner)
        self.assertIn('-UserDataRoot $userDir', runner)
        self.assertIn('$expectedSaveHash -eq $reopen.SavePersistence.InitialHash', runner)
        self.assertIn('$soak.stability_gate.checks.checkpoint_state_persisted', runner)
        self.assertIn('SaveFileReadsAfterCampaign', runner)
        self.assertIn('GameplayPauseThunkCallsAfterCampaign -gt 0', runner)
        self.assertIn('ContinueVerified = $continueVerified', runner)

    def test_rtv_fixed16_ab_runner_is_idle_guarded(self):
        runner = (Path(profile.__file__).parent / 'run_n15_rtv_fixed16_ab.ps1').read_text()
        self.assertIn('[int]$WaitForIdleSeconds = 900', runner)
        self.assertIn("Name = 'full_range'", runner)
        self.assertIn("Name = 'limited_range'", runner)
        self.assertIn("$arguments += '--disable-snorm16-full-range'", runner)
        self.assertIn("'--wait-for-idle', $WaitForIdleSeconds", runner)
        self.assertIn('$results[1].GameplayGatePassed', runner)
        self.assertIn('$results[1].PerformanceGatePassed', runner)
        self.assertIn('$results[1].MaximumAverageChannelDelta -lt', runner)
        self.assertIn('$results[1].LuminanceHistogramDistance -lt', runner)
        self.assertIn('$results[0].Snorm16FullRange', runner)
        self.assertIn('-not $results[1].Snorm16FullRange', runner)
        self.assertIn('HypothesisSupported = $hypothesisSupported', runner)

    def test_stability_cycle_uses_fresh_soak_for_reopen(self):
        runner = (Path(profile.__file__).parent / 'run_n15_stability_cycle.ps1').read_text()
        self.assertIn('[int]$WaitForIdleSeconds = 900', runner)
        self.assertIn('[ValidateRange(1800, 3600)]', runner)
        self.assertIn("'--stability'", runner)
        self.assertIn('$profileFile.LastWriteTimeUtc -lt $runStartedUtc', runner)
        self.assertIn('$exeFile.LastWriteTimeUtc -lt $newestEvidenceSource.LastWriteTimeUtc', runner)
        self.assertIn("Test-BinaryMarker $exe 'N15 gameplay pause thunk 0x8253B640 reached'", runner)
        self.assertIn("Test-BinaryMarker $runtimeDll 'Read save file:'", runner)
        self.assertIn('-SoakProfilePath $profilePath', runner)
        self.assertIn('$reopen.ContinueVerified', runner)
        self.assertIn('if (-not $passed)', runner)

    def test_pause_diagnostic_preserves_original_thunk(self):
        diagnostic = (Path(profile.__file__).parents[1] / 'src' / 'src' /
                      'neverdead_diagnostics.cpp').read_text()
        cmake = (Path(profile.__file__).parents[1] / 'src' / 'CMakeLists.txt').read_text()
        self.assertIn('REX_FUNC(sub_8253B640)', diagnostic)
        self.assertIn('__imp__sub_8253B640(ctx, base);', diagnostic)
        self.assertIn('src/neverdead_diagnostics.cpp', cmake)

    def test_release_validator_requires_n15_runtime_markers(self):
        validator = (Path(profile.__file__).parent / 'validate_release_zip.ps1').read_text()
        self.assertIn('N15 gameplay pause thunk 0x8253B640 reached', validator)
        self.assertIn('Read save file:', validator)
        self.assertIn("EvidenceMarkers = 'present'", validator)

    def test_input_is_sent_only_to_game_window(self):
        class FakeUser32:
            def __init__(self):
                self.messages = []

            def MapVirtualKeyW(self, vk, _):
                return vk

            def PostMessageW(self, *message):
                self.messages.append(message)

            def keybd_event(self, *_):
                raise AssertionError("global keyboard input must not be used")

        fake = FakeUser32()
        with patch.object(profile, 'user32', fake), patch.object(profile.time, 'sleep'):
            profile.tap_key(123, profile.VK_W)
            profile.hold_key(123, profile.VK_A, 1.0)
            profile.tap_key_while_held(123, profile.VK_Q, profile.VK_E)

        self.assertEqual([message[:3] for message in fake.messages], [
            (123, profile.WM_KEYDOWN, profile.VK_W),
            (123, profile.WM_KEYUP, profile.VK_W),
            (123, profile.WM_KEYDOWN, profile.VK_A),
            (123, profile.WM_KEYUP, profile.VK_A),
            (123, profile.WM_KEYDOWN, profile.VK_Q),
            (123, profile.WM_KEYDOWN, profile.VK_E),
            (123, profile.WM_KEYUP, profile.VK_E),
            (123, profile.WM_KEYUP, profile.VK_Q),
        ])

    def test_input_requires_game_window(self):
        with self.assertRaisesRegex(RuntimeError, "game window"):
            profile.tap_key(None, profile.VK_W)

    def test_waits_until_idle_threshold(self):
        with patch.object(profile, 'get_idle_seconds', side_effect=[1.0, 5.0]), \
             patch.object(profile.time, 'sleep') as sleep:
            profile.wait_for_idle(5)
        sleep.assert_called_once_with(5.0)

    def test_user_activity_stops_background_game(self):
        class FakeProcess:
            def __init__(self):
                self.pid = 99
                self.terminated = False

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

        process = FakeProcess()
        detected = profile.threading.Event()
        fake_user32 = Mock()
        fake_user32.GetForegroundWindow.return_value = 123
        with patch.object(profile, 'get_last_input_tick', return_value=11), \
             patch.object(profile, 'user32', fake_user32):
            profile.stop_process_when_user_returns(process, detected, 10)
        self.assertTrue(process.terminated)
        self.assertTrue(detected.is_set())

    def test_runtime_input_does_not_stop_foreground_game(self):
        class FakeProcess:
            pid = 99

            def __init__(self):
                self.polls = iter([None, 0])
                self.terminated = False

            def poll(self):
                return next(self.polls)

            def terminate(self):
                self.terminated = True

        def set_foreground_pid(_hwnd, pid_pointer):
            pid_pointer._obj.value = 99

        process = FakeProcess()
        detected = profile.threading.Event()
        fake_user32 = Mock()
        fake_user32.GetForegroundWindow.return_value = 123
        fake_user32.GetWindowThreadProcessId.side_effect = set_foreground_pid
        with patch.object(profile, 'get_last_input_tick', return_value=11), \
             patch.object(profile, 'user32', fake_user32), \
             patch.object(profile.time, 'sleep'):
            profile.stop_process_when_user_returns(process, detected, 10)
        self.assertFalse(process.terminated)
        self.assertFalse(detected.is_set())

    def test_user_activity_rearms_the_same_run_after_idle(self):
        benchmark = Mock(side_effect=[
            profile.UserActivityInterrupted("laptop activity resumed"),
            "completed",
        ])
        with patch.object(profile, 'wait_for_idle') as wait:
            result = profile.run_after_idle(300, benchmark)
        self.assertEqual(result, "completed")
        self.assertEqual(wait.call_count, 2)
        self.assertEqual(benchmark.call_count, 2)


class ProfilerMutexTests(unittest.TestCase):
    def test_rejects_a_second_profiler(self):
        class FakeKernel32:
            def __init__(self):
                self.closed = []

            def CreateMutexW(self, *_):
                return 42

            def GetLastError(self):
                return profile.ERROR_ALREADY_EXISTS

            def CloseHandle(self, handle):
                self.closed.append(handle)

        fake = FakeKernel32()
        with patch.object(profile, 'kernel32', fake), \
             self.assertRaisesRegex(RuntimeError, "already running"):
            profile.acquire_profiler_mutex()
        self.assertEqual(fake.closed, [42])


if __name__ == "__main__":
    unittest.main()
