# アーキテクチャ

```text
KiCad 10+ PCB Editor
        │ 公開IPC API / kicad-python
        ▼
KicadIpcAdapter
  snapshot / selection / layer / ping / reconnect / transactions
        │ mm単位のKiCad非依存スナップショット
        ▼
解析・提案コア
  raster + antenna + noise + quantitative
  fixes + silkscreen + edge_optimizer + manufacturing
        │ JSON化可能な結果、根拠ID、処理時間
        ▼
GuardianController
  キャッシュ、設定、ロック、安全ゲート、プレビューpayload
        │
        ├── token保護localhost HTTP API
        ├── 青系日英HTML/CSS/JavaScript UI
        ├── 基板／修正／シルクSVGプレビュー
        ├── HTML / JSON / Markdown / JLCPCB bundle
        └── 外部ソルバ交換manifest
```

## 互換性境界

`kipy`をimportするのは`kicad_adapter.py`です。KiCad 10の正規レイヤー名と機能検出を優先し、旧SWIG `pcbnew.ActionPlugin`へ依存しません。選択やpingが失敗した場合は限定回数だけクライアントを再作成します。

## ドメインモデル

KiCadオブジェクトをmm単位のdataclassへ変換します。配線は元KiCadアイテムIDを保持し、円弧近似フラグも保持します。解析結果は根拠IDを持つため、UIからKiCad選択へ戻れます。

## プレビュー

コントローラは配線、ビア、パッド、フットプリント、既存シルク、ゾーン、外形、指摘を件数制限付きで返します。ブラウザーは同じ基板payloadへ修正案とシルク案を重ね、レイヤー表示、zoom、panをクライアント側で処理します。

## 書き込み境界

書き込み要求を調停できるのはコントローラだけです。アダプタは既存ネット完全一致、トランザクション、Dry-run、確信度、明示確認を満たした場合だけ変更します。外形置換はバックアップと追加の確認を要求します。

## ローカルUI

loopback、一時ポート、ランダムトークン、要求制限、CSPを使用します。無操作終了は設定可能ですがv0.0.2の既定は無効です。ブラウザーheartbeatはKiCad IPCのpingと再接続を起動します。
