# EMI Guardian release checklist

[日本語版](RELEASE_CHECKLIST.ja.md)

## Source and version

- [ ] `pyproject.toml`, Plugin `plugin.json`, `metadata.json`, Python package version, manuals, build scripts, and changelog use the same release version.
- [ ] `CHANGELOG.md` describes user-visible changes and compatibility limits.
- [ ] JLCPCB data and verification date were checked against current official sources.
- [ ] No credentials, private board files, generated reports, or local paths are included.

## Automated verification

- [ ] `python -m coverage run -m pytest -q`
- [ ] `python -m coverage report --fail-under=68`
- [ ] `ruff check plugin tests scripts docs/conf.py`
- [ ] `ruff format --check plugin tests scripts docs/conf.py`
- [ ] `mypy plugin/emi_guardian`
- [ ] `bandit -r plugin/emi_guardian plugin/open_dashboard.py plugin/quick_scan.py -ll`
- [ ] `python -m compileall -q plugin tests scripts`
- [ ] `node --check plugin/emi_guardian/web/app.js`
- [ ] `shellcheck installers/linux/*.sh installers/macos/*.command`
- [ ] `sphinx-build -W --keep-going -b html docs docs/_build/html`
- [ ] `pip-audit --strict --requirement plugin/requirements.txt`
- [ ] `python scripts/check_package.py`
- [ ] `python scripts/build_package.py`
- [ ] A second build produces identical artifact hashes.
- [ ] Every ZIP passes integrity and path-traversal checks.
- [ ] Python 3.9, 3.13, and 3.14 checks pass.
- [ ] Japanese and English manuals build with valid internal anchors.

## Platform installation

- [ ] Windows install/update and uninstall were executed on a current supported Windows system.
- [ ] macOS install/update and uninstall were executed on a current supported macOS system.
- [ ] Linux install/update and uninstall were executed on a current supported distribution.
- [ ] No `_emi-guardian-backups` or installer staging directory remains below the KiCad `plugins` directory.
- [ ] Update creates no copy of the previous plugin in either the KiCad tree or OS temporary storage; a controlled placement failure removes the incomplete destination and a clean rerun succeeds.
- [ ] Exactly one installable `plugins/emi-guardian` directory remains after a successful update.
- [ ] User settings remain after normal uninstall.

## KiCad 10.0.5 acceptance

- [ ] Plugin appears under Tools → External Plugins.
- [ ] Python 3.9 managed environment is created successfully.
- [ ] Dashboard launches and uses the blue theme.
- [ ] Japanese finding title, description, metrics, and recommendation are Japanese.
- [ ] Board preview zoom, pan, and layer toggles work.
- [ ] Show location in KiCad selects evidence and zooms where supported.
- [ ] 90-degree corners are not reported under the default 75-degree threshold.
- [ ] Acute corners outside pad/via areas are reported.
- [ ] Long-net route path does not blindly sum branches.
- [ ] Track and via presets support multiple selections.
- [ ] Fix and silkscreen previews show overlays.
- [ ] Every antenna keepout excludes all pads, the width-`t` GND backbone, explicit GND tracks, and protected perimeter GND.
- [ ] Stale antenna findings are revalidated against the current board before a rule area is offered.
- [ ] Proposed tracks and vias remain fully inside the outer Edge.Cuts and outside internal cutouts, including their complete copper width/annulus.
- [ ] Initial-placement preview shows footprint body, translated pads, reference/value text, identity, and movement vector.
- [ ] Heartbeat and reconnect work across a long idle period and sleep/resume test.
- [ ] Convex-first outline honors target vertex settings and preserves only safe source concavities.
- [ ] Dry-run and mutation confirmation gates work.
- [ ] DRC, zone refill, Undo, Gerber, and manufacturing-bundle checks pass on a disposable board copy.

## GitHub release

- [ ] GitHub Actions succeeds on `main` and tag.
- [ ] Tag is annotated as `vX.Y.Z`.
- [ ] Release notes state that the plugin is not an EMC or manufacturing guarantee.
- [ ] Platform installers, manual archive, PCM archive, source archive, manuals, `SHA256SUMS`, and `BUILD-INFO.json` are attached.
- [ ] Downloaded release assets match `SHA256SUMS`.
