# Development and API compatibility

## Source layout

- `models.py`: KiCad-independent models and evidence IDs
- `kicad_adapter.py`: public IPC read/write, selection, layer, ping, reconnect, transactions
- `raster.py`, `antenna.py`, `noise.py`, `quantitative.py`: analysis
- `fixes.py`, `silkscreen.py`, `edge_optimizer.py`: planning
- `manufacturing.py`, `manufacturing_profiles.py`: JLCPCB DFM and presets
- `localization.py`: bilingual finding and DFM presentation
- `controller.py`: orchestration, cache, safety gates, preview payload
- `server.py`, `web/`: local API and blue UI
- `report.py`, `solver_export.py`: reporting and exchange data
- `installers/`: platform install/update/uninstall
- `scripts/`: validation, manuals, demo, deterministic packaging

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
ruff check plugin tests scripts docs/conf.py
ruff format --check plugin tests scripts docs/conf.py
mypy plugin/emi_guardian
bandit -r plugin/emi_guardian plugin/open_dashboard.py plugin/quick_scan.py -ll
python -m compileall -q plugin tests scripts
node --check plugin/emi_guardian/web/app.js
sphinx-build -W --keep-going -b html docs docs/_build/html
pip-audit --strict --requirement plugin/requirements.txt
python scripts/check_package.py
python scripts/build_package.py
```

Validation covers Python 3.9 syntax, manifests, metadata, JSON, HTML anchors, installer layout, shell syntax, ZIP traversal, deterministic timestamps, and hashes.

## Documentation

```bash
sphinx-build -W --keep-going -b html docs docs/_build/html
doxygen Doxyfile
```

Bilingual MyST Markdown is authoritative. `markdown-it-py` builds standalone manuals. Source comments and docstrings are English.

## GitHub CI

`.github/workflows/ci.yml` tests Python 3.9, 3.13, and 3.14; enforces Ruff formatting and linting, mypy type checking, YAML, JavaScript, POSIX shell, coverage, strict bilingual Sphinx, and dependency-audit checks; validates KiCad packaging; and compares two complete release builds. A separate CodeQL workflow analyzes Python and JavaScript, while Dependabot monitors Python and GitHub Actions dependencies.

## Live acceptance

Mocks cannot prove KiCad GUI behavior, OS security policy, managed-environment creation, Undo, or Gerber output. Execute the [acceptance test](acceptance-test.md) on every supported KiCad minor and target OS.
