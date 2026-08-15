# EMI Guardian v0.0.2 検証報告

[English](VERIFICATION_REPORT.md)

**Build status:** release 前 engineering build

**Target:** KiCad 10.0.5+、Python 3.9+

**Verification date:** 2026-08-15

## 完了した automated verification

- Analysis、score、geometry、GND connectivity、protected-backbone antenna detection、remediation、stale-plan rejection、silkscreen、outline、via stitching、initial placement、localization、controller、HTTP、adapter、installer、documentation、manifest、packaging を対象に 146 件の pytest を実行しました。
- Deterministic randomized safety suite では、48 件の ground-tail/pad case、32 件の narrow mandatory bridge、24 件の concave Edge.Cuts と各 40 件の random track proposal を検証しました。
- Plugin 全体を Python 3.9 grammar で parse し、plugin、script、test を bytecode compile しました。
- Node.js による JavaScript syntax、Bash による Linux/macOS script syntax を検証しました。
- KiCad manifest、PCM metadata、configuration schema 5、runtime version、KIID boundary、required module、zero-backup installer contract、apply-time revalidation contract を検証しました。
- 日英 manual coverage、schema version、zero-backup/no-rollback、active-board revalidation guidance の documentation regression check を実行しました。
- 9 個の release archive について、ZIP CRC、duplicate entry、path traversal、cache artifact、fixed timestamp、executable bit を検証しました。
- Extracted Linux/macOS package で isolated home を使用し、fresh install、replacement update、legacy cleanup、managed environment refresh、backup-free uninstall を実行しました。
- 2 回の clean package build を SHA-256 で比較し、再現性を確認しました。
- 公式 `kicad-python-packager` validator は plugin directory と生成済み PCM ZIP の両方を受理しました。KiCad CLI 10.0.5 は同梱 KiCad template を正常に読み込み DRC を完了しました。報告された violation は upstream template に属し、plugin finding ではありません。

## High-risk regression

### Installer duplicate-plugin crash prevention

- Installer source は、旧 `plugins/emi-guardian` を KiCad plugin directory または OS temporary directory に copy しません。
- 新 payload だけを stage し、replacement 前に legacy backup/staging directory を削除します。
- Successful update 後は `plugins/emi-guardian` が 1 個だけ残ります。Final copy failure では incomplete destination を削除し、automatic rollback は行いません。

### Pad と mandatory GND の保護

- 対象 layer の全 physical pad を removable antenna geometry から除外します。
- Same-net GND pad body と launch/thermal capture region を mandatory terminal とします。
- Same-net via、explicit track、existing perimeter GND、secondary broad core、width-`t` path を保護します。
- GND pad anchoring、valid Edge.Cuts、connectivity proof が不足する場合、automatic keepout generation を無効にします。
- Virtual removal 後もすべての mandatory group が primary broad GND core に接続されることを要求します。

### Rule area と新規銅箔の containment

- Rule area は current-board で証明した residual と同一形状で、outward margin はありません。
- Pad、protected corridor、explicit GND trace、protected perimeter、board boundary、cutout に触れる keepout は拒否します。
- Proposed trace/via は全幅・annulus で board containment と other-net clearance を検証します。
- Mutation 直前に analysis/planning を再実行し、pad、zone、track、outline、polygon、width、safety parameter が変化していれば、board mutation を行わず apply request 全体を拒否します。

### 2 layer return-path false positive の制御

- Generic transition-return-via rule は既定で無効です。
- Reference gap は minimum route length、endpoint exclusion、unsupported length/fraction を要求します。
- Common power net を既定で除外し、GND detour は高い ratio と十分な absolute excess の両方を要求します。

### Placement preview の可読性

- Destination footprint outline、translated pad、reference/value field、block identity、component label、movement vector を preview payload に含めます。
- Locked footprint は移動しません。

## この環境で完了できない検証

- Live KiCad 10.0.5 GUI/IPC による mutation、selection、layer activation、zoom behavior
- Native Windows PowerShell と Windows security product の interaction
- macOS Finder/Gatekeeper の launch behavior
- 元の `.kicad_pcb` がない状態での user board connectivity と antenna candidate の検証
- Physical EMC、signal integrity、thermal、mechanical、fabrication result

製造前に、実基板の copy で日英 acceptance procedure を実行し、zone refill、KiCad DRC、Gerber、JLCPCB upload DFM、すべての selected mutation を確認してください。本 plugin は engineering screening と workflow assistance のための tool であり、EMC または manufacturing の保証ではありません。
