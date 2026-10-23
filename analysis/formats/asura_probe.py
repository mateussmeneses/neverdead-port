#!/usr/bin/env python3
"""Read-only probes for the bounded NeverDead Asura/XCTD layouts."""

from __future__ import annotations

import argparse
import json
import os
import struct
from dataclasses import asdict, dataclass
from typing import BinaryIO, Iterator


ASURA_PREFIX = b"Asura   "
XCTD_MAGIC = b"\x0f\xf5\x12\xed"
FCSR_HEADER_SIZE = 28
MAX_FCSR_NAME_BYTES = 4096


class FormatError(ValueError):
    """Raised when a supported header is malformed or truncated."""


@dataclass(frozen=True)
class XctdHeader:
    flags: int
    segment_count: int
    bits_per_size: int
    compressed_block_size: int
    window_size: int
    table_size: int
    segment_sizes: tuple[int, ...]

    @property
    def uncompressed_size(self) -> int:
        return sum(self.segment_sizes)


@dataclass(frozen=True)
class TxthHeader:
    payload_size: int
    version: int
    flags: int
    payload_offset: int


@dataclass(frozen=True)
class FcsrRecord:
    offset: int
    size: int
    resource_type: int
    subtype: int
    format_id: int
    flags: int
    payload_size: int
    name: str
    payload_offset: int
    payload_magic: str


def _read_exact(stream: BinaryIO, size: int, description: str) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise FormatError(f"truncated {description}: expected {size} bytes, got {len(data)}")
    return data


def _read_packed_sizes(data: bytes, count: int, bits_per_size: int) -> tuple[int, ...]:
    if bits_per_size == 32:
        return struct.unpack(f">{count}I", data[: count * 4])

    sizes: list[int] = []
    bit_offset = 0
    for _ in range(count):
        value = 0
        for bit_index in range(bits_per_size):
            position = bit_offset + bit_index
            value = (value << 1) | (
                (data[position // 8] >> (7 - position % 8)) & 1
            )
        sizes.append(value)
        bit_offset += bits_per_size
    return tuple(sizes)


def parse_xctd_header(stream: BinaryIO, file_size: int) -> XctdHeader:
    """Parse the 16-byte LZXTDECODE header and bounded segment-size table."""
    stream.seek(0)
    header = _read_exact(stream, 16, "XCTD header")
    if header[:4] != XCTD_MAGIC:
        raise FormatError("not an LZXTDECODE (0x0FF512ED) file")

    flags = int.from_bytes(header[12:16], "big")
    segment_count = (flags >> 6) & 0xFFFF
    size_mode = (flags >> 22) & 3
    bits_per_size = (20, 32, 0, 0)[size_mode]
    if segment_count == 0 or bits_per_size == 0:
        raise FormatError(
            f"unsupported XCTD table mode: segments={segment_count}, mode={size_mode}"
        )

    table_size = ((bits_per_size * segment_count + 31) >> 5) * 4
    if 16 + table_size > file_size:
        raise FormatError(
            f"XCTD segment table exceeds file: table ends at {16 + table_size}, "
            f"file size is {file_size}"
        )

    stream.seek(16)
    table = _read_exact(stream, table_size, "XCTD segment-size table")
    segment_sizes = _read_packed_sizes(table, segment_count, bits_per_size)

    return XctdHeader(
        flags=flags,
        segment_count=segment_count,
        bits_per_size=bits_per_size,
        compressed_block_size=0x8000 << ((flags >> 4) & 3),
        window_size=1 << ((flags & 0xF) + 0xF),
        table_size=table_size,
        segment_sizes=segment_sizes,
    )


def parse_txth_header(stream: BinaryIO, file_size: int) -> TxthHeader:
    """Validate the observed single-chunk TXTH envelope, without decoding text."""
    stream.seek(0)
    prefix = _read_exact(stream, 24, "TXTH header")
    if prefix[:8] != ASURA_PREFIX or prefix[8:12] != b"TXTH":
        raise FormatError("not an Asura TXTH file")

    payload_size, version, flags = struct.unpack(">III", prefix[12:24])
    expected_size = 24 + payload_size
    if expected_size != file_size:
        raise FormatError(
            f"TXTH boundary mismatch: header declares {expected_size} bytes, "
            f"file has {file_size}"
        )
    return TxthHeader(
        payload_size=payload_size,
        version=version,
        flags=flags,
        payload_offset=24,
    )


def parse_fcsr_record(
    stream: BinaryIO, offset: int, file_size: int
) -> FcsrRecord:
    """Parse one observed big-endian FCSR resource record without reading its payload."""
    if offset < 8 or offset + FCSR_HEADER_SIZE > file_size:
        raise FormatError(f"FCSR header at {offset} is outside the file")

    stream.seek(offset)
    header = _read_exact(stream, FCSR_HEADER_SIZE, "FCSR record header")
    if header[:4] != b"FCSR":
        raise FormatError(f"expected FCSR at offset {offset}, got {header[:4]!r}")

    size = int.from_bytes(header[4:8], "big")
    if size < FCSR_HEADER_SIZE or offset + size > file_size:
        raise FormatError(
            f"invalid FCSR record size {size} at {offset} for file size {file_size}"
        )

    resource_type, subtype, format_id, flags, payload_size = struct.unpack(
        ">IIIII", header[8:28]
    )
    name_start = offset + FCSR_HEADER_SIZE
    stream.seek(name_start)
    name_bytes = bytearray()
    for _ in range(MAX_FCSR_NAME_BYTES + 1):
        char = stream.read(1)
        if not char:
            raise FormatError(f"unterminated FCSR name at offset {offset}")
        if char == b"\0":
            break
        name_bytes.extend(char)
    else:
        raise FormatError(f"FCSR name exceeds {MAX_FCSR_NAME_BYTES} bytes at {offset}")

    name_end = name_start + len(name_bytes) + 1
    payload_offset = (name_end + 3) & ~3
    if payload_offset > offset + size:
        raise FormatError(f"FCSR name exceeds record at offset {offset}")

    stream.seek(name_end)
    name_padding = _read_exact(
        stream, payload_offset - name_end, "FCSR name alignment"
    )
    if any(name_padding):
        raise FormatError(f"nonzero FCSR name padding at offset {offset}")

    payload_end = payload_offset + payload_size
    record_end = offset + size
    if payload_end > record_end or record_end - payload_end > 3:
        raise FormatError(
            f"FCSR payload does not fit record at {offset}: "
            f"payload end {payload_end}, record end {record_end}"
        )
    stream.seek(payload_end)
    trailing = _read_exact(stream, record_end - payload_end, "FCSR record padding")
    if any(trailing):
        raise FormatError(f"nonzero FCSR payload padding at offset {offset}")

    stream.seek(payload_offset)
    payload_magic = stream.read(min(4, payload_size)).hex()
    return FcsrRecord(
        offset=offset,
        size=size,
        resource_type=resource_type,
        subtype=subtype,
        format_id=format_id,
        flags=flags,
        payload_size=payload_size,
        name=name_bytes.decode("ascii", errors="replace"),
        payload_offset=payload_offset,
        payload_magic=payload_magic,
    )


def iter_fcsr_records(
    stream: BinaryIO, file_size: int
) -> Iterator[FcsrRecord]:
    """Walk the observed texture aggregate and allow its four-byte zero footer."""
    if file_size < 8:
        raise FormatError("file is shorter than the Asura prefix")
    stream.seek(0)
    if _read_exact(stream, 8, "Asura prefix") != ASURA_PREFIX:
        raise FormatError("not an Asura file")

    offset = 8
    while offset + FCSR_HEADER_SIZE <= file_size:
        stream.seek(offset)
        if stream.read(4) != b"FCSR":
            break
        record = parse_fcsr_record(stream, offset, file_size)
        yield record
        offset += record.size

    trailing_size = file_size - offset
    if trailing_size:
        if trailing_size > 4:
            raise FormatError(f"unexpected {trailing_size}-byte trailer at offset {offset}")
        stream.seek(offset)
        trailer = _read_exact(stream, trailing_size, "FCSR trailer")
        if any(trailer):
            raise FormatError(f"nonzero FCSR trailer at offset {offset}")


def probe_file(path: str) -> dict[str, object]:
    file_size = os.path.getsize(path)
    with open(path, "rb") as stream:
        signature = stream.read(8)
        if signature[:4] == XCTD_MAGIC:
            parsed = parse_xctd_header(stream, file_size)
            return {
                "path": path,
                "format": "xctd-lzxtdecode",
                "file_size": file_size,
                "flags": f"0x{parsed.flags:08x}",
                "segment_count": parsed.segment_count,
                "bits_per_size": parsed.bits_per_size,
                "segment_table_bytes": parsed.table_size,
                "compressed_block_size": parsed.compressed_block_size,
                "window_size": parsed.window_size,
                "uncompressed_size_from_table": parsed.uncompressed_size,
                "first_segment_sizes": list(parsed.segment_sizes[:8]),
                "decompressed": False,
            }
        if signature == ASURA_PREFIX:
            stream.seek(8)
            tag = stream.read(4)
            if tag == b"TXTH":
                parsed = parse_txth_header(stream, file_size)
                return {
                    "path": path,
                    "format": "asura-txth-envelope",
                    "file_size": file_size,
                    **asdict(parsed),
                    "payload_decoded": False,
                }
            if tag == b"FCSR":
                first_record = parse_fcsr_record(stream, 8, file_size)
                next_offset = first_record.offset + first_record.size
                stream.seek(next_offset)
                next_tag = stream.read(4)
                if next_tag not in (b"FCSR", b"") and file_size - next_offset > 4:
                    return {
                        "path": path,
                        "format": "asura-fcsr-first-record",
                        "file_size": file_size,
                        "first_record": asdict(first_record),
                        "unsupported_trailing_bytes": file_size - next_offset,
                        "trailing_signature": next_tag.hex(),
                        "payloads_extracted": False,
                    }
                records = list(iter_fcsr_records(stream, file_size))
                payload_bytes = sum(record.payload_size for record in records)
                magic_counts: dict[str, int] = {}
                for record in records:
                    magic_counts[record.payload_magic] = (
                        magic_counts.get(record.payload_magic, 0) + 1
                    )
                return {
                    "path": path,
                    "format": "asura-fcsr-resource-stream",
                    "file_size": file_size,
                    "record_count": len(records),
                    "record_bytes": sum(record.size for record in records),
                    "payload_bytes": payload_bytes,
                    "trailing_bytes": file_size - (
                        records[-1].offset + records[-1].size if records else 8
                    ),
                    "payload_magic_counts": magic_counts,
                    "first_records": [asdict(record) for record in records[:5]],
                    "payloads_extracted": False,
                }
            return {
                "path": path,
                "format": "asura-unsupported-layout",
                "file_size": file_size,
                "tag": tag.decode("ascii", errors="replace"),
            }
        return {
            "path": path,
            "format": "unknown",
            "file_size": file_size,
            "signature": signature.hex(),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="game files to probe read-only")
    args = parser.parse_args()
    results = [probe_file(path) for path in args.paths]
    print(json.dumps(results, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
