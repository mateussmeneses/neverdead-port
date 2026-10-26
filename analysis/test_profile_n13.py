import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


class TargetedInputTests(unittest.TestCase):
    def test_save_harness_does_not_use_global_input(self):
        harness = (Path(profile.__file__).parent / 'test_n12_gameplay_save_audio.ps1').read_text()
        self.assertNotIn('SetForegroundWindow', harness)
        self.assertNotIn('SendInput', harness)
        self.assertIn('WaitForIdleSeconds = 300', harness)
        self.assertIn('laptop activity resumed', harness)

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
                self.terminated = False

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

        process = FakeProcess()
        detected = profile.threading.Event()
        with patch.object(profile, 'get_last_input_tick', return_value=11):
            profile.stop_process_when_user_returns(process, detected, 10)
        self.assertTrue(process.terminated)
        self.assertTrue(detected.is_set())


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
