# 開発とAPI互換性

## ソース構成

- `models.py`: KiCad非依存モデルと根拠ID
- `kicad_adapter.py`: 公開IPC読書き、選択、レイヤー、ping、再接続、トランザクション
- `raster.py`, `antenna.py`, `noise.py`, `quantitative.py`: 解析
- `fixes.py`, `silkscreen.py`, `edge_optimizer.py`: 提案生成
- `manufacturing.py`, `manufacturing_profiles.py`: JLCPCB DFMとプリセット
- `localization.py`: 日英の指摘・DFM表示
- `controller.py`: 調停、キャッシュ、安全確認、プレビューpayload
- `server.py`, `web/`: ローカルAPIと青系UI
- `report.py`, `solver_export.py`: レポートと交換データ
- `installers/`: OS別導入・更新・削除
- `scripts/`: 検査、マニュアル、デモ、決定的パッケージ生成

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

Python 3.9相当の構文検査、manifest、metadata、JSON、HTML anchor、installer構造、shell構文、ZIPパストラバーサル、決定的タイムスタンプ、ハッシュを検査します。

## ドキュメント

```bash
sphinx-build -W --keep-going -b html docs docs/_build/html
doxygen Doxyfile
```

MyST Markdownを日英正本にし、取扱説明書は`markdown-it-py`で単独HTMLへ変換します。コードコメントとdocstringは英語です。

## GitHub CI

`.github/workflows/ci.yml`はPython 3.9、3.13、3.14で試験し、Ruffのlint/format、mypy type check、YAML、JavaScript、POSIX shell、coverage、日英Sphinx strict build、依存脆弱性、KiCad packageを検証し、2回の完全なrelease buildを比較します。別のCodeQL workflowがPythonとJavaScriptを解析し、DependabotがPythonとGitHub Actionsの依存関係を監視します。

## 実機受入

モック試験はKiCad GUI、OSセキュリティ、実際のPlugin管理環境、Undo、Gerberを証明しません。各KiCad minor版と対象OSで[受入試験](acceptance-test.md)を実行します。
