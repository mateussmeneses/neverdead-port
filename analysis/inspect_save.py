import struct
from pathlib import Path

header_path = Path("build/n2-neverdead/n10-user-20261023-120813/B13EBABEBABEBABE/4B4E081F/Headers/00000001/ND.header")
sav_path = Path("build/n2-neverdead/n10-user-20261023-120813/B13EBABEBABEBABE/4B4E081F/00000001/ND/ND.sav")

print(f"Header exists: {header_path.exists()} (size: {header_path.stat().st_size} bytes)")
print(f"Sav exists:    {sav_path.exists()} (size: {sav_path.stat().st_size} bytes)")

with open(header_path, "rb") as f:
    hdata = f.read()

# XCONTENT_DATA:
# be<uint32_t> device_id; (0..4)
# be<XContentType> content_type; (4..8)
# char16_t display_name[128]; (8..264)
# char file_name[42]; (264..306)
# uint8_t padding[2]; (306..308)
# be<uint64_t> xuid; (308..316)
# be<uint32_t> title_id; (316..320)

dev_id, ctype = struct.unpack(">II", hdata[0:8])
display_raw = hdata[8:264]
# Byte swap each 16-bit word from BE to LE for utf-16le decoding
display_swapped = bytes([b for i in range(0, len(display_raw), 2) for b in (display_raw[i+1], display_raw[i])])
display_name = display_swapped.decode("utf-16le", errors="ignore").rstrip("\x00")
file_name = hdata[264:306].decode("ascii", errors="ignore").rstrip("\x00")
xuid, title_id = struct.unpack(">QI", hdata[308:320])

print(f"Device ID:     {dev_id:#010x} (HDD={1:#010x})")
print(f"Content Type:  {ctype:#x} (kSavedGame=1)")
print(f"Display Name:  '{display_name}'")
print(f"File Name:     '{file_name}'")
print(f"XUID:          {xuid:#018x}")
print(f"Title ID:      {title_id:#010x}")

with open(sav_path, "rb") as f:
    shead = f.read(64)
print(f"Save File magic/header (first 32 bytes hex): {shead[:32].hex()}")
print(f"Save File ASCII preview: {bytes([b if 32 <= b <= 126 else 46 for b in shead[:32]]).decode('ascii')}")
