# Publishing the release on GitHub

This guide publishes the EMI Guardian 0.0.2 source archive as a new GitHub repository and creates a tagged release. Replace account and repository placeholders with your own values.

## 1. Verify the release

Run the release checklist and the complete local validation:

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

Review `dist/SHA256SUMS`, `dist/BUILD-INFO.json`, the KiCad 10.0.5 acceptance-test record, and the current manufacturing-source verification date.

## 2. Create an empty repository

Create a new repository on GitHub, for example `kicad-emi-guardian`. The source already contains a README, license, and `.gitignore`, so leave the corresponding GitHub initialization options clear.

## 3. Push the source

Extract the source archive, open a terminal at its root, and run:

```bash
git init
git branch -M main
git add .
git commit -m "Release EMI Guardian v0.0.2"
git remote add origin https://github.com/<USER_OR_ORG>/kicad-emi-guardian.git
git push -u origin main
```

For SSH authentication, use:

```bash
git remote add origin git@github.com:<USER_OR_ORG>/kicad-emi-guardian.git
```

## 4. Create and push the tag

```bash
git tag -a v0.0.2 -m "EMI Guardian v0.0.2"
git push origin v0.0.2
```

Confirm that the bundled GitHub Actions workflow succeeds before publishing the release.

## 5. Create a GitHub Release

Open **Releases → Draft a new release** and use:

- Tag: `v0.0.2`
- Title: `EMI Guardian v0.0.2`
- Notes: base them on the 0.0.2 section of `CHANGELOG.md`
- Pre-release: disabled
- Latest release: enabled

Recommended assets:

```text
emi-guardian-0.0.2-windows-installer.zip
emi-guardian-0.0.2-macos-installer.zip
emi-guardian-0.0.2-linux-installer.zip
emi-guardian-0.0.2-all-platform-installers.zip
emi-guardian-0.0.2-manual-install.zip
openai-emi-guardian-0.0.2-pcm.zip
kicad-emi-guardian-0.0.2-source.zip
emi-guardian-0.0.2-user-manuals.zip
SHA256SUMS
BUILD-INFO.json
```

State the KiCad and Python minimums, the public-IPC navigation limitation, the live-KiCad acceptance coverage, and the fact that the plugin does not certify EMC or manufacturing acceptance.

## 6. Optional GitHub CLI workflow

After authenticating `gh` and pushing the tag:

```bash
gh release create v0.0.2 \
  dist/emi-guardian-0.0.2-windows-installer.zip \
  dist/emi-guardian-0.0.2-macos-installer.zip \
  dist/emi-guardian-0.0.2-linux-installer.zip \
  dist/emi-guardian-0.0.2-all-platform-installers.zip \
  dist/emi-guardian-0.0.2-manual-install.zip \
  dist/openai-emi-guardian-0.0.2-pcm.zip \
  dist/kicad-emi-guardian-0.0.2-source.zip \
  dist/emi-guardian-0.0.2-user-manuals.zip \
  dist/SHA256SUMS \
  dist/BUILD-INFO.json \
  --title "EMI Guardian v0.0.2" \
  --notes-file RELEASE_NOTES.md
```

`--generate-notes` can replace `--notes-file`, but manually add limitations and acceptance-test status.

## 7. Recommended maintenance

Protect `main`, use pull requests, collect KiCad/OS/Python/error details in bug reports, update manufacturing values together with their verification date, attach built archives to Releases rather than committing them, and keep every version-bearing file synchronized for future releases.
