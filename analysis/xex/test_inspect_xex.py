import struct
import unittest

from inspect_xex import Reader, basic_blocks


class XexBoundsTests(unittest.TestCase):
    def test_truncated_and_negative_ranges_are_rejected(self):
        reader = Reader(b"\0" * 8)
        for offset, size in [(-1, 4), (0, -1), (6, 4)]:
            with self.subTest(offset=offset, size=size):
                with self.assertRaises(ValueError):
                    reader.take(offset, size)

    def test_basic_block_mapping_retains_zero_holes(self):
        data = struct.pack(">IHH4I", 24, 1, 1, 16, 32, 16, 0) + bytes(32)
        blocks, expanded = basic_blocks(Reader(data), 0, 24)
        self.assertEqual(expanded, 64)
        self.assertEqual(
            [(b["ciphertext_offset"], b["image_offset"]) for b in blocks],
            [(24, 0), (40, 48)],
        )

    def test_malformed_or_incomplete_basic_blocks_are_rejected(self):
        cases = [
            struct.pack(">IHH", 9, 1, 1),
            struct.pack(">IHHII", 16, 1, 1, 16, 0) + bytes(15),
            struct.pack(">IHHII", 16, 1, 1, 16, 0) + bytes(17),
        ]
        for data in cases:
            with self.subTest(size=len(data)):
                with self.assertRaises(ValueError):
                    basic_blocks(Reader(data), 0, 16)


if __name__ == "__main__":
    unittest.main()
