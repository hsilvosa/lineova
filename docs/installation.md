# Installation

## Requirements

- Python 3.10, 3.11, 3.12 or 3.13
- NumPy 1.23 or newer (installed automatically)

## From PyPI

```bash
pip install lineova
```

This gives you SVG, PDF and interactive HTML output, which need nothing else.

### Optional extras

| Extra | Installs | Adds |
|---|---|---|
| `png` | `resvg-py` | PNG export with no system libraries (`chart.save("x.png", dpi=300)`) |
| `pandas` | `pandas` | Nothing new in lineova itself; a convenience for notebooks |
| `dev` | `pytest`, `pandas`, `networkx`, `ruff` | Running the test suite and linters |
| `docs` | `mkdocs-material` | Building this documentation site |

```bash
pip install "lineova[png]"
```

PNG export can also use `cairosvg` or `playwright` if either is already installed. lineova tries resvg first, then cairosvg, then playwright. Set `LINEOVA_PNG_BACKEND=cairosvg` (or another name) to choose one.

## From GitHub

The latest development version:

```bash
pip install "git+https://github.com/hsilvosa/lineova.git@develop"
```

A specific release:

```bash
pip install "git+https://github.com/hsilvosa/lineova.git@v0.2.0"
```

## For development

```bash
git clone https://github.com/hsilvosa/lineova.git
cd lineova
git switch develop
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

See [CONTRIBUTING.md](https://github.com/hsilvosa/lineova/blob/main/CONTRIBUTING.md) for the branch model and release process.

## Checking the installation

```python
import lineova as lv
print(lv.__version__)
lv.bar({"a": 1, "b": 2}).save("check.svg")
```
