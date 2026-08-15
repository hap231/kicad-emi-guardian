# Development and API compatibility

## Source layout

- `plugin/`: the complete KiCad runtime payload and PCM manifest
- `plugin/emi_guardian/`: KiCad-independent models, analysis, planning, controller, reporting, and IPC adapter modules
- `plugin/emi_guardian/web/`: local dashboard HTML, CSS, and JavaScript
- `docs/en/` and `docs/ja/`: mirrored documentation sources
- `installers/`: platform install/update/uninstall
- `tests/`: unit, safety, packaging, and documentation regression tests
- `tools/`: site/manual generation, validation, demo generation, and deterministic packaging
- `.github/`: CI, CodeQL, Pages, and Renovate configuration
- `resources/`: KiCad Package and Content Manager assets

## Compatibility policy

- KiCad 10 and later only
- Python 3.9 and later
- `kicad-python>=0.7.1,<1.0`
- Prefer canonical layer names and capability detection
- Fail closed when a safe capability is unavailable
- Use selection plus zoom because stable custom DRC-marker creation is not public IPC
- Treat `run_action` action identifiers as unstable fallbacks
- Validate/export thickness, color, and project rules rather than rewriting board text

## Local validation

```bash
python -m pip install -e ".[test,docs,quality]"
python -m coverage run -m pytest -q
python -m coverage report --fail-under=68
ruff check plugin tests tools docs/conf.py
ruff format --check plugin tests tools docs/conf.py
mypy plugin/emi_guardian
bandit -r plugin/emi_guardian plugin/open_dashboard.py plugin/quick_scan.py -ll
python -m compileall -q plugin tests tools
node --check plugin/emi_guardian/web/app.js
python tools/build_site.py --output site
pip-audit --strict --requirement plugin/requirements.txt
python tools/check_package.py
python tools/build_package.py
```

Validation covers Python 3.9 syntax, manifests, metadata, JSON, HTML anchors, installer layout, shell syntax, ZIP traversal, deterministic timestamps, and hashes.

## Documentation

```bash
python tools/build_site.py --output site
```

Bilingual MyST Markdown is authoritative. English and Japanese trees must contain the same relative Markdown paths; `tools/build_site.py` enforces the mirror and validates generated local links. `markdown-it-py` builds standalone manuals. Source comments and docstrings are English.

## GitHub CI

`.github/workflows/ci.yml` tests Python 3.9, 3.13, and 3.14; enforces Ruff formatting and linting, mypy type checking, YAML, JavaScript, POSIX shell, coverage, strict bilingual Sphinx, and dependency-audit checks; validates KiCad packaging; and compares two complete release builds. Separate workflows analyze Python and JavaScript with CodeQL and publish the validated site to GitHub Pages. Renovate configuration monitors Python, documentation, and GitHub Actions dependencies.

## Live acceptance

Mocks cannot prove KiCad GUI behavior, OS security policy, managed-environment creation, Undo, or Gerber output. Execute the [acceptance test](acceptance-test.md) on every supported KiCad minor and target OS.
