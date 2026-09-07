"""A small, independent FLAC parser used to check the streams the integration writes.

It only understands what ``FlacWriter`` produces (16-bit VERBATIM subframes,
fixed block size) but verifies every field and both CRCs from the FLAC
specification rather than reusing the encoder's tables.
"""

from __future__ import annotations

import struct
import sys
from array import array
from dataclasses import dataclass

_BLOCK_SIZES = {
    0x1: 192,
    0x2: 576,
    0x3: 1152,
    0x4: 2304,
    0x5: 4608,
    0x8: 256,
    0x9: 512,
    0xA: 1024,
    0xB: 2048,
    0xC: 4096,
    0xD: 8192,
    0xE: 16384,
    0xF: 32768,
}
_SAMPLE_RATES = {
    0x1: 88200,
    0x2: 176400,
    0x3: 192000,
    0x4: 8000,
    0x5: 16000,
    0x6: 22050,
    0x7: 24000,
    0x8: 32000,
    0x9: 44100,
    0xA: 48000,
    0xB: 96000,
}


@dataclass
class FlacStream:
    """What was found in a parsed stream."""

    rate: int
    channels: int
    bits: int
    total_samples: int  # from STREAMINFO, 0 = unknown
    block_size: int
    frames: int
    samples: array  # interleaved 16-bit samples of all frames


def _crc(data: bytes, poly: int, width: int) -> int:
    """Bitwise CRC (no init, no xor-out, MSB first) for verification."""
    crc = 0
    top = 1 << (width - 1)
    mask = (1 << width) - 1
    for byte in data:
        crc ^= byte << (width - 8)
        for _ in range(8):
            crc = ((crc << 1) ^ poly) if crc & top else crc << 1
        crc &= mask
    return crc


def _utf8(data: bytes, pos: int) -> tuple[int, int]:
    lead = data[pos]
    if lead < 0x80:
        return lead, pos + 1
    ones = 0
    while lead & (0x80 >> ones):
        ones += 1
    assert 2 <= ones <= 7, "bad UTF-8 style number"
    value = lead & (0x7F >> ones)
    for i in range(ones - 1):
        byte = data[pos + 1 + i]
        assert byte & 0xC0 == 0x80, "bad continuation byte"
        value = (value << 6) | (byte & 0x3F)
    return value, pos + ones


def parse_flac(data: bytes) -> FlacStream:
    """Parse a complete FLAC stream, asserting on every malformed detail."""
    assert data[:4] == b"fLaC", "missing fLaC marker"
    pos = 4
    info: dict[str, int] | None = None
    while True:
        flags = data[pos]
        length = int.from_bytes(data[pos + 1 : pos + 4], "big")
        body = data[pos + 4 : pos + 4 + length]
        pos += 4 + length
        if flags & 0x7F == 0:
            assert length == 34, "STREAMINFO must be 34 bytes"
            min_block, max_block = struct.unpack(">HH", body[:4])
            assert min_block == max_block, "only fixed block size streams are written"
            packed = int.from_bytes(body[10:18], "big")
            info = {
                "rate": packed >> 44,
                "channels": ((packed >> 41) & 0x7) + 1,
                "bits": ((packed >> 36) & 0x1F) + 1,
                "total": packed & ((1 << 36) - 1),
                "block_size": max_block,
            }
        if flags & 0x80:
            break
    assert info is not None, "no STREAMINFO block"

    samples = array("h")
    frames = 0
    while pos < len(data):
        start = pos
        assert data[pos : pos + 2] == b"\xff\xf8", f"bad sync code in frame {frames}"
        size_code, rate_code = data[pos + 2] >> 4, data[pos + 2] & 0xF
        channel_code, bits_code = data[pos + 3] >> 4, (data[pos + 3] >> 1) & 0x7
        assert data[pos + 3] & 1 == 0, "reserved bit set"
        number, pos = _utf8(data, pos + 4)
        assert number == frames, f"frame number {number} != {frames}"
        if size_code == 0x6:
            count = data[pos] + 1
            pos += 1
        elif size_code == 0x7:
            count = struct.unpack(">H", data[pos : pos + 2])[0] + 1
            pos += 2
        else:
            count = _BLOCK_SIZES[size_code]
        assert count <= info["block_size"]
        rate = info["rate"] if rate_code == 0 else _SAMPLE_RATES[rate_code]
        assert rate == info["rate"]
        assert channel_code <= 7 and channel_code + 1 == info["channels"]
        assert bits_code == 0b100 and info["bits"] == 16, "only 16-bit streams are written"
        assert data[pos] == _crc(data[start:pos], 0x07, 8), f"bad CRC-8 in frame {frames}"
        pos += 1
        channels: list[array] = []
        for _ in range(info["channels"]):
            assert data[pos] == 0x02, "not a VERBATIM subframe"
            pos += 1
            block = array("h", data[pos : pos + 2 * count])
            if sys.byteorder == "little":
                block.byteswap()
            channels.append(block)
            pos += 2 * count
        crc = struct.unpack(">H", data[pos : pos + 2])[0]
        assert crc == _crc(data[start:pos], 0x8005, 16), f"bad CRC-16 in frame {frames}"
        pos += 2
        if len(channels) == 1:
            samples.extend(channels[0])
        else:
            for i in range(count):
                samples.extend(channel[i] for channel in channels)
        frames += 1

    return FlacStream(
        rate=info["rate"],
        channels=info["channels"],
        bits=info["bits"],
        total_samples=info["total"],
        block_size=info["block_size"],
        frames=frames,
        samples=samples,
    )
