import json
import re

import numpy as np
import pytest

import lineova as lv


def meta_of(html: str) -> list:
    m = re.search(r'<script type="application/json" id="lv-meta">(.*?)</script>', html, re.S)
    return json.loads(m.group(1).replace(r"<\/", "</"))


@pytest.fixture
def times():
    return np.arange("2024-01-01", "2024-03-01", dtype="datetime64[h]")


def test_line_charts_get_smart_zoom_metadata(times, rng):
    c = lv.line(x=times, y=np.cumsum(rng.normal(size=len(times))))
    html = c.to_html()
    z = [m["zoom"] for m in meta_of(html) if "zoom" in m][0]
    assert z["x"]["kind"] == "time" and len(z["x"]["levels"]) >= 4 and len(z["y"]["levels"]) >= 4
    assert z["series"][0]["x"] and len(z["series"][0]["x"]) == len(z["series"][0]["y"])
    assert "lvz0-marks" in html and "lvz0-xt" in html and "__lvZoom" in html


def test_tick_levels_get_denser_and_stay_in_the_domain():
    c = lv.line(x=np.arange(1000.0), y=np.arange(1000.0))
    z = meta_of(c.to_html())[0]["zoom"]
    counts = [len(lv_["v"]) for lv_ in z["x"]["levels"]]
    assert counts == sorted(counts) and counts[-1] > 10 * counts[0]
    assert all(len(lv_["v"]) == len(lv_["l"]) for lv_ in z["x"]["levels"])
    assert all(z["x"]["d0"] - 1e-6 <= v <= z["x"]["d1"] + 1e-6 for v in z["x"]["levels"][-1]["v"])


def test_static_outputs_are_untouched(times):
    c = lv.line(x=times, y=np.arange(len(times), dtype=float))
    assert "lvz" not in c.to_svg()
    c.to_html()
    assert "lvz" not in c.to_svg()                 # building the page leaves no state behind
    assert c.to_pdf().startswith(b"%PDF")


@pytest.mark.parametrize("make", [
    lambda: lv.bar({"a": 1, "b": 2}),
    lambda: lv.area({"x": [1, 2, 3], "y": [1, 2, 3]}, x="x", y="y"),
    lambda: lv.line(x=[1, 2, 3], y=[1, 2, 3], band=([0, 1, 2], [2, 3, 4])),
    lambda: lv.line(x=[1, 10, 100], y=[1, 2, 3], x_scale="log"),
    lambda: lv.line(x=[1, 2, 3], y=[1, 2, 3]).vline(2, "mark"),
    lambda: lv.scatter(x=[1, 2], y=[1, 2]),
])
def test_other_charts_keep_the_plain_zoom(make):
    html = make().to_html()
    assert not any("zoom" in m for m in meta_of(html))
    assert "lvz0" not in html and "__lvZoom=" not in html


def test_reversed_axes_are_not_zoomable():
    c = lv.line(x=[1, 2, 3], y=[3, 2, 1])
    c.y_axis(reverse=True)
    assert not any("zoom" in m for m in meta_of(c.to_html()))


def test_hline_annotation_is_allowed():
    c = lv.line(x=[1, 2, 3], y=[3, 2, 1]).hline(2, "target")
    assert any("zoom" in m for m in meta_of(c.to_html()))


def test_payload_is_capped(rng):
    n = 400_000
    c = lv.line(x=np.arange(n, dtype=float), y=np.cumsum(rng.normal(size=n)))
    z = meta_of(c.to_html(data=False))[0]["zoom"]
    assert len(z["series"][0]["x"]) <= 32_000
    assert all(v is None or abs(v) < 1e6 for v in z["series"][0]["y"])          # plain finite numbers


def test_grid_panels_get_unique_ids(rng):
    t = np.arange(50.0)
    g = lv.grid([lv.line(x=t, y=rng.normal(size=50)), lv.line(x=t, y=rng.normal(size=50)), lv.bar({"a": 1})], cols=3)
    html = g.to_html()
    zooms = [m["zoom"] for m in meta_of(html) if "zoom" in m]
    assert [z["id"] for z in zooms] == ["lvz0", "lvz1"]
    assert "lvz0-marks" in html and "lvz1-marks" in html and "lvz2" not in html
    plots = [m["plot"] for m in meta_of(html) if "zoom" in m]
    assert plots[0][0] != plots[1][0]              # global coordinates are shifted per panel, local ones are not
    assert max(z["plot"][0] + z["plot"][2] for z in zooms) < 400      # local coordinates: no panel offset in them


def test_facets_are_zoomable(rng):
    t = np.tile(np.arange(30.0), 2)
    html = lv.line({"t": t, "v": rng.normal(size=60), "g": np.repeat(["a", "b"], 30)}, x="t", y="v", facet="g").to_html()
    assert sum("zoom" in m for m in meta_of(html)) == 2


# ---------------------------------------------------------------- the JavaScript, in a real browser

def _browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    pw = sync_api.sync_playwright().start()
    try:
        for kw in ({"channel": "chrome"}, {"channel": "msedge"}, {}):
            try:
                return pw, pw.chromium.launch(headless=True, **kw)
            except Exception:
                continue
    except Exception:
        pass
    pw.stop()
    pytest.skip("no Chromium browser available")


def test_zoom_in_a_browser(tmp_path, times, rng):
    pw, browser = _browser()
    try:
        page = browser.new_page(viewport={"width": 1000, "height": 700})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        f = tmp_path / "z.html"
        f.write_text(lv.line(x=times, y=np.cumsum(rng.normal(size=len(times)))).to_html(data=False), encoding="utf-8")
        page.goto(f.as_uri())
        assert page.evaluate("window.__lvZoom.plots.length") == 1
        before = page.evaluate("[...document.querySelectorAll('.lvz0-xt')].map(e => e.textContent)")
        page.evaluate("window.__lvZoom.setWindow(0, window.__lvZoom.plots[0].full[0], window.__lvZoom.plots[0].full[0] + 3 * 86400e9)")
        after = page.evaluate("[...document.querySelectorAll('.lvz0-xt')].map(e => e.style.display)")
        assert all(d == "none" for d in after)                       # the static labels are hidden...
        fresh = page.evaluate(r"[...document.querySelectorAll('text')].filter(e => !e.classList.length && /\d{2}:\d{2}|Jan/.test(e.textContent)).length")
        assert fresh >= 2 and before                                   # ...and new ones drawn for a 3-day window
        assert page.evaluate("document.querySelectorAll('clipPath').length") >= 2
        page.evaluate("window.__lvZoom.reset()")
        assert page.evaluate("[...document.querySelectorAll('.lvz0-xt')].every(e => e.style.display === '')")
        assert not errors
    finally:
        browser.close()
        pw.stop()
