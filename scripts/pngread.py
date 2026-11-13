"""Minimal PNG reader (stdlib only - runs under WSL python3 or Windows Python), for measuring
snap() images in pixels. SolidWorks writes 8-bit RGB or 1-8 bit palette PNGs depending on how
many colours the picture has; both are handled (plus grey and RGBA).

    from pngread import read_png, dark_runs
    w, h, rows = read_png(path)           # rows[y][3*x : 3*x+3] = (r, g, b), row 0 at the top
    dark_runs(grey_row(rows, y))          # centres of the black edge lines crossing row y
"""
import struct, zlib
def read_png(path):
    d = open(path, 'rb').read()
    assert d[:8] == b'\x89PNG\r\n\x1a\n', "not a PNG"
    pos, idat, pal = 8, b'', None
    while pos < len(d):
        n, typ = struct.unpack('>I4s', d[pos:pos+8]); body = d[pos+8:pos+8+n]; pos += 12 + n
        if typ == b'IHDR':
            w, h, bit, ct, _, _, il = struct.unpack('>IIBBBBB', body)
        elif typ == b'PLTE': pal = body
        elif typ == b'IDAT': idat += body
    assert il == 0 and (ct == 3 or bit == 8), f"unsupported PNG (bit {bit}, colour {ct}, interlace {il})"
    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    bpp = max(1, chans * bit // 8)                         # filter unit, bytes
    stride = (w * chans * bit + 7) // 8
    raw = zlib.decompress(idat)
    rows, prev, i = [], bytearray(stride), 0
    for _ in range(h):
        f = raw[i]; line = bytearray(raw[i+1:i+1+stride]); i += 1 + stride
        for x in range(stride) if f else ():
            a = line[x-bpp] if x >= bpp else 0; b = prev[x]; c = prev[x-bpp] if x >= bpp else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        if ct == 3:
            per, mask = 8 // bit, (1 << bit) - 1
            idx = [(line[j // per] >> (8 - bit * (j % per + 1))) & mask for j in range(w)]
            rows.append(bytes(v for k in idx for v in pal[3*k:3*k+3]))
        elif ct == 0: rows.append(bytes(v for g in line for v in (g, g, g)))
        elif ct == 4: rows.append(bytes(v for j in range(w) for v in (line[2*j],) * 3))
        elif ct == 6: rows.append(bytes(v for j in range(w) for v in line[4*j:4*j+3]))
        else: rows.append(bytes(line))
    return w, h, rows


def grey_row(rows, y):
    """Red channel of image row y (the renders are grey, so one channel is enough)."""
    return list(rows[y][0::3])


def grey_col(rows, x):
    return [r[3 * x] for r in rows]


def dark_runs(values, threshold=90):
    """Centres (pixel index) of the runs of dark pixels in a row or column - SolidWorks draws
    model edges as ~1 px black lines, faces and background are much lighter."""
    out, start = [], None
    for i, v in enumerate(list(values) + [255]):
        if v < threshold and start is None:
            start = i
        elif v >= threshold and start is not None:
            out.append((start + i - 1) / 2)
            start = None
    return out
