# 設定リファレンス

設定ファイルのスキーマ版は**5**です。画面で変更できる主要項目に加え、詳細JSONで全項目を編集できます。旧スキーマは可能な範囲で移行し、未知の項目は無視し、不正値はファイル置換前に拒否します。

## `antenna`

| 項目 | 既定 | 内容 |
|---|---:|---|
| `ground_net_regex` | GND系正規表現 | 対象GNDネットファミリー |
| `raster_step_mm` | 0.20 | 塗りつぶしゾーンのラスタ刻み |
| `max_raster_cells` | 1,500,000 | 粗密化前の最大セル予算 |
| `narrow_neck_width_mm` | 0.80 | ユーザー指定の狭い首幅 |
| `minimum_appendage_area_mm2` | 0.40 | 最小残差面積 |
| `minimum_appendage_length_mm` | 2.00 | 最小残差測地長 |
| `connectivity_tolerance_mm` | 0.08 | 同一ネット接触判定余裕 |
| `minimum_unanchored_component_area_mm2` | 0.50 | 浮遊成分の最小面積 |
| `required_ground_connection_width_mm` | 1.00 | 必須GND接続路幅`t` |
| `pad_protection_margin_mm` | 0.30 | パッド／サーマル追加保護余白 |
| `via_protection_margin_mm` | 0.20 | 同一ネットビア追加保護余白 |
| `explicit_track_protection_margin_mm` | 0.15 | 明示GND配線の追加保護余白 |
| `perimeter_ground_protection_mm` | 1.00 | 既存外周GND保護帯 |
| `require_safe_removal_connectivity` | true | 除去後接続証明を必須化 |
| `protect_perimeter_ground` | true | Edge.Cuts／外周証明不能時に停止 |
| `protect_explicit_ground_tracks` | true | 意図的なGND配線を保護 |

実効opening幅は`narrow_neck_width_mm`と`required_ground_connection_width_mm`の大きい方です。ラスタ刻みを小さくすると細い形状へ敏感になりますが、セル数と処理時間が増えます。実効解像度で1つの塗りつぶしポリゴンが4近傍の電気的連結成分にならない場合、自動銅箔除去は安全側に停止します。

## `fixes`

| 項目 | 既定 | 内容 |
|---|---:|---|
| `dry_run` | true | 全自動書き込みを遮断 |
| `minimum_apply_confidence` | 0.75 | 適用案の最低確信度 |
| `track_width_mm` | 0.20 | 製造プロファイル基準幅 |
| `adaptive_track_width` | true | 安全な最大幅を探索 |
| `maximum_track_width_mm` | 2.00 | 自動幅の上限 |
| `maximum_bridge_length_mm` | 6.00 | 新規GNDブリッジ最大長 |
| `via_diameter_mm` / `via_drill_mm` | 0.60 / 0.30 | 自動修正ビア寸法 |
| `via_clearance_mm` | 0.25 | 既知銅箔との離隔 |
| `maximum_via_search_radius_mm` | 3.00 | ビア候補探索半径 |
| `rule_area_margin_mm` | 0.00 | 安全証明済み残差を拡張しない |
| `prefer_rule_area_for_appendages` | true | 余剰突起では正確なkeepoutを優先 |
| `reject_redundant_same_plane_tracks` | true | 同一ベタ上だけの配線を拒否 |
| `board_edge_clearance_mm` | 0.10 | 新規銅箔とEdge.Cutsの追加離隔 |
| `require_board_outline_for_new_copper` | true | 配線／ビアに有効外形を必須化 |
| `require_proven_safe_rule_area` | true | 現行保護バックボーン証明を必須化 |
| `refill_zones_after_apply` | true | 成功後にゾーン再塗りつぶし |
| `create_single_undo_group` | true | 対応可能な編集を1トランザクション化 |

アンテナ修正の適用直前にアクティブ基板を再読込し、全解析と計画を再実行します。選択案のID、対象ネット／レイヤー、形状、寸法、安全パラメータが全て再現されない場合、基板を変更せず全適用を中止します。

JLCPCBプロファイル適用時は、複数選択したルーティングカタログを保持しつつ、自動修正寸法が有効プロファイルを満たすように補正します。

## `noise`

| 項目 | 既定 | 内容 |
|---|---:|---|
| `endpoint_snap_mm` | 0.05 | 端点グラフ量子化 |
| `dangling_stub_min_length_mm` | 0.80 | スタブ最小長 |
| `parallel_angle_tolerance_deg` | 5.0 | 平行角度差 |
| `parallel_spacing_warning_mm` | 0.50 | 平行間隔閾値 |
| `parallel_overlap_warning_mm` | 5.0 | 平行重なり長 |
| `acute_corner_warning_deg` | 75.0 | 鋭角閾値。90°は対象外 |
| `corner_pad_exclusion` | true | パッド／ビア周辺除外 |
| `corner_pad_clearance_mm` | 0.10 | パッド除外余白 |
| `corner_min_segment_length_mm` | 0.50 | 微小セグメント除外 |
| `corner_skip_complex_junctions` | true | 3本以上の分岐を除外 |
| `trace_length_warning_mm` | 50.0 | 幾何長閾値 |
| `signal_rise_time_ns` | 1.0 | ドライバー立上り時間 |
| `critical_length_fraction` | 1/6 | 電気的臨界長係数 |
| `long_net_trigger_mode` | `both_or_severe` | 長配線の発火論理 |
| `long_net_severe_multiplier` | 1.50 | 明確超過倍率 |
| `long_net_diameter_scan_limit` | 32 | 経路グラフ探索予算 |
| `skip_return_via_check_on_two_layer` | true | 2層の一般リターンビア警告を停止 |
| `reference_plane_sample_step_mm` | 0.50 | 反対面基準面サンプル刻み |
| `reference_gap_min_length_mm` | 3.00 | 持続的欠落の最小絶対長 |
| `reference_gap_min_track_length_mm` | 5.00 | 基準面評価する最小配線長 |
| `reference_gap_min_fraction` | 0.30 | 欠落区間の最小経路比 |
| `reference_gap_endpoint_exclusion_mm` | 0.75 | 通常の端点ブレークアウト除外 |
| `ground_bottleneck_width_mm` | 1.00 | GND狭窄幅閾値 |
| `ground_detour_warning_ratio` | 4.00 | GND帰路／信号経路比 |
| `ground_detour_min_length_mm` | 5.00 | 迂回評価の最小信号長 |
| `ground_detour_min_active_length_mm` | 1.00 | 評価対象GND経路の最小長 |
| `ground_detour_min_excess_mm` | 5.00 | 必須の絶対迂回超過長 |
| `board_edge_signal_clearance_mm` | 1.0 | 信号と基板端の閾値 |
| `differential_pair_mismatch_warning_mm` | 1.0 | 差動長差閾値 |

`long_net_trigger_mode`は`either`、`both`、`both_or_severe`から選びます。`long_net_ignore_regex`と`reference_gap_ignore_regex`はGNDと主要電源名を既定除外します。2層のリターン判定は単発サンプルではなく持続的な根拠を要求します。

カテゴリ重みの既定はアンテナ0.30、平行0.20、折れ角0.10、長さ0.15、リターン0.15、その他0.10です。

## `silkscreen`

既定は0.8 × 0.8 mm、線幅0.10 mm、ビア／パッド離隔0.20 mm、基板端0.30 mm、文字間0.15 mmです。角度候補は0°、90°、+45°、-45°です。可能な限り所有フットプリントから2.50 mm以内に置き、安全な外部候補がない場合はフットプリント上の要手動確認案を生成できます。MountingHole／LOGO値を既定で隠し、参照番号をF.Fab／B.Fabへ移して非表示にし、ロック済み部品を除外します。

## `edge`

| 項目 | 既定 |
|---|---:|
| `mode` | `diagonal` |
| `grid_mm` | 0.50 |
| `component_margin_mm` | 1.50 |
| `copper_margin_mm` | 0.50 |
| `minimum_ground_band_mm` | 1.00 |
| `fillet_radius_mm` | 1.00 |
| `outline_strategy` | `convex_preserve_existing_concavities` |
| `target_vertex_count` | 8 |
| `preserve_existing_concavities` | true |
| `allow_concave_outline` | false |
| `allow_diagonal_edges` | true |
| `maximum_area_reduction_percent` | 35.0 |
| `reject_area_increase` | true |
| `maximum_area_increase_percent` | 0.0 |
| `preserve_existing_outline_when_smaller` | true |
| `allow_destructive_edge_replacement` | false |
| `perimeter_via_rebuild_default` | false |

目標頂点数は4～64です。安全条件により実頂点数が異なる場合があります。既定戦略は新しい凹部を作らず、元外形の安全な凹頂点だけを保持します。`mode=diagonal`では`allow_diagonal_edges=true`へ自動正規化します。

`require_explicit_backup`は破壊的な`.kicad_pcb`のEdge.Cuts置換だけに関係し、インストーラーとは無関係です。インストーラーは旧Pluginのコピーを作りません。

## `stitching`

既定は外周間隔5.00 mm、端オフセット1.00 mm、頂点オフセット1.20 mm、候補間最小2.50 mm、ビア0.60／0.30 mm、離隔0.25 mm、表裏GND必須、最大1000候補です。既存外周リング再構築は既定オフで、部分採用時は旧リングを削除しません。

## `placement`

既定はブロック間8.00 mm、部品間1.50 mm、ブロック幅45.00 mm、回路図シート単位、ロック部品保持、コネクタ外周寄せ、コンデンサ参照番号／値推定、`dry_run_only=true`です。

## `manufacturing`

既定は`jlcpcb_2l_economy`です。2層、1.60 mm、緑レジスト、白シルク、1 oz、有鉛HASL、ルーター、最小配線／間隔0.20 mm、自動修正ビア0.60／0.30 mmです。

配線プリセット:

`0.1, 0.2, 0.3, 0.4, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0 mm`

ビアプリセット:

- `jlcpcb_capability_limit`: 0.25／0.15 mm
- `kicad_default`: 0.60／0.30 mm

`selected_track_widths_mm`と`selected_via_preset_ids`は複数値を保持します。単数項目は自動修正へ使うプロファイル適合値です。`apply_profile_to_silkscreen`はfalseで、0.8 mm／0.10 mmシルクを保持します。JLCPCB可読性基準を採用する場合だけ明示的に変更します。

## `ui`

| 項目 | 既定 | 内容 |
|---|---:|---|
| `language` | `auto` | `ja`／`en`も可 |
| `open_browser` | true | 起動時にブラウザーを開く |
| `bind_address` | `127.0.0.1` | ループバック限定 |
| `inactivity_timeout_minutes` | 0 | 無操作終了無効 |
| `heartbeat_seconds` | 20 | KiCad接続確認 |
| `ipc_retry_count` | 2 | 再接続回数 |
| `report_directory` | 空 | 既定保存先を使用 |

ループバック以外のバインド先は拒否します。無操作終了を使う場合だけ正数を設定します。
