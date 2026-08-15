# 変更履歴

[English](../../en/project/changelog.md)

## 0.0.1 — 2026-08-13

- KiCad 10.0.5以降向けIPC Pluginとして、形状ベースEMIスクリーニング、日英ローカル画面、レポート出力、シルク整理、基板外形案、Dry-run既定の変更機能を追加しました。
- GNDベタ解析では、pad、同一ネットのpad・via・明示配線、外周GND、広いGNDコアまでの必須銅箔経路を保護してから、残差突起を分類するようにしました。
- 接続証明がない場合の安全側停止、現在基板での再検証、残差と同形状のkeepout、凹形状・内部cutout・異ネット銅箔を考慮した配線全幅とvia annulusの基板内判定を追加しました。
- GND bridge、stitching via、bridge＋viaを順位付けし、提案の部分採用と、KiCadが必要機能を提供する場合のtransaction付き変更を追加しました。
- Stub、並走、鋭角、電気的経路長、reference gap、return detour、bottleneck、基板端距離、差動長差を検査し、カテゴリ採点へ上限付き減衰を適用しました。
- Impedance、delay、critical length、resonance、skin depth、正規化crosstalkを推定できるようにしました。
- JLCPCB 2層の低コスト／能力限界profile、形状DFM、配線・via preset、発注記録、custom rule出力、日英製造ガイドを追加しました。
- 基板、指摘、修正、シルク、stitching、外形、schematic block配置を、layer切替とpan/zoom付きで表示し、KiCad上の非破壊な選択＋zoomへ連携するようにしました。
- Windows、macOS、Linux、手動導入、PCM、source、demo report、日英manualの決定的archiveとchecksumを追加しました。
- Python互換性、package、installer lifecycle、geometry、localization、randomized safety、documentation、API boundaryのregression testを追加しました。
- Quality、unit test、documentation、dependency audit、再現可能package、CodeQL、Renovate、日英GitHub Pages用のGitHub Actionsを追加しました。
