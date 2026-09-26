"""Scene -> PNG via the best available SVG rasteriser.

Tried in order (override with the LINEOVA_PNG_BACKEND environment variable):

1. ``resvg_py``   – ``pip install "lineova[png]"``; small, fast, no system deps
2. ``cairosvg``   – needs the Cairo library installed on the system
3. ``playwright`` – headless Chromium; highest fidelity, slow to start
"""

from __future__ import annotations

import os

from ..scene import Scene
from . import svg as svg_backend


class PNGBackendMissing(RuntimeError):
    pass


def _resvg(svg: str, scale: float, w: float, h: float) -> bytes:
    import resvg_py
    try:
        out = resvg_py.svg_to_bytes(svg_string=svg, zoom=scale, load_system_fonts=True)
    except TypeError:
        out = resvg_py.svg_to_bytes(svg_string=svg, zoom=scale)
    return bytes(out)


def _cairosvg(svg: str, scale: float, w: float, h: float) -> bytes:
    import cairosvg
    return cairosvg.svg2png(bytestring=svg.encode("utf-8"), scale=scale)


def _playwright(svg: str, scale: float, w: float, h: float) -> bytes:
    from playwright.sync_api import sync_playwright
    html = ("<!doctype html><html><head><meta charset='utf-8'><style>html,body{margin:0;padding:0;background:transparent}"
            "svg{display:block}</style></head><body>" + svg + "</body></html>")
    with sync_playwright() as p:
        kwargs = {}
        exe = os.environ.get("LINEOVA_CHROMIUM")
        if exe:
            kwargs["executable_path"] = exe
        browser = p.chromium.launch(**kwargs)
        try:
            page = browser.new_page(viewport={"width": int(round(w)), "height": int(round(h))},
                                    device_scale_factor=scale)
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready")
            return page.locator("svg").screenshot(type="png")
        finally:
            browser.close()


BACKENDS = {"resvg": _resvg, "cairosvg": _cairosvg, "playwright": _playwright}


def available() -> list[str]:
    """Names of the PNG backends importable in this environment."""
    import importlib.util
    mods = {"resvg": "resvg_py", "cairosvg": "cairosvg", "playwright": "playwright"}
    return [k for k, m in mods.items() if importlib.util.find_spec(m) is not None]


def render(scene: Scene, scale: float = 2.0) -> bytes:
    svg = svg_backend.render(scene)
    forced = os.environ.get("LINEOVA_PNG_BACKEND")
    order = [forced] if forced else ["resvg", "cairosvg", "playwright"]
    errors = []
    for name in order:
        fn = BACKENDS.get(name)
        if fn is None:
            raise ValueError(f"Unknown PNG backend {name!r}; choose from {', '.join(BACKENDS)}.")
        try:
            return fn(svg, scale, scene.width, scene.height)
        except ImportError:
            continue
        except Exception as exc:  # backend present but failed: try the next one
            errors.append(f"{name}: {exc}")
    detail = ("\nBackend errors:\n  " + "\n  ".join(errors)) if errors else ""
    raise PNGBackendMissing(
        "PNG export needs an SVG rasteriser. Install one with:\n"
        "    pip install \"lineova[png]\"      (recommended: resvg, no system dependencies)\n"
        "or use .svg / .pdf, which need nothing extra." + detail)
