"""Text measurement and number/date formatting.

Layout needs to know how wide a label is before anything is drawn. We use the
metrics of the PDF core fonts (Helvetica, Times, Courier) as proxies for the
theme's sans, serif and mono faces. They are close enough for margins and
collision checks, and they are exactly right for the native PDF backend.
"""

from __future__ import annotations

import math
from functools import lru_cache

# Advance widths (1/1000 em) for ASCII 32..126, from the Adobe core-font AFMs.
_HELVETICA = (
    278, 278, 355, 556, 556, 889, 667, 222, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556,
    556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667,
    611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667,
    667, 611, 278, 278, 278, 469, 556, 222, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500,
    222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
)
_HELVETICA_BOLD = (
    278, 333, 474, 556, 556, 889, 722, 278, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556,
    556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667,
    611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667,
    667, 611, 333, 278, 333, 584, 556, 278, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556,
    278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
)
_TIMES = (
    250, 333, 408, 500, 500, 833, 778, 333, 333, 333, 500, 564, 250, 333, 250, 278, 500, 500, 500,
    500, 500, 500, 500, 500, 500, 500, 278, 278, 564, 564, 564, 444, 921, 722, 667, 667, 722, 611,
    556, 722, 722, 333, 389, 722, 611, 889, 722, 722, 556, 722, 667, 556, 611, 722, 722, 944, 722,
    722, 611, 333, 278, 333, 469, 500, 333, 444, 500, 444, 500, 444, 333, 500, 500, 278, 278, 500,
    278, 778, 500, 500, 500, 500, 333, 389, 278, 500, 500, 722, 500, 500, 444, 480, 200, 480, 541,
)
_TIMES_BOLD = (
    250, 333, 555, 500, 500, 1000, 833, 333, 333, 333, 500, 570, 250, 333, 250, 278, 500, 500, 500,
    500, 500, 500, 500, 500, 500, 500, 333, 333, 570, 570, 570, 500, 930, 722, 667, 722, 722, 667,
    611, 778, 778, 389, 500, 778, 667, 944, 722, 778, 611, 778, 722, 556, 667, 722, 722, 1000, 722,
    722, 667, 333, 278, 333, 581, 500, 333, 500, 556, 444, 556, 444, 333, 500, 556, 278, 333, 556,
    278, 833, 556, 500, 556, 556, 444, 389, 333, 556, 500, 722, 500, 500, 444, 394, 220, 394, 520,
)

_TABLES = {
    ("sans", False): _HELVETICA,
    ("sans", True): _HELVETICA_BOLD,
    ("serif", False): _TIMES,
    ("serif", True): _TIMES_BOLD,
}
# Web faces used by the themes (and their fallbacks, e.g. Georgia) run wider than the
# core fonts. Over-estimating is safe for layout; under-estimating causes overlaps.
KIND_FACTOR = {"sans": 1.05, "serif": 1.12, "mono": 1.0}


@lru_cache(maxsize=8192)
def text_width(text: str, size: float, kind: str = "sans", bold: bool = False) -> float:
    """Approximate rendered width of ``text`` in px at font ``size`` px."""
    if not text:
        return 0.0
    if kind == "mono":
        return len(text) * 0.6 * size
    table = _TABLES[(kind if kind in ("sans", "serif") else "sans", bold)]
    total = 0
    for ch in text:
        o = ord(ch)
        total += table[o - 32] if 32 <= o <= 126 else 600
    return total / 1000.0 * size * KIND_FACTOR.get(kind, 1.0)


def text_height(size: float) -> float:
    """Line box height used for layout (cap height + descender, with a little air)."""
    return size * 1.25


def wrap(text: str, width: float, size: float, kind: str = "sans", bold: bool = False) -> list[str]:
    """Greedy word wrap to ``width`` px. Explicit newlines are kept."""
    lines: list[str] = []
    for para in str(text).split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            cand = f"{cur} {w}"
            if text_width(cand, size, kind, bold) <= width:
                cur = cand
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def truncate(text: str, width: float, size: float, kind: str = "sans", bold: bool = False) -> str:
    """Shorten ``text`` with an ellipsis so it fits in ``width`` px."""
    if text_width(text, size, kind, bold) <= width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if text_width(text[:mid] + "…", size, kind, bold) <= width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…" if lo else "…"


# --------------------------------------------------------------------------- numbers

MINUS = "−"
_SI = ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k"))


def decimals_for_step(step: float) -> int:
    """How many decimals are needed so consecutive ticks ``step`` apart differ."""
    if step <= 0 or not math.isfinite(step):
        return 0
    d = -math.floor(math.log10(step) + 1e-9)
    # steps like 2.5 need one more digit than their magnitude suggests
    if abs(round(step * 10**d) - step * 10**d) > 1e-6 * 10**d:
        d += 1
    return max(0, d)


def format_number(value: float, step: float | None = None, *, compact: bool | None = None) -> str:
    """Format a tick value.

    ``step`` is the spacing between ticks; it decides how many decimals to show.
    Large magnitudes switch to compact SI suffixes (12k, 3.4M) automatically.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    v = float(value)
    if v == 0:
        return "0"
    step = abs(step) if step else abs(v) / 10
    mag = max(abs(v), step)
    use_compact = compact if compact is not None else mag >= 1e4
    if use_compact:
        for div, suffix in _SI:
            if mag >= div:
                d = decimals_for_step(step / div)
                s = f"{abs(v) / div:,.{d}f}{suffix}"
                return (MINUS if v < 0 else "") + s
    d = decimals_for_step(step)
    s = f"{abs(v):,.{d}f}"
    return (MINUS if v < 0 else "") + s


def format_value(value: float) -> str:
    """Format a single data value for labels/tooltips (about 3 significant digits)."""
    v = float(value)
    if v == 0 or not math.isfinite(v):
        return "0" if v == 0 else str(v)
    mag = abs(v)
    if mag >= 1e4:
        s = format_number(v, 10 ** math.floor(math.log10(mag)) / 100, compact=True)
        num, suffix = s[:-1], s[-1]
        if "." in num:                      # 12.0k -> 12k, 2.50M -> 2.5M
            num = num.rstrip("0").rstrip(".")
        return num + suffix
    digits = max(0, 2 - math.floor(math.log10(mag)))
    s = f"{mag:,.{digits}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return (MINUS if v < 0 else "") + s
