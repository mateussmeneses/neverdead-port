"""Read-only, source-bound XEX inventory using an already derived private image."""

import argparse
import collections
import csv
import hashlib
import json
import re
import struct
from datetime import datetime, timezone
from pathlib import Path


class Reader:
    def __init__(self, data):
        self.data = data

    def take(self, offset, size):
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise ValueError(f"Out-of-bounds range: {offset:#x}+{size:#x}")
        return self.data[offset:offset + size]

    def unpack(self, fmt, offset):
        return struct.unpack(fmt, self.take(offset, struct.calcsize(fmt)))

    def u32(self, offset, endian=">"):
        return self.unpack(endian + "I", offset)[0]

    def u16(self, offset, endian=">"):
        return self.unpack(endian + "H", offset)[0]


def version(value):
    return f"{value >> 28}.{(value >> 24) & 15}.{(value >> 8) & 65535}.{value & 255}"


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def basic_blocks(xex, ffi, payload_offset):
    size = xex.u32(ffi)
    if size < 8 or (size - 8) % 8:
        raise ValueError("Malformed basic compression table")
    source, target = payload_offset, 0
    blocks = []
    for offset in range(ffi + 8, ffi + size, 8):
        data, zeros = xex.unpack(">II", offset)
        xex.take(source, data)
        blocks.append({
            "descriptor_offset": offset, "ciphertext_offset": source,
            "image_offset": target, "data_size": data, "zero_size": zeros,
        })
        source += data
        target += data + zeros
    if source != len(xex.data):
        raise ValueError("Basic compression blocks do not cover exact payload")
    return blocks, target


def inspect(root, dump_root, image_path):
    files = sorted(p for p in dump_root.rglob("*") if p.is_file())
    if any(p.is_symlink() for p in files):
        raise ValueError("Symlink in dump; explicit scope review required")
    candidates = [p for p in files if p.name.casefold() == "default.xex"]
    if len(candidates) != 1:
        raise ValueError(f"Expected one default.xex; found {len(candidates)}")
    original = candidates[0]
    x = Reader(original.read_bytes())
    image = Reader(image_path.read_bytes())
    if x.take(0, 4) != b"XEX2":
        raise ValueError("Not XEX2")
    sources = {}
    claims = []

    def source(path, start, end):
        path = Path(path)
        absolute = root / path
        key = f"{path}:{start}-{end}"
        if key not in sources:
            sources[key] = {
                "kind": "analysis-source" if path.parts[0] == "analysis" else "reference-source",
                "path": str(path), "lines": [start, end],
                "sha256": digest(absolute),
            }
        return key

    sdk_info = source(r"refs\core\rexglue-sdk\include\rex\system\util\xex2_info.h", 284, 580)
    xenia_info = source(r"refs\reverse-engineering\xenia\src\xenia\kernel\util\xex2_info.h", 279, 588)
    pe_ref = source(r"refs\core\rexglue-sdk\src\system\xex_module.cpp", 740, 833)
    import_ref = source(r"refs\core\rexglue-sdk\src\system\xex_module.cpp", 1059, 1144)
    pdata_ref = source(r"refs\core\rexglue-sdk\src\codegen\phase_register.cpp", 43, 55)
    switch_ref = source(r"refs\core\XenonRecomp\XenonAnalyse\main.cpp", 253, 308)
    decode_ref = source(r"refs\core\rexglue-sdk\src\system\xex_module.cpp", 536, 621)
    loader_header_ref = source(r"refs\reverse-engineering\XEXLoaderWV\XEXLoaderWV\src\main\java\xexloaderwv\XEXHeader.java", 50, 101)
    loader_import_ref = source(r"refs\reverse-engineering\XEXLoaderWV\XEXLoaderWV\src\main\java\xexloaderwv\XEXHeader.java", 213, 271)
    loader_pe_ref = source(r"refs\reverse-engineering\XEXLoaderWV\XEXLoaderWV\src\main\java\xexloaderwv\NTHeader.java", 17, 69)
    old_header_ref = source(r"refs\core\360tools\tools\xex_info.py", 60, 115)
    old_import_ref = source(r"refs\core\360tools\tools\parse_xex_imports.py", 155, 208)
    abi_ref = source(r"refs\core\rexglue-sdk\include\rex\ppc\function.h", 104, 134)
    register_ref = source(r"refs\core\rexglue-sdk\include\rex\ppc\context.h", 43, 54)
    scanner_ref = source(r"analysis\xex\inspect_xex.py", 1, len(Path(__file__).read_text().splitlines()))

    def location(kind, offset, size):
        return {"artifact": kind, "offset": offset, "length": size}

    def field(name, value, evidence, kind="observed", refs=()):
        row = {
            "id": name, "value": value, "classification": kind,
            "evidence": evidence, "source_ids": list(refs),
        }
        claims.append(row)
        return value

    payload, security, header_count = x.u32(8), x.u32(16), x.u32(20)
    field("xex.module_flags", x.u32(4), [location("original", 4, 4)], refs=[sdk_info])
    headers = {}
    header_rows = []
    for index in range(header_count):
        offset = 24 + index * 8
        key, value = x.unpack(">II", offset)
        if key in headers:
            raise ValueError(f"Duplicate optional header {key:#x}")
        headers[key] = value
        header_rows.append({
            "key": f"0x{key:08X}", "value_or_offset": value,
            "evidence": [location("original", offset, 8)], "source_ids": [sdk_info, xenia_info],
        })
    ffi = headers[0x3FF]
    if x.unpack(">HH", ffi + 4) != (1, 1):
        raise ValueError("This investigation expects encrypted basic compression")
    blocks, expanded = basic_blocks(x, ffi, payload)
    if expanded != len(image.data) or expanded != x.u32(security + 4):
        raise ValueError("Derived image length mismatch")
    field("xex.format", "XEX2", [location("original", 0, 4)], refs=[sdk_info])
    field("xex.header_size", payload, [location("original", 8, 4)], refs=[sdk_info])
    field("xex.security_offset", security, [location("original", 16, 4)], refs=[sdk_info])
    field("xex.encryption", {"id": 1, "name": "Normal (AES-CBC)"}, [location("original", ffi + 4, 2)], refs=[sdk_info, decode_ref])
    field("xex.compression", {"id": 1, "name": "Basic (data + zero runs), not LZX"}, [location("original", ffi + 6, 2)], refs=[sdk_info, decode_ref])
    base = field("xex.load_address", x.u32(security + 0x110), [location("original", security + 0x110, 4)], refs=[sdk_info])
    field("xex.image_size", expanded, [location("original", security + 4, 4)], refs=[sdk_info, decode_ref])
    entry_row = next(r for r in header_rows if r["key"] == "0x00010100")
    entry = field("xex.entrypoint", headers[0x10100], entry_row["evidence"], refs=[sdk_info])
    if headers[0x10201] != base:
        raise ValueError("XEX base declarations disagree")
    for name, offset in [("image_flags", 0x10C), ("exports_address", 0x160), ("region_mask", 0x178), ("allowed_media", 0x17C)]:
        field("xex." + name, x.u32(security + offset), [location("original", security + offset, 4)], refs=[sdk_info, xenia_info])
    execution = headers[0x40006]
    for name, offset in [("media_id", 0), ("version", 4), ("base_version", 8), ("title_id", 12), ("savegame_id", 20)]:
        val = x.u32(execution + offset)
        value = {"raw": val, "decoded": version(val)} if "version" in name else val
        field("execution." + name, value, [location("original", execution + offset, 4)], refs=[sdk_info, xenia_info])
    field("execution.platform_table_discs", list(x.unpack(">4B", execution + 16)), [location("original", execution + 16, 4)], refs=[sdk_info])
    field("execution.update_status", {
        "version_equals_base": x.u32(execution + 4) == x.u32(execution + 8),
        "update_filename_candidates": [
            str(p.relative_to(dump_root)) for p in files
            if p.suffix.casefold() == ".xexp" or re.match(r"(?i)^tu(?:[0-9._ -]|$)", p.name)
        ],
        "official_tu_number": None, "authenticity_verified": False,
    }, [location("original", execution + 4, 8)], "inferred", [sdk_info])
    pe_name = headers[0x183FF]
    field("xex.original_pe_name", x.take(pe_name + 4, x.u32(pe_name) - 4).split(b"\0")[0].decode("ascii"),
          [location("original", pe_name, x.u32(pe_name))], refs=[sdk_info])
    system_row = next(r for r in header_rows if r["key"] == "0x00030000")
    field("xex.system_flags", headers[0x30000], system_row["evidence"], refs=[sdk_info])
    tls = headers[0x20104]
    field("xex.tls", dict(zip(["slot_count", "raw_data_address", "data_size", "raw_data_size"], x.unpack(">4I", tls))), [location("original", tls, 16)], refs=[sdk_info])
    stack_row = next(r for r in header_rows if r["key"] == "0x00020200")
    field("xex.default_stack", headers[0x20200], stack_row["evidence"], refs=[sdk_info])
    field("xex.optional_heap_header", None, [location("original", 24, header_count * 8)], "observed", [sdk_info])

    page_rows = []
    page_size = 4096 if x.u32(security + 0x10C) & 0x10000000 else 65536
    page_offset = 0
    for index in range(x.u32(security + 0x180)):
        offset = security + 0x184 + index * 24
        desc = x.u32(offset)
        size = (desc >> 4) * page_size
        actual = hashlib.sha1(image.take(page_offset, size)).digest()
        page_rows.append({
            "type": desc & 15, "pages": desc >> 4, "image_offset": page_offset,
            "size": size, "digest_matches": actual == x.take(offset + 4, 20),
            "evidence": [location("original", offset, 24), location("derived", page_offset, size)],
            "source_ids": [sdk_info],
        })
        page_offset += size
    if page_offset != expanded:
        raise ValueError("Page descriptors do not cover expanded image")

    pe = image.u32(0x3C, "<")
    if image.take(0, 2) != b"MZ" or image.take(pe, 4) != b"PE\0\0":
        raise ValueError("Invalid PE signatures")
    machine, nsections, timestamp, symbols, symbol_count, optsize, characteristics = image.unpack("<HHIIIHH", pe + 4)
    opt = pe + 24
    if machine != 0x1F2 or optsize != 224 or image.u16(opt, "<") != 0x10B:
        raise ValueError("Unexpected PE32 POWERPCBE layout")
    field("pe.coff", {
        "machine": machine, "machine_name": "IMAGE_FILE_MACHINE_POWERPCBE",
        "sections": nsections, "timestamp_raw": timestamp,
        "timestamp_utc": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
        "symbol_table_offset": symbols, "symbol_count": symbol_count,
        "characteristics": characteristics, "optional_header_size": optsize,
    }, [location("derived", pe + 4, 20)], refs=[pe_ref])
    for name, offset, size in [
        ("entry_rva", 16, 4), ("image_base", 28, 4), ("section_alignment", 32, 4),
        ("file_alignment", 36, 4), ("size_of_image", 56, 4),
        ("size_of_headers", 60, 4), ("subsystem", 68, 2),
        ("stack_reserve", 72, 4), ("stack_commit", 76, 4),
        ("heap_reserve", 80, 4), ("heap_commit", 84, 4),
    ]:
        value = image.u32(opt + offset, "<") if size == 4 else image.u16(opt + offset, "<")
        field("pe." + name, value, [location("derived", opt + offset, size)], refs=[pe_ref])
    if base + image.u32(opt + 16, "<") != entry:
        raise ValueError("PE and XEX entrypoints disagree")

    sections = []
    for index in range(nsections):
        offset = opt + optsize + index * 40
        name = image.take(offset, 8).split(b"\0")[0].decode("ascii")
        vsize, rva, rawsize, rawptr, reloc, lines, nreloc, nlines, flags = image.unpack("<6I2HI", offset + 8)
        image.take(rva, vsize)
        sections.append({
            "name": name, "rva": rva, "va": base + rva, "virtual_size": vsize,
            "legacy_raw_offset": rawptr, "legacy_raw_size": rawsize,
            "flags": flags, "executable": bool(flags & 0x20000000),
            "writable": bool(flags & 0x80000000),
            "evidence": [location("derived", offset, 40)], "source_ids": [pe_ref],
        })
    executable = [s for s in sections if s["executable"]]

    def is_code(address):
        return any(s["va"] <= address < s["va"] + s["virtual_size"] for s in executable)

    dirs = []
    for index in range(image.u32(opt + 92, "<")):
        offset = opt + 96 + index * 8
        rva, size = image.unpack("<II", offset)
        if size:
            image.take(rva, size)
        dirs.append({
            "index": index, "rva": rva, "size": size,
            "evidence": [location("derived", offset, 8)], "source_ids": [pe_ref],
        })
    field("xex.exports", {
        "security_export_va": x.u32(security + 0x160),
        "pe_export_directory": {"rva": dirs[0]["rva"], "size": dirs[0]["size"]},
        "exports_by_name_header_present": 0xE10402 in headers,
    }, [location("original", security + 0x160, 4), *dirs[0]["evidence"]],
        refs=[sdk_info, pe_ref])
    field("architecture.abi", {
        "code_and_data_endianness": "big-endian; PE metadata is little-endian",
        "guest_addresses": "32-bit virtual addresses; not an assertion of 32-bit GPR width",
        "calling_convention": "Xbox PPC: r1 stack, LR saved across calls, r3 argument/result observed; SDK translates r3-r10 integer arguments and uses 64-bit GPR storage",
        "scope": "Header/instruction evidence and SDK ABI reference, not complete per-function signature recovery",
    }, [location("derived", pe + 4, 2), location("derived", entry - base, 160)],
        "inferred", [abi_ref, register_ref, pe_ref])

    export_maps = {}
    for module in ("xboxkrnl", "xam", "xbdm"):
        paths = [
            root / rf"refs\core\rexglue-sdk\src\kernel\{module}\export_table.inc",
            root / rf"refs\reverse-engineering\xenia\src\xenia\kernel\{module}\{module}_table.inc",
        ]
        for path in paths:
            if not path.is_file():
                continue
            key = "sdk" if "rexglue-sdk" in str(path) else "xenia"
            records = {}
            for line, text in enumerate(path.read_text().splitlines(), 1):
                match = re.search(r"XE_EXPORT\(\s*\w+,\s*(0x[\dA-Fa-f]+),\s*(\w+),\s*(\w+)", text)
                if match:
                    ordinal, name, typ = match.groups()
                    records[int(ordinal, 16)] = {
                        "name": name, "type": typ,
                        "source_id": source(path.relative_to(root), line, line),
                    }
            export_maps[module, key] = records
    stubs = {}
    for path in (root / r"refs\core\rexglue-sdk\src\kernel").rglob("*.cpp"):
        for line, text in enumerate(path.read_text().splitlines(), 1):
            match = re.search(r"REX_EXPORT_STUB\(__imp__(\w+)\)", text)
            if match:
                stubs[match[1]] = source(path.relative_to(root), line, line)

    imp = headers[0x103FF]
    total, stringsize, libcount = x.unpack(">III", imp)
    stringdata = x.take(imp + 12, stringsize)
    names = [s.decode("ascii") for s in stringdata.split(b"\0") if s]
    libraries = []
    pos = imp + 12 + stringsize
    for index in range(libcount):
        size = x.u32(pos)
        x.take(pos, size)
        libid, ver, minver, nameindex, count = x.unpack(">IIIHH", pos + 24)
        if nameindex >= len(names) or size != 40 + count * 4:
            raise ValueError("Invalid import library structure")
        name = names[nameindex]
        module = name.split(".")[0].casefold()
        imports = {}
        rawrecords = []
        for n in range(count):
            off = pos + 40 + n * 4
            address = x.u32(off)
            value = image.u32(address - base)
            typ, ordinal = value >> 24, value & 65535
            if typ not in (0, 1):
                raise ValueError("Invalid import record type")
            evidence = [location("original", off, 4), location("derived", address - base, 4)]
            row = imports.setdefault(ordinal, {
                "ordinal": ordinal, "value_slot_va": None, "thunk_va": None,
                "evidence": [], "source_ids": [import_ref],
            })
            slot = "value_slot_va" if typ == 0 else "thunk_va"
            if row[slot] is not None:
                raise ValueError("Duplicate import type for ordinal")
            row[slot] = address
            row["evidence"].extend(evidence)
            rawrecords.append({"address": address, "type": typ, "ordinal": ordinal, "evidence": evidence})
        for ordinal, row in imports.items():
            sdk = export_maps.get((module, "sdk"), {}).get(ordinal)
            xe = export_maps.get((module, "xenia"), {}).get(ordinal)
            row["sdk_export"] = sdk
            row["xenia_export"] = xe
            row["name"] = sdk["name"] if sdk else None
            row["sdk_stub_declaration"] = stubs.get(row["name"])
            row["name_agrees_with_xenia"] = sdk["name"] == xe["name"] if sdk and xe else None
        libraries.append({
            "name": name, "id": libid, "version": version(ver), "minimum_version": version(minver),
            "record_count": count, "imports": sorted(imports.values(), key=lambda r: r["ordinal"]),
            "raw_records": rawrecords, "evidence": [location("original", pos, size)],
            "source_ids": [import_ref, sdk_info, xenia_info],
        })
        pos += size
    if pos != imp + total:
        raise ValueError("Import block not consumed exactly")

    static = []
    libpos = headers[0x200FF]
    libsize = x.u32(libpos)
    if (libsize - 4) % 16:
        raise ValueError("Malformed static library table")
    for offset in range(libpos + 4, libpos + libsize, 16):
        name = x.take(offset, 8).split(b"\0")[0].decode("ascii").strip()
        major, minor, build, approval, qfe = x.unpack(">HHHBB", offset + 8)
        static.append({
            "name": name, "version": f"{major}.{minor}.{build}.{qfe}",
            "approval_byte": approval, "evidence": [location("original", offset, 16)],
            "source_ids": [sdk_info],
        })

    pdata_dir = dirs[3]
    if pdata_dir["size"] % 8:
        raise ValueError("Malformed PDATA length")
    pdata = []
    for offset in range(pdata_dir["rva"], pdata_dir["rva"] + pdata_dir["size"], 8):
        address, flags = image.unpack(">II", offset)
        pdata.append({
            "va": address, "length": ((flags >> 8) & 0x3FFFFF) * 4,
            "prolog_instructions": flags & 255, "exception_flag": bool(flags >> 31),
            "thirty_two_bit_flag": bool(flags & 0x40000000), "start_in_executable_section": is_code(address),
            "evidence": [location("derived", offset, 8)], "source_ids": [pdata_ref],
        })

    reloc_dir = dirs[5]
    relocation_attempts = []
    for endian in (">", "<"):
        offset, end = reloc_dir["rva"], reloc_dir["rva"] + reloc_dir["size"]
        counts = collections.Counter()
        error = None
        while offset < end:
            page, size = image.unpack(endian + "II", offset)
            if page % 4096 or page >= expanded or size < 8 or size % 2 or offset + size > end:
                error = {"offset": offset, "page_rva": page, "block_size": size, "reason": "Invalid PE base-relocation block"}
                break
            for p in range(offset + 8, offset + size, 2):
                counts[image.u16(p, endian) >> 12] += 1
            offset += size
        relocation_attempts.append({
            "endianness": endian, "complete": error is None and offset == end,
            "types": dict(counts), "error": error,
            "evidence": [location("derived", reloc_dir["rva"], min(8, reloc_dir["size"]))],
        })

    indirect = []
    islands = []
    tables = []
    branch_counts = collections.Counter()
    memory_counts = collections.Counter()
    by_thunk = {
        row["thunk_va"]: row
        for lib in libraries for row in lib["imports"] if row["thunk_va"] is not None
    }
    for row in by_thunk.values():
        row["direct_branch_sites"] = []

    def op(word):
        major = word >> 26
        if major == 15 and (word >> 16) & 31 == 0:
            return "lis"
        if major == 14:
            return "addi"
        if major == 21:
            return "rlwinm"
        if word & 0xFC1FFFFF == 0x7C0903A6:
            return "mtctr"
        if word == 0x4E800420:
            return "bctr"
        if major == 31:
            return {23: "lwzx", 87: "lbzx", 279: "lhzx", 266: "add"}.get((word >> 1) & 1023)
        return None

    patterns = {
        "absolute": ["lis", "addi", "rlwinm", "lwzx", "mtctr", "bctr"],
        "absolute_interleaved": ["lis", "rlwinm", "addi", "lwzx", "mtctr", "bctr"],
        "computed": ["lis", "addi", "lbzx", "rlwinm", "lis", "addi", "add", "mtctr", "bctr"],
        "byteoffset": ["lis", "addi", "lbzx", "lis", "addi", "add", "mtctr", "bctr"],
        "shortoffset": ["lis", "addi", "rlwinm", "lhzx", "lis", "addi", "add", "mtctr", "bctr"],
    }
    for section in executable:
        start = section["rva"]
        size = section["virtual_size"] // 4 * 4
        words = list(struct.unpack(f">{size // 4}I", image.take(start, size)))
        names = [op(w) for w in words]
        for index, word in enumerate(words):
            offset = start + index * 4
            va = base + offset
            major = word >> 26
            if major == 18:
                branch_counts["direct_bl" if word & 1 else "direct_b"] += 1
                displacement = signed(word & 0x03FFFFFC, 26)
                target = (displacement if word & 2 else va + displacement) & 0xFFFFFFFF
                if target in by_thunk:
                    by_thunk[target]["direct_branch_sites"].append({
                        "va": va, "link": bool(word & 1),
                        "evidence": [location("derived", offset, 4)],
                    })
            if major in (32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 58, 62):
                ra = (word >> 16) & 31
                memory_counts[f"base_r{ra}"] += 1
            if word in (0x4E800420, 0x4E800421):
                indirect.append({
                    "va": va, "kind": "bctrl" if word & 1 else "bctr",
                    "evidence": [location("derived", offset, 4)],
                })
            if index + 4 <= len(words) and names[index] == "lis" and names[index + 2:index + 4] == ["mtctr", "bctr"]:
                a, b, c, _ = words[index:index + 4]
                reg = (a >> 21) & 31
                addi = b >> 26 == 14 and (b >> 21) & 31 == reg and (b >> 16) & 31 == reg
                ori = b >> 26 == 24 and (b >> 21) & 31 == reg and (b >> 16) & 31 == reg
                if (addi or ori) and (c >> 21) & 31 == reg:
                    target = (((a & 65535) << 16) + signed(b & 65535, 16)) & 0xFFFFFFFF if addi else ((a & 65535) << 16) | (b & 65535)
                    islands.append({
                        "va": va, "target": target, "target_in_code": is_code(target),
                        "classification": "pattern_candidate_not_cfg_proven",
                        "evidence": [location("derived", offset, 16)],
                    })
            for kind, pattern in patterns.items():
                if names[index:index + len(pattern)] != pattern:
                    continue
                low_index = 2 if kind == "absolute_interleaved" else 1
                table_va = (((words[index] & 65535) << 16) + signed(words[index + low_index] & 65535, 16)) & 0xFFFFFFFF
                bound_index = next((j for j in range(index - 1, max(-1, index - 33), -1) if words[j] >> 26 == 10), None)
                count = (words[bound_index] & 65535) + 1 if bound_index is not None else None
                targets = None
                if count is not None and count <= 4096:
                    width = 4 if kind.startswith("absolute") else 2 if kind == "shortoffset" else 1
                    table_offset = table_va - base
                    if 0 <= table_offset <= expanded - count * width:
                        vals = [int.from_bytes(image.take(table_offset + n * width, width), "big") for n in range(count)]
                        if kind.startswith("absolute"):
                            targets = vals
                        else:
                            second = 4 if kind in ("computed", "shortoffset") else 3
                            target_base = (((words[index + second] & 65535) << 16) + signed(words[index + second + 1] & 65535, 16)) & 0xFFFFFFFF
                            shift = (words[index + 3] >> 11) & 31 if kind == "computed" else 0
                            targets = [(target_base + (v << shift)) & 0xFFFFFFFF for v in vals]
                tables.append({
                    "va": va, "kind": kind, "table_va_candidate": table_va,
                    "case_count_candidate": count, "targets_candidate": targets,
                    "all_candidate_targets_in_code": all(map(is_code, targets)) if targets else None,
                    "classification": "heuristic_requires_register_bounds_and_cfg_validation",
                    "evidence": [location("derived", offset, len(pattern) * 4)],
                    "source_ids": [switch_ref, scanner_ref],
                })

    inventory = [{
        "path": str(p.relative_to(dump_root)), "size": p.stat().st_size,
        "sha256": digest(p), "source": "read-only file enumeration and hashing",
    } for p in files]
    result = {
        "schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
        "original": {
            "path": str(original), "size": len(x.data),
            "sha256": hashlib.sha256(x.data).hexdigest(), "sha1": hashlib.sha1(x.data).hexdigest(),
        },
        "derived": {
            "path": str(image_path), "size": expanded, "sha256": hashlib.sha256(image.data).hexdigest(),
            "layout": "loaded XEX image: offset=VA-base, NOT standard PE raw-file layout",
            "derivation": "AES-CBC using existing local reference; continuous ciphertext chain, basic data/zero runs; no key bytes retained",
            "adapter": str(Path(__file__).relative_to(root).with_name("decode-for-analysis.ps1")),
            "source_ids": [decode_ref], "blocks": blocks,
        },
        "sources": sources, "claims": claims, "optional_headers": header_rows,
        "parser_comparison": [
            {
                "parser": "ReXGlue", "mode": "source-inspection, not execution",
                "finding": "Header IDs, basic block reconstruction, PE32 LE metadata, BE import-record dereferencing and ordinal pairing used as reference.",
                "source_ids": [sdk_info, decode_ref, pe_ref, import_ref],
            },
            {
                "parser": "Xenia", "mode": "source-inspection, not execution",
                "finding": "XEX structures/IDs agree; all 269 imported symbol names agree between the local SDK and Xenia ordinal tables.",
                "source_ids": [xenia_info],
                "evidence": "import_libraries[*].imports[*].sdk_export/xenia_export",
            },
            {
                "parser": "XEXLoaderWV", "mode": "source-inspection, not execution",
                "finding": "Reads BE XEX/records and LE PE; import loader modifies its in-memory thunk bytes, and pairs type 1 with preceding type 0 rather than using the SDK ordinal map. Never use modified analysis bytes as original bytes.",
                "source_ids": [loader_header_ref, loader_import_ref, loader_pe_ref],
            },
            {
                "parser": "360tools xex_info.py", "mode": "executed, exit 0, incorrect semantic fields",
                "finding": "Reports entry=0x200 from system flags; labels execution info as TLS, stack as heap, original PE name as address.",
                "source_ids": [old_header_ref],
                "log": {"path": r"logs\n1-360tools-xex-info.log", "sha256": digest(root / r"logs\n1-360tools-xex-info.log")},
            },
            {
                "parser": "360tools parse_xex_imports.py", "mode": "executed, exit 0, incorrect ordinals",
                "finding": "Uses address low bits as ordinal without dereferencing the decrypted image; reports 1536 instead of XNotifyGetNext ordinal 651 for the first xam import; version split is also incorrect.",
                "source_ids": [old_import_ref],
                "log": {"path": r"logs\n1-360tools-imports.log", "sha256": digest(root / r"logs\n1-360tools-imports.log")},
            },
        ],
        "tooling": {
            "parser_path": str(Path(__file__).relative_to(root)),
            "parser_sha256": digest(Path(__file__)),
            "decode_adapter_sha256": digest(Path(__file__).with_name("decode-for-analysis.ps1")),
            "reference_pins": list(csv.DictReader(
                (root / "references.csv").read_text(encoding="utf-8-sig").splitlines()
            )),
        },
        "page_descriptors": page_rows, "sections": sections, "pe_directories": dirs,
        "import_libraries": libraries, "static_libraries": static,
        "pdata": {
            "count": len(pdata), "exception_flag_count": sum(r["exception_flag"] for r in pdata),
            "non_code_start_count": sum(not r["start_in_executable_section"] for r in pdata),
            "entries": pdata,
        },
        "relocation_directory_attempts": relocation_attempts,
        "ppc_scan": {
            "scope": "4-byte aligned words only in the three executable PE sections; may include embedded data",
            "branches": dict(branch_counts), "memory_base_register_counts": dict(memory_counts),
            "indirect_sites": indirect, "branch_island_candidates": islands, "jump_table_candidates": tables,
        },
        "dump_inventory": inventory,
        "limitations": [
            "No execution, codegen, build, RSA authentication or official dump/TU catalog comparison.",
            "Source comparisons are not runs of the compiled ReXGlue, Xenia or Ghidra loaders.",
            "REA rejected XEX and derived POWERPCBE PE; no native REA session opened.",
            "Opcode-pattern candidates are not exhaustive CFG, function-boundary or indirect-target analysis.",
            "Page SHA1 equality is an exploratory hash comparison, not an authenticated XEX integrity verdict.",
            "Memory-request headers do not establish total RAM/VRAM demand.",
            "No keys, AES session material, assets, binary payloads or private PDB paths are included.",
        ],
    }
    if hashlib.sha256(original.read_bytes()).hexdigest() != result["original"]["sha256"]:
        raise ValueError("Original changed during analysis")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump-root", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists():
        raise FileExistsError("Refusing to replace an existing inventory")
    result = inspect(root, args.dump_root, args.image)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "original": result["original"], "derived_sha256": result["derived"]["sha256"],
        "sections": len(result["sections"]), "imports": {lib["name"]: len(lib["imports"]) for lib in result["import_libraries"]},
        "pdata_count": result["pdata"]["count"], "exception_flag_count": result["pdata"]["exception_flag_count"],
        "branch_islands": len(result["ppc_scan"]["branch_island_candidates"]),
        "jump_tables": len(result["ppc_scan"]["jump_table_candidates"]),
        "page_hashes_matching": sum(p["digest_matches"] for p in result["page_descriptors"]),
        "dump_files": len(result["dump_inventory"]), "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
