import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import analysis.profile_n13 as profile
from analysis.profile_n13 import compare_bmp, measure_bmp


def write_bmp(path, red, green, blue):
    width = height = 8
    row_stride = width * 3
    pixels = bytes((blue, green, red)) * width * height
    header = (b"BM" + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54) +
              struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0,
                          len(pixels), 0, 0, 0, 0))
    path.write_bytes(header + pixels)


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


class StabilityGateTests(unittest.TestCase):
    def test_memory_slope_is_reported_per_minute(self):
        self.assertAlmostEqual(
            profile.linear_slope_per_minute([0.0, 30.0, 60.0], [100.0, 110.0, 120.0]),
            20.0,
        )

    def test_accepts_exercised_run_and_rejects_dred_fault(self):
        results = {
            'frames_captured': 36000,
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


class TargetedInputTests(unittest.TestCase):
    def test_save_harness_does_not_use_global_input(self):
        harness = (Path(profile.__file__).parent / 'test_n12_gameplay_save_audio.ps1').read_text()
        self.assertNotIn('SetForegroundWindow', harness)
        self.assertNotIn('SendInput', harness)
        self.assertIn('WaitForIdleSeconds = 300', harness)
        self.assertIn('laptop activity resumed', harness)
        self.assertIn('exit 75', harness)
        self.assertIn('Where-Object LastWriteTimeUtc -ge $captureStartedUtc', harness)
        self.assertIn('Local\\NeverDeadGameplayProfiler', harness)

    def test_save_reopen_runner_retries_only_user_activity(self):
        runner = (Path(profile.__file__).parent / 'test_n15_save_reopen.ps1').read_text()
        self.assertIn('$LASTEXITCODE -eq 75', runner)
        self.assertIn('$LASTEXITCODE -ne 0', runner)
        self.assertIn('$first.SavePersistence.FinalHash -eq $second.SavePersistence.InitialHash',
                      runner)

    def test_rtv_fixed16_ab_runner_is_idle_guarded(self):
        runner = (Path(profile.__file__).parent / 'run_n15_rtv_fixed16_ab.ps1').read_text()
        self.assertIn('[int]$WaitForIdleSeconds = 900', runner)
        self.assertIn("Name = 'full_range'", runner)
        self.assertIn("Name = 'limited_range'", runner)
        self.assertIn("$arguments += '--disable-snorm16-full-range'", runner)
        self.assertIn("'--wait-for-idle', $WaitForIdleSeconds", runner)
        self.assertIn('$results[1].GameplayGatePassed', runner)
        self.assertIn('HypothesisSupported = $hypothesisSupported', runner)

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

        self.assertEqual([message[:3] for message in fake.messages], [
            (123, profile.WM_KEYDOWN, profile.VK_W),
            (123, profile.WM_KEYUP, profile.VK_W),
            (123, profile.WM_KEYDOWN, profile.VK_A),
            (123, profile.WM_KEYUP, profile.VK_A),
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
