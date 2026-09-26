"""Regenerate the generated parts of the docs.

    python tools/build_docs.py

- docs/use-cases.md   from docs/_templates/use-cases.md + code blocks in examples/use_cases.py
- docs/api.md         from the public API's signatures and docstrings
"""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import lineova as lv  # noqa: E402


def snippets() -> dict[str, str]:
    code = (ROOT / "examples" / "use_cases.py").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"# \[(\w+)\]\n(.*?)# \[/\1\]", code, re.S):
        body = re.sub(r"OUT / \"([\w.]+)\"", r'"\1"', m.group(2)).rstrip()
        out[m.group(1)] = "```python\nimport numpy as np\nimport pandas as pd\nimport lineova as lv\n\n" \
            f"rng = np.random.default_rng(42)\n{body}\n```"
    return out


def build_use_cases() -> None:
    tpl = (ROOT / "docs" / "_templates" / "use-cases.md").read_text(encoding="utf-8")
    sn = snippets()
    text = re.sub(r"\{\{(\w+)\}\}", lambda m: sn[m.group(1)], tpl)
    (ROOT / "docs" / "use-cases.md").write_text(text, encoding="utf-8")


def _sig(obj) -> str:
    try:
        sig = str(inspect.signature(obj)).replace("'auto'", '"auto"')
        sig = re.sub(r"(: |-> )\"?'([^']+)'\"?", r"\1\2", sig)      # annotations are strings (PEP 563)
        return sig.replace("(self, ", "(").replace("(self)", "()")
    except (TypeError, ValueError):
        return "(...)"


def _doc(obj) -> str:
    return inspect.cleandoc(obj.__doc__ or "").strip()


def build_api() -> None:
    from lineova.marks import layer_class
    lines = ["# API reference", "",
             "Generated from the source by `tools/build_docs.py`. Every chart function returns a "
             "[`Chart`](#chart), so the methods below work on its result.", ""]
    lines += ["## Chart functions", ""]
    for name in ["line", "area", "bar", "scatter", "histogram", "heatmap", "box", "violin", "ridgeline", "pie",
                 "donut", "dumbbell", "slope", "waterfall", "candlestick", "treemap", "sankey", "radar", "density",
                 "timeline", "calendar", "sparkline", "stat", "network"]:
        fn = getattr(lv, name)
        lines += [f"### `lv.{name}`", "", f"```python\nlv.{name}{_sig(fn)}\n```", "", _doc(fn), ""]
        layer = layer_class("pie" if name == "donut" else name)
        params = [p for p in inspect.signature(layer.__init__).parameters.values()
                  if p.name not in ("self", "data", "x", "y", "color", "value", "kw")]
        if params:
            lines.append("Chart-specific options: " + ", ".join(
                f"`{p.name}={p.default!r}`".replace("'auto'", '"auto"') for p in params) + ".")
            lines.append("")
    lines += ["## Common options", "",
              "Accepted by every chart function as keywords, and by `Chart(...)`:", "",
              "| Option | Meaning |", "|---|---|"]
    common = {
        "title / subtitle": "Heading text (in `folio`, the figure caption)",
        "caption / number / source": "Text under the chart; `number` gives 'Figure N.'",
        "theme": "`folio`, `ledger`, `instrument`, `fjord`, a registered name or a `Theme`",
        "width / height / size": "Pixels, or a preset: " + ", ".join(f"`{k}`" for k in lv.SIZES),
        "legend": "`auto`, `top`, `bottom`, `right`, `direct`, `readout`, `none`",
        "palette / highlight": "Colours for series, and series to emphasise",
        "facet / facet_cols / share": "Small multiples by a column",
        "x_* / y_*": "Axis options: " + ", ".join(f"`{f}`" for f in lv.Axis.__dataclass_fields__),
    }
    lines += [f"| `{k}` | {v} |" for k, v in common.items()] + [""]
    lines += ["## Chart", "", f"```python\nlv.Chart{_sig(lv.Chart)}\n```", "", _doc(lv.Chart), ""]
    for name, m in inspect.getmembers(lv.Chart, inspect.isfunction):
        if name.startswith("_") or name in ("build",):
            continue
        d = _doc(m)
        lines += [f"- **`.{name}{_sig(m)}`**" + (f": {d.splitlines()[0]}" if d else "")]
    lines += ["", "## Grid", "", f"```python\nlv.grid{_sig(lv.grid)}\n```", "", _doc(lv.Grid), "",
              "## Chunks", "", f"```python\nlv.Chunks{_sig(lv.Chunks)}\n```", "", _doc(lv.Chunks), "",
              "## Graph", "", _doc(lv.Graph), ""]
    for name, m in inspect.getmembers(lv.Graph, lambda o: inspect.isfunction(o) or isinstance(o, classmethod)):
        if name.startswith("_"):
            continue
        d = _doc(m)
        lines += [f"- **`.{name}{_sig(m)}`**" + (f": {d.splitlines()[0]}" if d else "")]
    lines += ["", "## Themes", "", _doc(lv.themes), "",
              "- `lv.themes.get(name)`, `lv.themes.register(name, theme)`, `lv.themes.names()`, "
              "`lv.themes.set_default(name)`", "",
              "`Theme` fields: " + ", ".join(f"`{f}`" for f in lv.Theme.__dataclass_fields__ if f != "extra") + ".", ""]
    (ROOT / "docs" / "api.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    build_use_cases()
    build_api()
    print("docs/use-cases.md and docs/api.md written")
