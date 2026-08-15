# EMI Guardian v0.0.2

[English](RELEASE_NOTES.md)

EMI Guardian v0.0.2 は、KiCad 10.0.5 以降を対象とする**リリース前 engineering build**です。Stable release の前に、実際の KiCad で acceptance test を行うための版です。

## 主な変更

### より安全な install と update

- Windows、macOS、Linux installer は、OS temporary directory を含めて旧 plugin の copy を作成しません。
- Installer は新 payload だけを stage、validate します。Replacement 前に legacy `_emi-guardian-backups` と `emi-guardian.installing-*` を削除し、KiCad が duplicate plugin を scan しないようにします。
- Automatic rollback は行いません。Final placement が失敗した場合は incomplete destination を削除し、原因を修正してから installer を再実行します。

### GND ベタの antenna detection と remediation

- Local narrow-tail heuristic を conservative protected-backbone model に置き換えました。Morphological opening width は、configured narrow-neck width と mandatory connection width `t` の大きい方です。
- Largest broad region を primary GND core とします。Secondary broad region、same-net GND pad/via/track、protected perimeter-GND component は、existing copper を通して primary core に接続されたままでなければなりません。
- 解析 layer 上の全 physical pad を候補から除外します。Same-net pad body、launch/thermal region、via、explicit GND track、perimeter GND、required width-`t` corridor を automatic copper removal から保護します。
- Candidate residual は four-neighbor connectivity を使用し、virtual removal が全 mandatory connection を保つ場合だけ採用します。Filled geometry、GND pad anchoring、raster topology、closed Edge.Cuts の情報が不足する場合は fail closed します。
- Rule area は証明済み residual と同一形状で、outward margin を持ちません。Pad、mandatory corridor、explicit GND track、protected perimeter、board boundary、internal cutout に触れる proposal は拒否します。
- Proposed track/via は、outer Edge.Cuts、internal cutout、other-net track/pad/via/filled zone に対して全銅箔幅または annulus で検証します。Existing same-plane GND fill に完全に重なる track は冗長として拒否します。
- Mutation 直前に current board を再取得し、analysis と fix planning を再実行します。Preview から target、net、layer、geometry、dimension、parameter が変化していれば、board を変更せず request 全体を中止します。

### Return path と initial placement

- 2 layer board の return-path screening を調整しました。Generic nearby-return-via warning は既定で無効です。Reference-plane gap は endpoint breakout を除外した後の unsupported length/fraction を要求し、common power net を除外します。GND detour は ratio と absolute excess の両方を要求します。
- Schematic-block initial-placement preview に、destination footprint body、translated pad、reference/value field、block box、component identity label、movement vector を追加しました。

### v0.0.1 の workflow correction

- Finding location では UUID を KiCad `KIID` protobuf message に変換します。
- Finding marker の detail、hover、list highlight、preview focus と、layer の全表示／全非表示が機能します。
- Outline optimization は area increase を拒否し、optimize、smooth、fillet を別 operation として提供します。
- Antenna、silkscreen、stitching、placement proposal は一部採用できます。
- Silkscreen は 0.10 mm stroke、0°/90°/±45°、bounded owner distance、MountingHole/LOGO suppression、manual-review fallback を使用します。
- Track/via preset は複数選択でき、dashboard は heartbeat/reconnect を行い、idle shutdown は既定で無効です。

## 動作条件

- KiCad 10 series の 10.0.5 以降
- KiCad Plugins preference で選択された Python 3.9 以降
- KiCad API が有効

## 安全上の制限

- Dry-run は既定で有効です。すべての modification を確認し、zone refill、KiCad DRC、Gerber、mechanical review、manufacturer DFM を実行してください。
- Finding navigation は non-destructive selection-and-zoom で、persistent native DRC marker ではありません。
- EMI finding は geometry と configuration に基づく screening であり、EMC compliance や放射構造がないことを証明しません。
- Antenna proof は保守的ですが discretized です。Raster resolution、filled-zone freshness、stackup assumption、circuit intent の不足により、automation が抑止される場合があります。
- 実基板の全接続を screenshot だけで検証することはできません。元の `.kicad_pcb` による acceptance test が必要です。

## この build で実施した検証

- 146 件の regression、geometry、randomized safety、localization、controller、server、installer、documentation、package test を実行しました。
- Fixed-seed suite で 48 tail/pad geometry、32 broad-region bridge geometry、concave outline 上の 960 full-width track proposal を検証しました。
- Python 3.9 parsing、bytecode compilation、JavaScript syntax、POSIX shell syntax、manifest/config、safety contract、documentation consistency を検証しました。
- Release ZIP の CRC、duplicate entry、path traversal、cache artifact、fixed timestamp、executable permission を検証しました。
- Extracted Linux/macOS installer で isolated home を使った fresh install、update、legacy cleanup、cache refresh、backup-free uninstall を実行しました。
- 2 回の clean build で、すべての release artifact の SHA-256 が一致しました。Native Windows と live KiCad GUI/IPC は target environment で acceptance test が必要です。
