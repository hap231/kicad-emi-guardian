# EMI Guardian 0.0.2 インストーラー

このフォルダーのスクリプトは、KiCad 10用IPC Pluginのインストール、更新、アンインストールをユーザー権限で行います。管理者権限は不要です。

## 実行前

1. KiCadとPCB Editorで基板を保存します。
2. KiCadとPCB Editorを完全に終了します。
3. ZIPをすべて展開します。ZIP内から直接スクリプトを実行しないでください。

## Windows

- インストールまたは更新: `Install-or-Update.cmd`をダブルクリック
- アンインストール: `Uninstall.cmd`をダブルクリック
- KiCadの別バージョンディレクトリを指定する場合:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-or-update.ps1 -KiCadVersion 10.0
```

## macOS

Finderで`install-or-update.command`をダブルクリックします。初回にmacOSが実行を拒否した場合は、ターミナルで次を実行します。

```bash
chmod +x install-or-update.command uninstall.command
./install-or-update.command
```

アンインストールは`uninstall.command`を使用します。

## Linux

```bash
chmod +x install-or-update.sh uninstall.sh
./install-or-update.sh
```

アンインストール:

```bash
./uninstall.sh
```

## 更新時の動作

インストーラーは、KiCadの`plugins`配下だけでなくOSの一時ディレクトリにも**旧Pluginのバックアップを作成しません**。新しいペイロードだけをOS一時ディレクトリで検査した後、既存Pluginを削除して配置します。最終配置に失敗した場合は不完全な配置を削除し、インストーラーを再実行する必要があります。自動ロールバックは意図的に行いません。旧版が作成した`_emi-guardian-backups`および`emi-guardian.installing-*`は、KiCadが子ディレクトリをPluginとして走査する可能性があるため自動削除します。KiCadが作成したPlugin専用Python環境も削除され、次回起動時に再作成されます。通常アンインストールでは設定ファイルとエクスポート済みレポートを保持します。

## 起動

1. KiCadプロジェクトマネージャの`設定 > 設定... > Plugins`で`Enable KiCad API`を有効にします。
2. Python 3.9以上のインタープリターが選択されていることを確認します。
3. KiCadを再起動し、PCB Editorで基板を開きます。
4. `ツール > 外部プラグイン > Open EMI Guardian`を選択します。

表示されない場合は、PCB Editor右下の警告、Pluginの配置先、Python環境作成エラーを確認してください。

## 配置先

- Windows: `%USERPROFILE%\Documents\KiCad\10.0\plugins\emi-guardian`
- macOS: `~/Documents/KiCad/10.0/plugins/emi-guardian`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/KiCad/10.0/plugins/emi-guardian`

## 注意

スクリプトは現在のユーザーのKiCad 10データ領域だけを操作します。`--force`または`-Force`は、KiCadを閉じられない特殊な場合に限り使用してください。開いた基板がある状態で強制更新すると、Plugin環境と実行中プロセスの状態が不整合になる可能性があります。
