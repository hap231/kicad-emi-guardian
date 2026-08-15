# インストール、更新、アンインストール

## 対応環境

- KiCad 10.0.5以降
- Python 3.9以降
- Windows、macOS、Linux
- PCB Editorで基板を開いた状態

KiCad 9以前は対象外です。処理前に全KiCadウィンドウを終了してください。

## 推奨: OS別インストーラー

### Windows

`emi-guardian-0.0.2-windows-installer.zip`を展開し、`Install-or-Update.cmd`を実行します。更新も同じファイルです。削除は`Uninstall.cmd`です。

既定配置:

```text
<Documents>\KiCad\10.0\plugins\emi-guardian\plugin.json
```

### macOS

`emi-guardian-0.0.2-macos-installer.zip`を展開し、`install-or-update.command`を実行します。実行権限がない場合:

```bash
chmod +x install-or-update.command uninstall.command
./install-or-update.command
```

削除は`./uninstall.command`です。

既定配置:

```text
~/Documents/KiCad/10.0/plugins/emi-guardian/plugin.json
```

### Linux

```bash
chmod +x install-or-update.sh uninstall.sh
./install-or-update.sh
```

削除は`./uninstall.sh`です。

既定配置:

```text
~/.local/share/KiCad/10.0/plugins/emi-guardian/plugin.json
```

## インストーラーの動作

- 現在のユーザーだけへ導入
- KiCadの`plugins`配下にもOS一時ディレクトリにも旧Pluginのバックアップを作成しない
- 新しいペイロードだけをOS一時ディレクトリで検査してから置換
- 最終配置失敗時は不完全な配置を削除し、ロールバックせず再実行を要求
- 旧`_emi-guardian-backups`と残留ステージングフォルダーを自動削除
- KiCad管理Python環境を削除し、次回起動時に再作成
- 通常アンインストール時は設定とレポートを保持

新しいペイロードだけをOS一時ディレクトリで検査してから既存Pluginを削除します。最終配置に失敗した場合は不完全な配置を削除し、自動ロールバックは行いません。原因を修正してインストーラーを再実行してください。

管理者権限は通常不要です。KiCadを起動したまま強制更新しないでください。

## 手動インストール

`emi-guardian-0.0.2-manual-install.zip`を展開し、`emi-guardian`フォルダーを上記`plugins`ディレクトリへ配置します。

正しい構成:

```text
plugins/
└── emi-guardian/
    ├── plugin.json
    ├── requirements.txt
    ├── open_dashboard.py
    ├── quick_scan.py
    └── emi_guardian/
```

`plugin.json`が二重フォルダーの内側に入らないようにします。

## KiCad設定

KiCadプロジェクトマネージャで次を開きます。

```text
設定 → 設定... → Plugins
```

- Enable KiCad APIをオン
- Pythonインタープリターを確認
- KiCadを完全再起動
- PCB Editorで基板を開く

起動場所:

```text
ツール → 外部プラグイン → Open EMI Guardian
```

初回はPlugin専用Python環境の作成に時間がかかる場合があります。環境が完成するまでメニューアクションが表示されないことがあります。

## 更新

旧版を手動削除する必要はありません。各OSのInstall-or-Updateを実行します。Web画面が旧版のままの場合は、ブラウザーを強制再読み込みし、KiCadを再起動します。

## アンインストール

OS別Uninstallを使用します。Plugin本体、KiCad管理Python環境、旧版が残した`_emi-guardian-backups`、残留ステージングフォルダーを削除します。設定とレポートは既定で残ります。

## 表示されない場合

1. `plugins/emi-guardian/plugin.json`を確認
2. KiCad共通Plugins設定を確認
3. Python 3.9以降を確認
4. KiCadを完全終了して再起動
5. PCB Editor右下のPlugin警告を確認
6. インストーラーを再実行して管理環境を再作成

詳細は[取扱説明書](user-manual.md)と[受入試験](acceptance-test.md)を参照してください。
