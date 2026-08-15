# 変更履歴

[English](CHANGELOG.md)

## 0.0.2 — 2026-08-13

- GND ベタのアンテナ検出を、保守的な protected-backbone model に再設計しました。すべての物理 pad を除外し、同一ネットの GND pad、via、明示配線、既存外周 GND、および broad GND core までの幅 `t` の既存銅箔経路を保護します。
- 閉じた Edge.Cuts または現在の connectivity proof を取得できない場合は、fail closed するようにしました。Floating island と接続済み residual appendage は排他的に分類されます。
- Rule area 案を計画直前に現在の基板で再検証し、pad、GND 経路、外周 band、zone geometry の変更後に stale finding から keepout が作成されないようにしました。
- Rule area は証明済み residual と完全に同じ形状に限定し、外側へ拡張しません。Pad、明示 GND 配線、internal cutout、基板境界、未証明領域に触れる案は拒否します。
- Concave outline と internal Edge.Cuts hole に対する新規銅箔の containment check を強化しました。配線の全幅と via annulus 全体が基板内にあり、異ネットの track、pad、via、filled zone から離れている必要があります。
- 2 layer return-path 判定に、最小配線長、endpoint exclusion、継続的な unsupported length/fraction、一般的な power net の除外、より厳しい GND detour ratio/excess 条件を追加しました。
- Initial placement preview に、schematic block、component identity、移動先 footprint body、移動後 pad、reference/value field、movement vector を表示します。
- Installer による旧 plugin backup 作成を廃止しました。新 payload だけを stage し、install/update 後は `plugins/emi-guardian` を 1 個だけ残し、legacy backup/staging directory を削除します。
- Pad/thermal protection、perimeter protection、Edge.Cuts 欠落、stale finding、狭い concavity、異ネット filled zone clearance、installer cleanup、placement preview geometry の regression test を追加しました。
- v0.0.2 に合わせて日英 manual、acceptance procedure、package metadata、release check、deterministic build input を更新しました。

## 0.0.1 — 2026-08-13

- KiCad 上の場所検索で UUID string ではなく `KIID` protobuf object を渡すように修正しました。
- Marker click detail、hover summary、list-to-preview highlight、preview location action を復旧しました。
- Finding marker を残したまま、preview layer の全表示／全非表示を切り替えられるようにしました。
- Outline、repair、silkscreen、stitching、placement preview に既存基板 layer を追加しました。
- Area increase の拒否、current outline smoothing、grid-snapped pre-fillet vertex を使う fillet を追加しました。
- GND via stitching と optional perimeter-via rebuild に、vertex priority、full-annulus copper、spacing/clearance、partial-selection deletion safeguard を追加しました。
- Wildcard THT padstack を含む zone/track/pad/via の ground-connectivity component を追加しました。
- Connected GND appendage の通常修正を shape-matched rule area とし、既存 GND fill 上の冗長 track を拒否します。
- Antenna、silkscreen、stitching、component placement 案の一部採用を追加しました。
- 2 layer の一般的な return-via warning を、reference gap、ground-return detour、ground bottleneck 判定へ置き換えました。
- 0°/90°/±45° silkscreen candidate、0.10 mm stroke、MountingHole/LOGO suppression、manual-review fallback、hidden Fab reference を追加しました。
- Schematic block に基づく dry-run initial placement と matching-net capacitor proximity planning を追加しました。
- Diagonal mode、sharp-corner score、electrically-long-net path、long-idle reconnect を修正しました。
- Python 3.9、package、installer lifecycle、deterministic build、geometry、localization、API boundary の regression check を追加しました。

## 0.2.0 — 2026-08-11

- 2026-08-11 に確認した公開情報に基づく JLCPCB 2 layer manufacturing support を追加しました。
- **economy** と **capability-limit** profile、board thickness、solder mask、copper weight、surface finish、routing/V-cut 選択を日英 dashboard に追加しました。
- Track width 0.1、0.2、0.3、0.4、0.5、0.8、1.0、1.5、2.0、3.0、5.0 mm と、via 0.25/0.15 mm、0.60/0.30 mm の preset を追加しました。
- Order combination、board size、stackup mismatch、routing width/clearance、via geometry/spacing、copper-to-edge、silkscreen の geometric DFM check を追加しました。
- DFM JSON、order setting、routing preset、KiCad custom rule template、日英 order note を含む manufacturing bundle を追加しました。
- 日英 user manual、JLCPCB reference、manufacturing acceptance test を追加し、configuration schema を version 2 へ移行しました。

## 0.1.0 — 2026-08-11

- KiCad 10.0.5+ 向け initial engineering preview です。
- Official IPC adapter、ground-pour antenna analysis、ranked remediation、routing-risk score、closed-form electrical estimate を追加しました。
- Bilingual localhost dashboard、report export、silkscreen planner、filleted Edge.Cuts proposal を追加しました。
- Destructive-operation safety gate、backup、exact-net matching、transaction requirement、regression test を追加しました。後の release では installer backup workflow を廃止しています。
- Default configuration、日英 requirement traceability、KiCad-in-the-loop acceptance test、manual-install archive を追加しました。
