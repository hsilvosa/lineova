"""Colour utilities: parsing, OKLab interpolation, colormap lookup tables."""

from __future__ import annotations

from functools import lru_cache

import numpy as np

_NAMED = {
    "white": "#ffffff", "black": "#000000", "none": "none", "transparent": "none",
    "red": "#d62728", "blue": "#1f77b4", "green": "#2ca02c", "orange": "#ff7f0e",
    "gray": "#808080", "grey": "#808080",
}


def parse(color: str) -> tuple[float, float, float, float]:
    """Parse ``#rgb``, ``#rrggbb``, ``#rrggbbaa`` or a few names into RGBA floats 0..1."""
    c = _NAMED.get(color.strip().lower(), color.strip())
    if c == "none":
        return (0.0, 0.0, 0.0, 0.0)
    if not c.startswith("#"):
        raise ValueError(f"Unsupported colour {color!r}; use hex like '#2f5bd3'.")
    h = c[1:]
    if len(h) in (3, 4):
        h = "".join(ch * 2 for ch in h)
    if len(h) not in (6, 8):
        raise ValueError(f"Unsupported colour {color!r}.")
    vals = [int(h[i:i + 2], 16) / 255 for i in range(0, len(h), 2)]
    if len(vals) == 3:
        vals.append(1.0)
    return tuple(vals)  # type: ignore[return-value]


def to_hex(rgb) -> str:
    r, g, b = (int(round(min(1.0, max(0.0, float(v))) * 255)) for v in rgb[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def mix(a: str, b: str, t: float) -> str:
    """Linear mix in sRGB (good enough for tints against a background)."""
    ca, cb = parse(a), parse(b)
    return to_hex([ca[i] + (cb[i] - ca[i]) * t for i in range(3)])


def luminance(color: str) -> float:
    r, g, b, _ = parse(color)

    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable_on(fill: str, light: str = "#ffffff", dark: str = "#111111") -> str:
    """Pick the text colour (light or dark) with better contrast on ``fill``."""
    return light if contrast(fill, light) >= contrast(fill, dark) else dark


# --------------------------------------------------------------------------- OKLab

def _srgb_to_linear(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def rgb_to_oklab(rgb: np.ndarray) -> np.ndarray:
    lin = _srgb_to_linear(np.asarray(rgb, dtype=float))
    m1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                   [0.2119034982, 0.6806995451, 0.1073969566],
                   [0.0883024619, 0.2817188376, 0.6299787005]])
    lms = np.cbrt(lin @ m1.T)
    m2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                   [1.9779984951, -2.4285922050, 0.4505937099],
                   [0.0259040371, 0.7827717662, -0.8086757660]])
    return lms @ m2.T


def oklab_to_rgb(lab: np.ndarray) -> np.ndarray:
    m2i = np.array([[1.0, 0.3963377774, 0.2158037573],
                    [1.0, -0.1055613458, -0.0638541728],
                    [1.0, -0.0894841775, -1.2914855480]])
    lms = (np.asarray(lab, dtype=float) @ m2i.T) ** 3
    m1i = np.array([[4.0767416621, -3.3077115913, 0.2309699292],
                    [-1.2684380046, 2.6097574011, -0.3413193965],
                    [-0.0041960863, -0.7034186147, 1.7076147010]])
    return _linear_to_srgb(lms @ m1i.T)


@lru_cache(maxsize=64)
def ramp_lut(stops: tuple[str, ...], n: int = 256) -> np.ndarray:
    """Interpolate colour ``stops`` evenly in OKLab into an ``(n, 3)`` uint8 table."""
    if len(stops) == 1:
        stops = (stops[0], stops[0])
    labs = rgb_to_oklab(np.array([parse(s)[:3] for s in stops]))
    pos = np.linspace(0, 1, len(stops))
    t = np.linspace(0, 1, n)
    out = np.empty((n, 3))
    for k in range(3):
        out[:, k] = np.interp(t, pos, labs[:, k])
    return (oklab_to_rgb(out) * 255 + 0.5).astype(np.uint8)


def ramp_color(stops: tuple[str, ...], t: float) -> str:
    lut = ramp_lut(tuple(stops))
    i = int(round(min(1.0, max(0.0, t)) * (len(lut) - 1)))
    return to_hex(lut[i] / 255)


def rgb_array(colors: list[str]) -> np.ndarray:
    return np.array([parse(c)[:3] for c in colors], dtype=np.float64)
