# 開発とAPI互換性

## ソース構成

- `plugin/`: KiCad runtime payloadとPCM manifest
- `plugin/emi_guardian/`: KiCad非依存モデル、解析、提案生成、controller、report、IPC adapter
- `plugin/emi_guardian/web/`: ローカルdashboardのHTML、CSS、JavaScript
- `docs/en/`と`docs/ja/`: 同一構造の日英文書ソース
- `installers/`: OS別導入・更新・削除
- `tests/`: unit、安全性、package、文書のregression test
- `tools/`: site/manual生成、検査、demo生成、決定的package生成
- `.github/`: CI、CodeQL、Pages、Renovate設定
- `resources/`: KiCad Package and Content Manager用asset

## 互換性方針

- KiCad 10以降のみ対応
- Python 3.9以降
- `kicad-python>=0.7.1,<1.0`
- 正規レイヤー名と機能検出を優先
- 安全な機能がない場合は失敗側へ閉じる
- カスタムDRCマーカーは安定公開IPCにないため、選択＋ズーム
- `run_action`の内部アクション名は不安定としてフォールバック扱い
- 板厚・色・プロジェクトルールは基板テキストを直接変更せず、照合・出力

## ローカル検査

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

Python 3.9相当の構文検査、manifest、metadata、JSON、HTML anchor、installer構造、shell構文、ZIPパストラバーサル、決定的タイムスタンプ、ハッシュを検査します。

## ドキュメント

```bash
python tools/build_site.py --output site
```

MyST Markdownを日英正本にし、日英treeには同じ相対パスのMarkdownを配置します。`tools/build_site.py`が対応関係と生成後のlocal linkを検査し、`markdown-it-py`が取扱説明書を単独HTMLへ変換します。コードコメントとdocstringは英語です。

## GitHub CI

`.github/workflows/ci.yml`はPython 3.9、3.13、3.14で試験し、Ruffのlint/format、mypy type check、YAML、JavaScript、POSIX shell、coverage、日英Sphinx strict build、依存脆弱性、KiCad packageを検証し、2回の完全なrelease buildを比較します。別workflowがCodeQLでPythonとJavaScriptを解析し、検証済みsiteをGitHub Pagesへ公開します。Renovate設定がPython、文書toolchain、GitHub Actionsの依存関係を監視します。

## 実機受入

モック試験はKiCad GUI、OSセキュリティ、実際のPlugin管理環境、Undo、Gerberを証明しません。各KiCad minor版と対象OSで[受入試験](acceptance-test.md)を実行します。
