# EMI Guardian release checklist

[English](RELEASE_CHECKLIST.md)

## Source と version

- [ ] `pyproject.toml`、Plugin `plugin.json`、`metadata.json`、Python package、manual、build script、changelog の release version が一致している。
- [ ] `CHANGELOG.md` と `CHANGELOG.ja.md` に user-visible change と compatibility limit が記載されている。
- [ ] JLCPCB data と verification date を最新の公式 source と照合した。
- [ ] Credential、private board file、generated report、local path が含まれていない。

## Automated verification

- [ ] `python -m coverage run -m pytest -q`
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
- [ ] 2 回目の build で artifact hash が一致する。
- [ ] すべての ZIP が integrity と path-traversal check に合格する。
- [ ] Python 3.9、3.13、3.14 の test が成功する。
- [ ] 日本語 manual と英語 manual の internal anchor が有効である。

## Platform installation

- [ ] Windows、macOS、Linux の install/update/uninstall を、それぞれ現在 support される環境で実行した。
- [ ] KiCad `plugins` directory 以下に `_emi-guardian-backups` または installer staging directory が残っていない。
- [ ] Update は KiCad tree と OS temporary storage のどちらにも旧 plugin copy を作らない。Controlled placement failure では incomplete destination が削除され、その後の clean rerun が成功する。
- [ ] Successful update 後に installable な `plugins/emi-guardian` directory が 1 個だけ存在する。
- [ ] Normal uninstall 後も user setting が保持される。

## KiCad 10.0.5 acceptance

- [ ] Plugin が Tools → External Plugins に表示され、Python 3.9 managed environment が正常に作成される。
- [ ] Dashboard が起動し、blue theme と日英 UI が機能する。
- [ ] 日本語 finding の title、description、metric、recommendation が日本語である。
- [ ] Board preview の zoom、pan、layer toggle、location navigation が機能する。
- [ ] Default 75° threshold では 90° corner を報告せず、pad/via 外の acute corner を報告する。
- [ ] Long-net route が branch の単純合計にならない。
- [ ] Track/via preset が複数選択でき、fix/silkscreen overlay が表示される。
- [ ] Antenna keepout は全 pad、幅 `t` の GND backbone、明示 GND track、protected perimeter GND を除外する。
- [ ] Stale antenna finding は rule area 提示前に current board で再検証される。
- [ ] Proposed track/via の全幅・annulus が outer Edge.Cuts 内かつ internal cutout 外にある。
- [ ] Initial-placement preview に footprint body、translated pad、reference/value、identity、movement vector が表示される。
- [ ] Long idle と sleep/resume 後も heartbeat/reconnect が機能する。
- [ ] Convex-first outline が target vertex を尊重し、安全な source concavity だけを保持する。
- [ ] Dry-run と mutation confirmation gate が機能する。
- [ ] Disposable board copy で DRC、zone refill、Undo、Gerber、manufacturing bundle を確認する。

## GitHub release

- [ ] `main` と tag で GitHub Actions が成功する。
- [ ] `vX.Y.Z` annotated tag を作成する。
- [ ] Release note に EMC または manufacturing guarantee ではないことを明記する。
- [ ] Platform installer、manual、PCM、source、manuals、`SHA256SUMS`、`BUILD-INFO.json` を添付する。
- [ ] Download した release asset が `SHA256SUMS` と一致する。
