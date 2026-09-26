# Contributing to lineova

Thanks for helping. This page explains how the repository is organised and how changes reach a release.

## Branches

lineova uses a Git Flow–style model:

| Branch | Purpose | Who merges into it |
|---|---|---|
| `main` | Released code only. Every commit on `main` is a tagged release (`v0.2.0`, …). The docs site is built from `main`. | `release/*` and `hotfix/*` branches |
| `develop` | Integration branch for the next release. Should always pass the tests. | `feature/*` and `fix/*` branches, via pull request |
| `feature/<name>` | New work, e.g. `feature/sunburst`. Branch from `develop`. | — |
| `fix/<name>` | Bug fixes for the next release. Branch from `develop`. | — |
| `release/<version>` | Stabilising a release: version bump, changelog, final fixes only. Branch from `develop`, merge into `main` **and** back into `develop`. | — |
| `hotfix/<version>` | Urgent fix to a release. Branch from `main`, merge into `main` and `develop`. | — |

```text
feature/x ──┐
fix/y ──────┴─► develop ──► release/0.3.0 ──► main (tag v0.3.0)
                    ▲                │
                    └────────────────┘  (merged back)
```

## Setting up

```bash
git clone https://github.com/hsilvosa/lineova.git
cd lineova
git switch develop
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Making a change

1. `git switch -c feature/my-change develop`
2. Write the change and a test in `tests/`. Chart code should render in all four themes. `tests/test_new_charts.py` shows the pattern.
3. Run the checks:
   ```bash
   pytest
   ruff check src tests
   ```
4. If the change affects the output, regenerate the images and look at them:
   ```bash
   python examples/gallery.py
   python examples/use_cases.py
   python tools/build_docs.py        # API reference and use-cases page
   ```
5. Add a line under *Unreleased* in `CHANGELOG.md`.
6. Open a pull request against `develop`.

## Guidelines

- **Defaults first.** A new option needs a sensible `"auto"` value, so it never becomes one more thing users have to set.
- **Scale with pixels, not rows.** Anything that can receive large input must stay vectorised (NumPy) and chunk-safe. Add a line to `benchmarks/bench.py` for new heavy paths.
- **No new required dependencies.** Optional ones go in an extra in `pyproject.toml` and are imported lazily.
- **Themes own the look.** Colours, fonts and spacing come from `Theme`, never literals in chart code.
- **Clear errors.** Say what was wrong and how to fix it (`DataError("Column 'x' not found. Available columns: …")`).

## Releasing (maintainers)

1. `git switch -c release/X.Y.Z develop`
2. Bump the version in `pyproject.toml`, `src/lineova/__init__.py` and `CITATION.cff`. Move *Unreleased* in `CHANGELOG.md` under the new version.
3. Open a PR from `release/X.Y.Z` into `main`. When CI passes, merge it.
4. Tag `main`: `git tag -a vX.Y.Z -m "lineova X.Y.Z" && git push origin vX.Y.Z`. The *release* workflow builds the package, publishes it to PyPI (trusted publishing) and creates the GitHub release.
5. Merge `main` back into `develop`.

## Reporting bugs

Open an issue with a minimal example that reproduces the problem, what you expected, and the output of `python -c "import lineova, numpy, sys; print(lineova.__version__, numpy.__version__, sys.version)"`.
