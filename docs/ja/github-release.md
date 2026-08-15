# GitHubへの公開手順

本ページは、EMI Guardian 0.0.2のソースZIPをそのままGitHubリポジトリへ登録し、タグとReleaseを作る手順です。認証情報、ユーザー名、リポジトリ名は環境に合わせて置き換えてください。

## 1. 公開前の確認

1. `RELEASE_CHECKLIST.md`を確認します。
2. 次を実行します。

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

3. `dist/SHA256SUMS`と`dist/BUILD-INFO.json`を確認します。
4. KiCad 10.0.5の実機受入試験を実施し、結果を記録します。
5. 製造情報が古くなっていないか再確認します。

## 2. GitHubで空のリポジトリを作る

GitHub上で新規リポジトリを作成します。ローカル側にREADME、LICENSE、`.gitignore`が含まれているため、GitHubの作成画面ではこれらを追加せず、空のリポジトリとして作ると履歴が単純になります。

例のリポジトリ名:

```text
kicad-emi-guardian
```

## 3. ソースを初回pushする

ソースZIPを展開し、そのルートで実行します。

```bash
git init
git branch -M main
git add .
git commit -m "Release EMI Guardian v0.0.2"
git remote add origin https://github.com/<USER_OR_ORG>/kicad-emi-guardian.git
git push -u origin main
```

SSHを使用する場合は、remoteを次の形式にします。

```bash
git remote add origin git@github.com:<USER_OR_ORG>/kicad-emi-guardian.git
```

## 4. タグを作る

```bash
git tag -a v0.0.2 -m "EMI Guardian v0.0.2"
git push origin v0.0.2
```

タグをpushすると、同梱の`.github/workflows/ci.yml`が通常の検査を実行します。Release公開前にActionsが成功していることを確認してください。

## 5. GitHub Releaseを作る

GitHubのリポジトリ画面で **Releases → Draft a new release** を開きます。

- Tag: `v0.0.2`
- Title: `EMI Guardian v0.0.2`
- Release notes: `CHANGELOG.md`の0.0.2節を基礎にする
- Pre-release: オフ
- Latest release: オン

次の成果物を添付することを推奨します。

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

デモレポートは任意です。Release説明には、KiCad 10.0.5以降、Python 3.9以降、公開IPC使用、ライブKiCad実機試験の範囲、EMC適合性を保証しないことを記載してください。

## 6. GitHub CLIを使う場合

GitHub CLIで認証済みなら、タグpush後に次のように公開できます。

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

`RELEASE_NOTES.md`を用意しない場合は、`--generate-notes`を使用できます。ただし、制限事項と実機試験状況は手動で追記してください。

## 7. 公開後の推奨運用

- `main`を保護し、Pull Request経由で変更します。
- バグ報告テンプレートではKiCad版、OS、Python版、右下のPlugin警告、再現用基板の有無を収集します。
- 製造制約の更新は、確認日と公式参照先を同時に更新します。
- バイナリ成果物はソース管理へ直接コミットせず、GitHub Releaseへ添付します。
- 次のリリースでは`CHANGELOG.md`、Plugin manifest、PCM metadata、ドキュメント、タグを同じ版番号にします。
