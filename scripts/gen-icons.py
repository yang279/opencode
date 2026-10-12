#!/usr/bin/env python3
"""生成占位应用图标（纯标准库，无需 PIL）。

输出到 src-tauri/icons/：32/128/256 PNG、icon.ico、icon.icns，以及 1024 源图。
后续可用 `npx @tauri-apps/cli icon` 重新生成正式图标。
"""
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(__file__), "..", "src-tauri", "icons")


def _png(width, height, rgba):
    def chunk(typ, data):
        return (
            struct.pack(">I", len(data))
            + typ
            + data
            + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = b""
    for y in range(height):
        raw += b"\x00" + rgba[y * width * 4 : (y + 1) * width * 4]
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def _gradient(width, height):
    top = (79, 70, 229)    # indigo-600
    bottom = (124, 58, 237)  # violet-600
    rows = bytearray()
    for y in range(height):
        t = y / max(height - 1, 1)
        r = round(top[0] + (bottom[0] - top[0]) * t)
        g = round(top[1] + (bottom[1] - top[1]) * t)
        b = round(top[2] + (bottom[2] - top[2]) * t)
        row = bytearray()
        for _x in range(width):
            row += bytes((r, g, b, 255))
        rows += row
    return bytes(rows)


def _ico(png_256):
    # ICO 格式：单条 PNG 内嵌条目（256x256）
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png_256), 22)
    return header + entry + png_256


def _icns(pngs):
    # ICNS 格式：'icns' + 总长 + 若干(类型 + 长度 + 数据)
    elems = b""
    for typ, data in pngs:
        elems += typ + struct.pack(">I", 8 + len(data)) + data
    return b"icns" + struct.pack(">I", 8 + len(elems)) + elems


def main():
    os.makedirs(OUT, exist_ok=True)

    sizes = {32: "32x32.png", 128: "128x128.png", 256: "128x128@2x.png"}
    for size, name in sizes.items():
        png = _png(size, size, _gradient(size, size))
        with open(os.path.join(OUT, name), "wb") as fh:
            fh.write(png)
        print("write", name)

    png_1024 = _png(1024, 1024, _gradient(1024, 1024))
    with open(os.path.join(OUT, "icon.png"), "wb") as fh:
        fh.write(png_1024)

    png_256 = _png(256, 256, _gradient(256, 256))
    with open(os.path.join(OUT, "icon.ico"), "wb") as fh:
        fh.write(_ico(png_256))

    with open(os.path.join(OUT, "icon.icns"), "wb") as fh:
        fh.write(_icns(
            [(b"ic07", _png(128, 128, _gradient(128, 128))), (b"ic10", png_1024)]
        ))
    print("write icon.ico / icon.icns / icon.png")


if __name__ == "__main__":
    main()