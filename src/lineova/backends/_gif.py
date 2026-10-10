"""A small GIF89a writer (NumPy palette quantiser, delta frames, LZW in pure Python). No dependencies."""

from __future__ import annotations

import struct

import numpy as np

MAX_UNIQUE = 60_000


def _median_cut(colors: np.ndarray, counts: np.ndarray, n: int) -> np.ndarray:
    """Palette of up to ``n`` colours from unique colours (k, 3) and their pixel counts."""
    boxes = [(np.arange(len(colors)))]
    while len(boxes) < n:
        best, best_score = -1, 0.0
        for i, idx in enumerate(boxes):
            if len(idx) < 2:
                continue
            span = np.ptp(colors[idx], axis=0)
            score = float(span.max()) * float(counts[idx].sum()) ** 0.5
            if score > best_score:
                best, best_score = i, score
        if best < 0:
            break
        idx = boxes.pop(best)
        ch = int(np.argmax(np.ptp(colors[idx], axis=0)))
        order = idx[np.argsort(colors[idx, ch], kind="stable")]
        cum = np.cumsum(counts[order])
        cut = int(np.searchsorted(cum, cum[-1] / 2.0)) + 1
        cut = min(max(cut, 1), len(order) - 1)
        boxes.append(order[:cut])
        boxes.append(order[cut:])
    pal = np.zeros((n, 3), dtype=np.uint8)
    for i, idx in enumerate(boxes):
        w = counts[idx].astype(np.float64)
        pal[i] = np.round((colors[idx] * w[:, None]).sum(axis=0) / w.sum())
    return pal[:len(boxes)]


def _quantise(frames: list, colors: int) -> tuple[np.ndarray, list]:
    """(palette, [index image per frame]) with one palette for the whole animation."""
    packed = [(f[..., 0].astype(np.uint32) << 16) | (f[..., 1].astype(np.uint32) << 8) | f[..., 2].astype(np.uint32)
              for f in frames]
    reduce = 0
    while True:
        mask = np.uint32((((0xFF << reduce) & 0xFF)) * 0x010101)        # drop the low bits of every channel
        keys = [p & mask for p in packed]
        uniq = np.unique(np.concatenate([k.ravel() for k in keys]))
        if len(uniq) <= MAX_UNIQUE or reduce >= 4:
            break
        reduce += 2
    counts = np.zeros(len(uniq), dtype=np.int64)
    for k in keys:
        u, c = np.unique(k, return_counts=True)
        counts[np.searchsorted(uniq, u)] += c
    rgb = np.column_stack(((uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255)).astype(np.float64)
    if len(uniq) <= colors:
        pal = rgb.astype(np.uint8)
        nearest = np.arange(len(uniq))
    else:
        pal = _median_cut(rgb, counts, colors)
        nearest = np.empty(len(uniq), dtype=np.int64)
        pf = pal.astype(np.float64)
        for a in range(0, len(uniq), 4096):
            d = ((rgb[a:a + 4096, None, :] - pf[None, :, :]) ** 2).sum(axis=2)
            nearest[a:a + 4096] = d.argmin(axis=1)
    out = [nearest[np.searchsorted(uniq, k)].astype(np.uint8) for k in keys]
    return pal, out


def _lzw(data: bytes, min_bits: int) -> bytes:
    clear, eoi = 1 << min_bits, (1 << min_bits) + 1
    table: dict = {}
    code_size = min_bits + 1
    next_code = eoi + 1
    out = bytearray()
    acc = nbits = 0

    def put(code: int, size: int) -> None:
        nonlocal acc, nbits
        acc |= code << nbits
        nbits += size
        while nbits >= 8:
            out.append(acc & 255)
            acc >>= 8
            nbits -= 8

    put(clear, code_size)
    prefix = data[0]
    for byte in data[1:]:
        key = (prefix << 8) | byte
        code = table.get(key)
        if code is not None:
            prefix = code
            continue
        put(prefix, code_size)
        table[key] = next_code
        next_code += 1
        if next_code > (1 << code_size) and code_size < 12:
            code_size += 1
        elif next_code >= 4096:
            put(clear, code_size)
            table.clear()
            code_size = min_bits + 1
            next_code = eoi + 1
        prefix = byte
    put(prefix, code_size)
    put(eoi, code_size)
    if nbits:
        out.append(acc & 255)
    return bytes(out)


def _blocks(data: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(data), 255):
        chunk = data[i:i + 255]
        out.append(len(chunk))
        out += chunk
    out.append(0)
    return bytes(out)


def encode(frames: list, delays_cs: list, loop: int = 0, colors: int = 256) -> bytes:
    """Encode RGB uint8 frames (all the same size). ``loop`` is the repeat count (0 = forever, -1 = play once)."""
    h, w = frames[0].shape[:2]
    colors = max(2, min(255, colors - 1))               # one entry is kept for "unchanged" (transparent)
    pal, idx = _quantise(frames, colors)
    transparent = 255
    table = np.zeros((256, 3), dtype=np.uint8)
    table[:len(pal)] = pal
    out = bytearray(b"GIF89a")
    out += struct.pack("<HHBBB", w, h, 0xF7, 0, 0)       # global colour table, 256 entries
    out += table.tobytes()
    if loop >= 0:
        out += b"\x21\xFF\x0BNETSCAPE2.0\x03\x01" + struct.pack("<H", loop) + b"\x00"
    prev = None
    for img, delay in zip(idx, delays_cs):
        if prev is None:
            x0, y0, x1, y1 = 0, 0, w, h
            patch = img
            trans_flag = 0
        else:
            diff = img != prev
            if not diff.any():
                x0 = y0 = 0
                x1 = y1 = 1
                patch = np.array([[transparent]], dtype=np.uint8)
                trans_flag = 1
            else:
                rows, cols = np.flatnonzero(diff.any(axis=1)), np.flatnonzero(diff.any(axis=0))
                y0, y1, x0, x1 = int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1
                patch = np.where(diff[y0:y1, x0:x1], img[y0:y1, x0:x1], transparent).astype(np.uint8)
                trans_flag = 1
        out += b"\x21\xF9\x04" + bytes([(1 << 2) | trans_flag]) + struct.pack("<H", int(delay)) + bytes([transparent]) + b"\x00"
        out += b"\x2C" + struct.pack("<HHHHB", x0, y0, x1 - x0, y1 - y0, 0)
        out += bytes([8]) + _blocks(_lzw(patch.tobytes(), 8))
        prev = img
    out += b"\x3B"
    return bytes(out)
