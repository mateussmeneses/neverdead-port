import io
import struct
import unittest

from asura_probe import (
    FormatError,
    iter_fcsr_records,
    parse_txth_header,
    parse_xctd_header,
)


class XctdHeaderTests(unittest.TestCase):
    @staticmethod
    def make_header(flags: int, table: bytes) -> io.BytesIO:
        return io.BytesIO(
            b"\x0f\xf5\x12\xed"
            + b"\x01\x00\x00\x00"
            + b"\x00\x00\x00\x00"
            + struct.pack(">I", flags)
            + table
        )

    def test_reads_big_endian_32_bit_segment_sizes(self) -> None:
        flags = (1 << 22) | (2 << 6) | (2 << 4) | 2
        stream = self.make_header(flags, struct.pack(">II", 0x12345, 0x6789))

        header = parse_xctd_header(stream, 24)

        self.assertEqual(header.segment_sizes, (0x12345, 0x6789))
        self.assertEqual(header.table_size, 8)
        self.assertEqual(header.compressed_block_size, 0x20000)
        self.assertEqual(header.window_size, 1 << 17)

    def test_reads_packed_20_bit_segment_sizes(self) -> None:
        flags = (2 << 6) | 1
        packed_values = (0x12345 << 20) | 0xABCDE
        table = packed_values.to_bytes(5, "big") + b"\0\0\0"
        stream = self.make_header(flags, table)

        header = parse_xctd_header(stream, 24)

        self.assertEqual(header.segment_sizes, (0x12345, 0xABCDE))
        self.assertEqual(header.table_size, 8)

    def test_rejects_table_past_end_of_file(self) -> None:
        flags = (1 << 22) | (2 << 6)
        stream = self.make_header(flags, b"")

        with self.assertRaisesRegex(FormatError, "exceeds file"):
            parse_xctd_header(stream, 16)


class AsuraEnvelopeTests(unittest.TestCase):
    def test_validates_txth_payload_boundary(self) -> None:
        data = (
            b"Asura   TXTH"
            + struct.pack(">III", 3, 2, 0)
            + b"abc"
        )

        parsed = parse_txth_header(io.BytesIO(data), len(data))

        self.assertEqual(parsed.payload_size, 3)
        self.assertEqual(parsed.version, 2)
        self.assertEqual(parsed.payload_offset, 24)

    def test_rejects_txth_length_mismatch(self) -> None:
        data = b"Asura   TXTH" + struct.pack(">III", 3, 2, 0) + b"ab"

        with self.assertRaisesRegex(FormatError, "boundary mismatch"):
            parse_txth_header(io.BytesIO(data), len(data))

    def test_walks_one_fcsr_record_and_zero_footer(self) -> None:
        name = b"\\textures\\test.tga\0"
        name_padding = b"\0" * ((-len(name)) % 4)
        payload = b"DDS "
        payload_offset = 8 + 28 + len(name) + len(name_padding)
        record_size = 28 + len(name) + len(name_padding) + len(payload)
        record = (
            b"FCSR"
            + struct.pack(">IIIII", record_size, 0, 2, 2, 0)
            + struct.pack(">I", len(payload))
            + name
            + name_padding
            + payload
        )
        stream = io.BytesIO(b"Asura   " + record + b"\0\0\0\0")

        records = list(iter_fcsr_records(stream, len(stream.getvalue())))

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].name, "\\textures\\test.tga")
        self.assertEqual(records[0].payload_offset, payload_offset)
        self.assertEqual(records[0].payload_magic, b"DDS ".hex())

    def test_rejects_fcsr_payload_outside_record(self) -> None:
        name = b"x\0\0\0"
        record = (
            b"FCSR"
            + struct.pack(">IIIII", 32, 0, 1, 2, 0)
            + struct.pack(">I", 20)
            + name
        )
        stream = io.BytesIO(b"Asura   " + record)

        with self.assertRaisesRegex(FormatError, "payload does not fit"):
            list(iter_fcsr_records(stream, len(stream.getvalue())))


if __name__ == "__main__":
    unittest.main()
