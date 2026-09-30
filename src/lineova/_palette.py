"""Colour science for palettes: OKLab/OKLCH, colour-vision-deficiency simulation, checks, generation.

Used by the theme builder (``lv.themes.from_brand``) and by ``lv.themes.check_palette``. The checks
follow common data-visualisation practice:

* lightness band - categorical colours sit at similar lightness so none dominates;
* chroma floor - no greys posing as categories;
* CVD separation - adjacent colours stay apart for protan, deutan and tritan vision (ΔE OKLab × 100);
* normal-vision floor - adjacent colours are clearly different for everyone;
* contrast - each colour stands out from the background (WCAG ratio >= 3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

BAND = {"light": (0.43, 0.77), "dark": (0.48, 0.67)}
CHROMA_MIN = 0.10
CVD_MIN = 8.0
NORMAL_MIN = 15.0
CONTRAST_MIN = 3.0

# Machado, Oliveira & Fernandes (2009), severity 1.0, applied to linear RGB
_CVD = {
    "protan": np.array([[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]]),
    "deutan": np.array([[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]]),
    "tritan": np.array([[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]]),
}


def _hex_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def _rgb_hex(rgb) -> str:
    r, g, b = (int(round(min(1.0, max(0.0, float(v))) * 255)) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _to_linear(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _to_srgb(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.abs(c) ** (1 / 2.4) - 0.055)


def _lin_oklab(lin):
    l_ = np.cbrt(0.4122214708 * lin[0] + 0.5363325363 * lin[1] + 0.0514459929 * lin[2])
    m_ = np.cbrt(0.2119034982 * lin[0] + 0.6806995451 * lin[1] + 0.1073969566 * lin[2])
    s_ = np.cbrt(0.0883024619 * lin[0] + 0.2817188376 * lin[1] + 0.6299787005 * lin[2])
    return np.array([0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
                     1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
                     0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_])


def _oklab_lin(lab):
    L, a, b = lab
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return np.array([4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
                     -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
                     -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s])


def oklab(hex_color: str) -> np.ndarray:
    return _lin_oklab(_to_linear(_hex_rgb(hex_color)))


def oklch(hex_color: str) -> tuple[float, float, float]:
    L, a, b = oklab(hex_color)
    return float(L), float(math.hypot(a, b)), float(math.degrees(math.atan2(b, a)) % 360)


def from_oklch(L: float, C: float, h: float) -> str:
    """OKLCH -> hex, reducing chroma until the colour fits in sRGB."""
    for _ in range(40):
        a, b = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
        lin = _oklab_lin((L, a, b))
        if np.all(lin >= -1e-4) and np.all(lin <= 1 + 1e-4):
            return _rgb_hex(_to_srgb(np.clip(lin, 0, 1)))
        C *= 0.93
    return _rgb_hex(_to_srgb(np.clip(_oklab_lin((L, 0, 0)), 0, 1)))


def simulate(hex_color: str, kind: str) -> np.ndarray:
    """OKLab of the colour as seen with a colour-vision deficiency (protan, deutan, tritan)."""
    lin = _to_linear(_hex_rgb(hex_color))
    return _lin_oklab(np.clip(_CVD[kind] @ lin, 0, 1))


def delta_e(a: str, b: str, kind: str | None = None) -> float:
    """ΔE in OKLab × 100, optionally under simulated CVD."""
    if kind is None:
        return float(np.linalg.norm(oklab(a) - oklab(b)) * 100)
    return float(np.linalg.norm(simulate(a, kind) - simulate(b, kind)) * 100)


def contrast(a: str, b: str) -> float:
    def lum(h):
        r, g, bl = _to_linear(_hex_rgb(h))
        return 0.2126 * r + 0.7152 * g + 0.0722 * bl
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@dataclass
class PaletteReport:
    colors: tuple
    background: str
    mode: str
    checks: list          # (name, "PASS" | "WARN" | "FAIL", detail)

    @property
    def ok(self) -> bool:
        """True when nothing fails (warnings ask for direct labels or a table, but aren't errors)."""
        return all(st != "FAIL" for _, st, _ in self.checks)

    def __str__(self) -> str:
        head = f"Palette ({self.mode}, background {self.background}): {len(self.colors)} colours"
        rows = [f"  [{st}] {n:<22} {d}" for n, st, d in self.checks]
        return "\n".join([head, *rows, "  -> " + ("all checks pass" if self.ok else "fix the failing checks")])

    __repr__ = __str__


def check_palette(colors, background: str = "#ffffff", mode: str | None = None) -> PaletteReport:
    """Run the five categorical-palette checks. ``mode`` defaults from the background's lightness.

    CVD separation between 6 and 8 and contrast between 2 and 3 are warnings: usable only with a
    second encoding (direct labels, gaps, markers or a data table).
    """
    colors = tuple(colors)
    if mode is None:
        mode = "dark" if oklch(background)[0] < 0.5 else "light"
    lo, hi = BAND[mode]

    def status(ok, warn=False):
        return "PASS" if ok else ("WARN" if warn else "FAIL")

    checks = []
    off = [c for c in colors if not lo <= oklch(c)[0] <= hi]
    checks.append(("Lightness band", status(not off), f"outside L {lo}-{hi}: {off}" if off else f"all inside L {lo}-{hi}"))
    grey = [c for c in colors if oklch(c)[1] < CHROMA_MIN]
    checks.append(("Chroma floor", status(not grey), f"too grey: {grey}" if grey else f"all >= {CHROMA_MIN}"))
    pairs = list(zip(colors, colors[1:]))
    if pairs:
        worst = min(((delta_e(a, b, k), a, b, k) for a, b in pairs for k in _CVD), key=lambda t: t[0])
        checks.append(("CVD separation", status(worst[0] >= CVD_MIN, worst[0] >= 6.0),
                       f"worst adjacent {worst[1]}-{worst[2]} ΔE {worst[0]:.1f} ({worst[3]})"))
        wn = min(((delta_e(a, b), a, b) for a, b in pairs), key=lambda t: t[0])
        checks.append(("Normal-vision floor", status(wn[0] >= NORMAL_MIN),
                       f"worst adjacent {wn[1]}-{wn[2]} ΔE {wn[0]:.1f}"))
    ratios = {c: contrast(c, background) for c in colors}
    low = [c for c, r in ratios.items() if r < CONTRAST_MIN]
    checks.append(("Contrast vs background", status(not low, all(ratios[c] >= 2.0 for c in low)),
                   f"below 3:1: {low}" if low else "all >= 3:1"))
    return PaletteReport(colors, background, mode, checks)


def _min_adjacent(order) -> float:
    return min((min(delta_e(a, b, k) for k in _CVD) for a, b in zip(order, order[1:])), default=99.0)


def generate(brand: str, background: str = "#ffffff", n: int = 8, hues=None) -> tuple[str, ...]:
    """A categorical palette that starts with ``brand`` and passes the checks where possible.

    The other slots come from hues spread around the colour wheel (or ``hues``), at two lightness
    levels inside the band for the background, then ordered so neighbours stay far apart for
    colour-blind and normal vision alike.
    """
    mode = "dark" if oklch(background)[0] < 0.5 else "light"
    lo, hi = BAND[mode]
    L0, C0, h0 = oklch(brand)
    mid = (lo + hi) / 2 + (0.0 if mode == "light" else 0.02)
    first = brand
    if not lo <= L0 <= hi or contrast(brand, background) < CONTRAST_MIN or C0 < CHROMA_MIN:
        # nudge the brand colour into the band, trying nearby lightness where sRGB allows more chroma
        base_L = min(max(L0, lo + 0.04), hi - 0.04)
        tries = [from_oklch(min(max(base_L + d, lo), hi), max(C0, 0.13), h0) for d in (0, 0.04, -0.04, 0.08, -0.08, 0.12, -0.12)]
        good = [c for c in tries if oklch(c)[1] >= CHROMA_MIN and contrast(c, background) >= CONTRAST_MIN]
        first = good[0] if good else tries[0]
    if hues is None:
        hues = [(h0 + d) % 360 for d in range(20, 360, 20)]
    cands = []
    for h in hues:
        for dl in (-0.08, -0.01, 0.06):
            L = min(max(mid + dl, lo + 0.02), hi - 0.02)
            c = from_oklch(L, 0.15, h)
            for _ in range(12):                      # keep contrast against the background
                if contrast(c, background) >= CONTRAST_MIN:
                    break
                L = min(max(L + (-0.02 if mode == "light" else 0.02), lo), hi)
                c = from_oklch(L, 0.15, h)
            if oklch(c)[1] >= CHROMA_MIN:
                cands.append(c)
    order = [first]
    pool = [c for c in cands if delta_e(c, first) > NORMAL_MIN + 5]

    def score(c):
        adj_cvd = min(delta_e(order[-1], c, k) for k in _CVD)
        adj_norm = delta_e(order[-1], c)
        near = min(min(delta_e(o, c), *(delta_e(o, c, k) for k in _CVD)) for o in order)
        penalty = (0 if adj_cvd >= CVD_MIN else 50) + (0 if adj_norm >= NORMAL_MIN + 2 else 50)
        return near * 2 + min(adj_cvd, 20) - penalty

    while len(order) < n and pool:
        best = max(pool, key=score)
        order.append(best)
        # drop candidates too close to anything chosen (the other lightness of the same hue, mostly)
        pool = [c for c in pool if c != best and delta_e(c, best) > 10]
    order = _improve_order(order)
    # still a weak pair? drop the later colour of it: 7 good colours beat 8 confusable ones
    def pairs_fail(o):
        return any(st == "FAIL" for n, st, _ in check_palette(o, background).checks
                   if n in ("CVD separation", "Normal-vision floor"))

    while len(order) > 5 and pairs_fail(order):
        weakest = min(range(1, len(order)), key=lambda i: _pair_score(order[i - 1], order[i]))
        order.pop(weakest if weakest > 0 else 1)
        order = _improve_order(order)
    return tuple(order)


def _pair_score(a: str, b: str) -> float:
    return min(min(delta_e(a, b, k) for k in _CVD) / CVD_MIN, delta_e(a, b) / NORMAL_MIN)


def _improve_order(order: list) -> list:
    """Swap non-brand slots while the weakest adjacent pair gets better."""
    order = list(order)

    def worst(o):
        return min((_pair_score(a, b) for a, b in zip(o, o[1:])), default=9.0)

    best = worst(order)
    improved = True
    while improved and best < 1.0:
        improved = False
        for i in range(1, len(order)):
            for j in range(i + 1, len(order)):
                o = order[:]
                o[i], o[j] = o[j], o[i]
                w = worst(o)
                if w > best + 1e-9:
                    order, best, improved = o, w, True
    return order


def ramp(color: str, background: str = "#ffffff", steps: int = 4) -> tuple[str, ...]:
    """Sequential ramp for ``color``: from near the background to a deep shade of the same hue."""
    L, C, h = oklch(color)
    Lb = oklch(background)[0]
    if Lb >= 0.5:
        Ls = np.linspace(0.96, 0.28, steps)
    else:
        Ls = np.linspace(0.24, 0.9, steps)
    Cs = [C * (0.25 + 0.75 * math.sin(math.pi * t) ** 0.6) if 0 < t < 1 else C * 0.25
          for t in np.linspace(0, 1, steps)]
    Cs[-1] = C * 0.7
    return tuple(from_oklch(float(l_), float(c), h) for l_, c in zip(Ls, Cs))
