"""Genera le icone PNG dell'app (fiocco di neve bianco su blu). Solo libreria standard."""

import math
import struct
import zlib
from pathlib import Path

BACKGROUND = (0x0B, 0x4F, 0x6C)
FOREGROUND = (0xFF, 0xFF, 0xFF)
SIZES = (180, 192, 512)
OUT_DIR = Path(__file__).resolve().parent.parent / "web" / "icons"


def _segments(size: int) -> list[tuple[float, float, float, float]]:
    center = size / 2
    arm = size * 0.36
    branch = size * 0.13
    segments = []
    for k in range(6):
        angle = math.pi / 3 * k
        dx, dy = math.cos(angle), math.sin(angle)
        segments.append((center, center, center + dx * arm, center + dy * arm))
        bx, by = center + dx * arm * 0.6, center + dy * arm * 0.6
        for side in (-1, 1):
            a = angle + side * math.pi / 4
            segments.append((bx, by, bx + math.cos(a) * branch, by + math.sin(a) * branch))
    return segments


def _distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    vx, vy = x2 - x1, y2 - y1
    t = max(0.0, min(1.0, ((px - x1) * vx + (py - y1) * vy) / (vx * vx + vy * vy)))
    return math.hypot(px - (x1 + t * vx), py - (y1 + t * vy))


def render(size: int) -> bytes:
    half_width = size * 0.03
    segments = _segments(size)
    rows = []
    for y in range(size):
        row = bytearray([0])  # filtro PNG "None"
        for x in range(size):
            d = min(_distance(x + 0.5, y + 0.5, *segment) for segment in segments)
            coverage = max(0.0, min(1.0, half_width + 0.5 - d))
            row.extend(round(b + (f - b) * coverage) for b, f in zip(BACKGROUND, FOREGROUND))
        rows.append(bytes(row))
    return b"".join(rows)


def png(size: int, raw: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8 bit, RGB
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        (OUT_DIR / f"icon-{size}.png").write_bytes(png(size, render(size)))
        print(f"web/icons/icon-{size}.png")
