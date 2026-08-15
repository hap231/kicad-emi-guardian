"""Localized analysis text used by the dashboard and exported JSON.

The analysis core stores stable English engineering language for reports and
Doxygen/Sphinx documentation.  This module adds a separate presentation layer
so user interface language changes never alter rule identifiers or scoring.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

FindingText = tuple[str, str, str]


_FINDING_TEXT_JA: dict[str, FindingText] = {
    "antenna.island": (
        "GND銅箔の未接続成分",
        "塗りつぶしゾーン、配線、ビア、パッドを同一ネットで統合した接続グラフにおいて、このGND銅箔成分がフットプリントのGNDパッドへ到達していません。単に別の塗りつぶしポリゴンとして記録されているだけではなく、実際に浮遊している可能性があります。",
        "ネット割当とゾーン再塗りつぶしを確認してください。意図した銅箔なら低インダクタンスでGNDパッドへ接続し、不要なら銅箔キープアウトのルールエリアで除去してください。",
    ),
    "antenna.appendage": (
        "保護対象外に残ったGND銅箔の突起",
        "GNDパッド、GNDビア、明示的なGND配線、主GND領域、および既存の外周GNDを、設定した必要接続幅tで連結した保護バックボーンを先に構成しました。この指摘は、そのバックボーンの外側に残り、除去後も必要なGND端子の接続が維持されることを幾何学的に確認できた銅箔部分です。パッド本体や必要な接続路はアンテナ候補に含めません。",
        "安全性が証明された指摘形状だけを、形状を拡張しない銅箔キープアウトのルールエリアで除去してください。GNDパッド接続、必要幅tの接続路、既存の外周GNDに重なる修正は拒否されます。配線またはビアは、実際の銅箔ギャップを低インダクタンスで接続でき、かつEdge.Cuts内に収まる場合だけ使用してください。",
    ),
    "antenna.isolated": (
        "細長い孤立GND銅箔",
        "設定した細首幅より狭い孤立銅箔を検出しました。浮遊銅箔または共振性構造になる可能性があります。",
        "安全にGNDへ接続できる場合はステッチングビアまたは短いブリッジを追加し、接続できない場合はルールエリアで除去してください。",
    ),
    "noise.stub": (
        "未終端配線スタブの可能性",
        "配線グラフ上で次数1の端点が検出され、その位置に同一ネットのパッドまたはビアがありません。不要なスタブは共振や容量性負荷の原因になります。",
        "スタブを削除するか、意図した終端を追加するか、必要なテストポイントであることを明記してください。",
    ),
    "noise.parallel": (
        "異なるネット間の近接平行配線",
        "異なるネットの2本の配線が、狭い間隔で長く平行しています。特に立上りの速い信号では、容量性・誘導性結合が増加します。",
        "配線間隔を広げる、平行区間を短くする、隣接層では直交方向に配線する、または配線層間に連続した基準面を設けてください。",
    ),
    "noise.corner": (
        "鋭角な配線コーナー",
        "パッド・ビア接続部を除外した配線頂点の内角が設定値未満です。鋭角は通常リターンパス不連続より影響が小さいものの、局所的なインピーダンス変化や製造上のアシッドトラップを生じる可能性があります。",
        "クリアランスが許す範囲で、2つの45度曲げまたは滑らかな円弧へ変更してください。",
    ),
    "noise.long_net": (
        "電気的に長い配線ネット",
        "分岐を単純加算せずに推定した最大端点間配線長が、幾何学的な設定値と立上り時間から求めた分布定数線路の基準を超えています。",
        "送端終端、受端負荷、基準面の連続性、タイミングを確認してください。可能なら短縮し、実際のドライバ立上り時間を入力して再評価してください。",
    ),
    "noise.return_via": (
        "層変更ビアの近傍にGNDリターンビアがない",
        "信号ビアの設定半径内にGNDステッチングビアが検出されませんでした。リターン電流が迂回し、電流ループ面積が大きくなる可能性があります。",
        "信号の層変更点に隣接して、1本以上のGNDステッチングビアを追加してください。",
    ),
    "noise.reference_gap": (
        "信号配線がGND基準面の欠損部を横断",
        "2層基板の信号配線の下側にあたる反対面で、一定長以上にわたりGNDベタまたは明示的なGND導体を確認できませんでした。スロット、キープアウト、ベタ端を回り込むリターン電流によってループインダクタンスが増える可能性があります。",
        "配線直下のGNDを連続させるか、信号配線を欠損部から離してください。基準面を切り替える必要がある場合は、切替位置の近傍に低インダクタンスのGND接続を設けてください。",
    ),
    "noise.ground_detour": (
        "部品のGND帰路が異常に迂回",
        "この部品のGNDパッドはGNDベタへ直接接触しておらず、検出できた最短GND配線経路が同じ部品の最短非GND配線経路より大幅に長くなっています。局所的な電流ループ拡大やグランドバウンスの原因になり得ます。",
        "GNDパッドを短く太い銅箔で局所GND面へ接続し、必要に応じて近接ビアを追加してください。スロットを回り込む帰路になっていないか、実際の電流ループも確認してください。",
    ),
    "noise.ground_bottleneck": (
        "GNDベタ狭窄による電位勾配リスク",
        "複数のGNDパッドを含む領域同士が、細い銅箔の首部分だけで接続されています。共有リターン電流がこの狭窄部へ集中すると、局所インピーダンスが増え、領域間に電位差が生じる可能性があります。",
        "狭窄部を広げるか、原因となるスロットやキープアウトを見直してください。新たなアンテナ形状を作らない範囲で、並列の低インダクタンス帰路や適切なGNDステッチングビアを追加してください。",
    ),
    "noise.edge": (
        "信号配線が基板端に近い",
        "GND以外の配線がEdge.Cutsに近接しています。基板端では端部電界、筐体結合、加工公差によるリスクが増える可能性があります。",
        "信号配線を内側へ移動し、外周は連続したGNDベタまたはガード構造に確保してください。",
    ),
    "noise.diff_mismatch": (
        "差動ペアの配線長差",
        "差動ペア命名規則に一致した2つのネットで、総配線長に差があります。",
        "ペア間隔と連続した基準面を維持したまま、差動ペアの配線長を整合してください。",
    ),
}


_METRIC_LABELS_JA: dict[str, str] = {
    "net": "ネット",
    "first_net": "ネット1",
    "second_net": "ネット2",
    "layer": "レイヤー",
    "layer_id": "レイヤーID",
    "segment_length_mm": "セグメント長 (mm)",
    "overlap_mm": "平行区間長 (mm)",
    "spacing_mm": "配線間隔 (mm)",
    "angle_difference_deg": "方向角差 (度)",
    "normalized_crosstalk_proxy": "正規化クロストーク指標",
    "included_angle_deg": "内角 (度)",
    "corner_threshold_deg": "判定閾値 (度)",
    "pad_exclusion_applied": "パッド除外適用",
    "total_length_mm": "総銅箔長 (mm)",
    "estimated_path_length_mm": "推定最大端点間長 (mm)",
    "critical_length_mm": "電気的臨界長 (mm)",
    "configured_length_warning_mm": "設定配線長警告値 (mm)",
    "assumed_rise_time_ns": "想定立上り時間 (ns)",
    "branch_ratio": "分岐比率",
    "component_index": "接続成分番号",
    "diameter_method": "最長経路探索方式",
    "diameter_source_count": "探索開始点数",
    "nearest_ground_via_mm": "最寄りGNDビア距離 (mm)",
    "required_radius_mm": "要求半径 (mm)",
    "edge_distance_mm": "基板端距離 (mm)",
    "required_clearance_mm": "要求クリアランス (mm)",
    "pair_base": "差動ペア基底名",
    "positive_net": "P側ネット",
    "negative_net": "N側ネット",
    "positive_length_mm": "P側配線長 (mm)",
    "negative_length_mm": "N側配線長 (mm)",
    "mismatch_mm": "配線長差 (mm)",
    "kind": "種別",
    "zone_id": "ゾーンID",
    "area_mm2": "面積 (mm²)",
    "perimeter_mm": "周長 (mm)",
    "anchor_count": "GND接続点数",
    "length_mm": "長さ (mm)",
    "estimated_width_mm": "推定幅 (mm)",
    "slenderness": "細長さ",
    "attachment_cells": "接続セル数",
    "isolated": "孤立",
    "nearest_ground_anchor_mm": "最寄りGND接続点距離 (mm)",
    "nearest_aggressor_mm": "最寄りアグレッサ距離 (mm)",
    "quarter_wave_resonance_mhz": "1/4波長共振周波数 (MHz)",
    "severity_components": "重大度構成要素",
    "tip": "先端座標",
    "gate": "付け根座標",
    "centroid": "重心座標",
    "bounds": "範囲",
    "polygon": "ポリゴン",
    "component_id": "接続成分ID",
    "component_area_mm2": "接続成分面積 (mm²)",
    "connected_via_count": "接続ビア数",
    "connected_track_count": "接続配線数",
    "signal_layer": "信号レイヤー",
    "reference_layer": "基準GNDレイヤー",
    "reference_copper_present": "基準GND銅箔の検出",
    "unsupported_length_mm": "GND基準面欠損長 (mm)",
    "sample_step_mm": "サンプリング間隔 (mm)",
    "footprint_id": "フットプリントID",
    "ground_net": "GNDネット",
    "ground_route_length_mm": "GND帰路長 (mm)",
    "shortest_active_route_mm": "最短非GND配線長 (mm)",
    "ground_to_active_ratio": "GND帰路／非GND配線比",
    "estimated_neck_width_mm": "推定狭窄幅 (mm)",
    "anchors_on_appendage_side": "狭窄先側GNDパッド数",
    "anchors_on_main_side": "主領域側GNDパッド数",
    "anchor_span_mm": "GNDパッド間距離 (mm)",
    "feature_polygon": "検出形状ポリゴン",
    "raster_step_mm": "ラスタ刻み (mm)",
    "safe_keepout_polygon": "安全確認済み除去ポリゴン",
    "safe_keepout": "除去形状の安全確認",
    "critical_connectivity_preserved": "必須GND接続の維持",
    "pad_overlap": "GNDパッドとの重なり",
    "perimeter_overlap": "保護外周GNDとの重なり",
    "required_ground_connection_width_mm": "必要GND接続幅 t (mm)",
    "effective_opening_width_mm": "実効形態学的開口幅 (mm)",
    "protected_cell_count": "保護GNDセル数",
    "removable_cell_count": "除去候補セル数",
    "required_terminal_count": "必須GND端子数",
    "connected_terminal_count": "接続維持済みGND端子数",
    "unsupported_fraction": "基準面欠損率",
    "endpoint_exclusion_mm": "端点除外長 (mm)",
    "excess_ground_length_mm": "GND帰路の超過長 (mm)",
    "minimum_ratio": "判定最小迂回比",
}


def localize_finding(
    rule_id: str,
    title: str,
    description: str,
    recommendation: str,
    metrics: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return complete English and Japanese presentation payloads."""

    ja_title, ja_description, ja_recommendation = _FINDING_TEXT_JA.get(
        rule_id,
        (title, description, recommendation),
    )
    metric_keys = tuple(str(key) for key in metrics)
    return {
        "en": {
            "title": title,
            "description": description,
            "recommendation": recommendation,
            "metric_labels": {key: _humanize_metric(key) for key in metric_keys},
        },
        "ja": {
            "title": ja_title,
            "description": ja_description,
            "recommendation": ja_recommendation,
            "metric_labels": {key: _METRIC_LABELS_JA.get(key, _humanize_metric(key)) for key in metric_keys},
        },
    }


_MANUFACTURING_TEXT_JA: dict[str, FindingText] = {
    "ORDER_LAYER_COUNT": (
        "選択した製造プロファイルは2層基板専用です",
        "基板または発注設定の銅箔層数が、JLCPCB 2層プロファイルと一致していません。",
        "KiCadのBoard Setupと発注設定を2層へそろえるか、別の製造プロファイルを使用してください。",
    ),
    "ORDER_THICKNESS_UNSUPPORTED": (
        "選択した基板厚が2層プロファイルの対応範囲外です",
        "選択された基板厚は、現在のJLCPCB 2層設定一覧に含まれていません。",
        "対応する基板厚を選択し、発注時の見積画面でも再確認してください。",
    ),
    "ORDER_MASK_COLOR_UNSUPPORTED": (
        "選択したレジスト色が対応一覧にありません",
        "選択されたソルダーレジスト色は、現在のJLCPCB 2層設定一覧に含まれていません。",
        "対応する色を選択し、最新の見積画面で提供状況を確認してください。",
    ),
    "ORDER_SILK_COLOR_MISMATCH": (
        "レジスト色とシルク色の組み合わせが標準設定と異なります",
        "白レジストでは黒シルク、それ以外では白シルクという標準的な組み合わせと一致していません。",
        "意図した組み合わせか確認し、JLCPCBの見積画面で選択可能か確認してください。",
    ),
    "ORDER_04MM_REQUIRES_ENIG": (
        "0.4 mm基板ではENIGが必要です",
        "選択した表面処理は、現在の0.4 mm基板の発注条件と互換性がありません。",
        "ENIGを選択するか、より厚い基板へ変更してください。",
    ),
    "ORDER_04MM_NO_PANEL": (
        "0.4 mm基板ではパネル分割条件を使用できません",
        "現在の発注条件では、0.4 mm基板をパネルとして製造できません。",
        "単体基板のルーター加工を選択するか、より厚い基板へ変更してください。",
    ),
    "ORDER_06MM_HASL_LEADED": (
        "0.6 mm・2層基板では有鉛HASLを選択できません",
        "選択した板厚と表面処理の組み合わせは、現在の見積条件に対応していません。",
        "鉛フリーHASLまたはENIGを選択するか、別の板厚へ変更してください。",
    ),
    "ORDER_SMALL_VIA_COST_RISK": (
        "小径ビアの追加料金が発生する可能性があります",
        "選択したビアプリセットは製造可能範囲ですが、小径ビアの有料オプションに該当する可能性があります。",
        "高密度配線が不要なら、KiCad標準／JLCPCB低コストのビアプリセットを使用してください。",
    ),
    "BOARD_OUTLINE_UNAVAILABLE": (
        "基板外形から寸法を取得できません",
        "閉じたEdge.Cuts外形を基板スナップショットから復元できませんでした。",
        "Edge.Cutsの隙間、重複、自己交差を修正してから再検査してください。",
    ),
    "BOARD_TOO_SMALL": (
        "基板が公開最小寸法を下回っています",
        "検出した基板外形の幅または高さが、公開されている3 × 3 mmの最小値を下回っています。",
        "基板を大きくするか、適切にパネル化してください。",
    ),
    "BOARD_TOO_LARGE_FOR_THICKNESS": (
        "選択した板厚の製造可能寸法を超えています",
        "検出した基板寸法が、選択した板厚に適用される公開サイズ範囲を超えています。",
        "外形を小さくする、対応する板厚へ変更する、またはJLCPCBへ特注可否を確認してください。",
    ),
    "BOARD_SMALL_SINGLE_COST_RISK": (
        "小型単体基板の取扱料金が発生する可能性があります",
        "片側が30 mm以下の単体基板では、発注条件によって追加の取扱料金が発生する可能性があります。",
        "パネル化または配送形態を、最新の見積画面で確認してください。",
    ),
    "STACKUP_LAYER_MISMATCH": (
        "KiCadの銅箔層数と発注設定が一致しません",
        "KiCadから読み取った銅箔層数が、選択したJLCPCB発注設定と異なります。",
        "Gerber出力前にBoard SetupとPluginの発注設定を一致させてください。",
    ),
    "STACKUP_THICKNESS_MISMATCH": (
        "KiCadの基板厚と発注設定が一致しません",
        "KiCadのスタックアップから読み取った基板厚が、Pluginで選択した発注厚と異なります。",
        "Board SetupまたはPluginの発注設定を修正し、両方を一致させてください。",
    ),
    "STACKUP_MASK_COLOR_MISMATCH": (
        "KiCadのレジスト色と発注設定が一致しません",
        "KiCadスタックアップのレジスト色が、Pluginで選択したJLCPCB発注色と異なります。",
        "KiCadの表示色または発注設定を手動でそろえてください。",
    ),
    "TRACK_WIDTH": (
        "配線幅が選択したJLCPCBプロファイル未満です",
        "少なくとも1本の配線が、現在の製造プロファイルで許容する最小配線幅を下回っています。",
        "配線を制限値以上へ太くするか、局所ネックダウンとして個別に設計審査してください。",
    ),
    "TRACK_CLEARANCE": (
        "異なるネット間の配線クリアランスが不足しています",
        "同一銅箔層上の異なるネット間で、配線端同士の推定間隔が選択した制限値を下回っています。",
        "配線間隔を制限値以上へ広げ、KiCad DRCでも確認してください。",
    ),
    "VIA_DIAMETER": (
        "ビア外径が選択したプロファイル未満です",
        "少なくとも1個のビアで、銅箔外径が現在の最小値を下回っています。",
        "ビア外径を制限値以上へ増やしてください。",
    ),
    "VIA_DRILL": (
        "ビア穴径が選択したプロファイル未満です",
        "少なくとも1個のビアで、ドリル径が現在の最小値を下回っています。",
        "ビア穴径を制限値以上へ増やしてください。",
    ),
    "VIA_ANNULAR_RING": (
        "ビアのアニュラリング幅が不足しています",
        "ビア外径と穴径から算出した片側リング幅が、選択した最小値を下回っています。",
        "ビア外径を増やすか穴径を小さくし、必要なリング幅を確保してください。",
    ),
    "VIA_SMALL_FEATURE_SURCHARGE": (
        "小径ビアの追加料金条件に該当する可能性があります",
        "このビアは製造能力内でも、小径穴または小外径ビアの有料オプションに該当する可能性があります。",
        "密度上必要でなければ0.60/0.30 mmなどの低コスト寸法へ変更してください。",
    ),
    "VIA_HOLE_TO_HOLE": (
        "ビア穴同士の間隔が不足しています",
        "2つのビア穴端の推定間隔が、選択した最小穴間隔を下回っています。",
        "ビアを離すか、穴径と配置を見直してください。",
    ),
    "VIA_TO_TRACK": (
        "ビア穴と異ネット配線の間隔が不足しています",
        "ビア穴端と異なるネットの配線銅箔端の推定距離が、選択した最小値を下回っています。",
        "ビアまたは配線を移動して、必要なクリアランスを確保してください。",
    ),
    "TRACK_TO_EDGE": (
        "配線が基板端に近すぎます",
        "配線銅箔端とEdge.Cutsの推定距離が、選択した加工方法の最小値を下回っています。",
        "配線を基板内側へ移動するか、外形を広げてください。",
    ),
    "VIA_TO_EDGE": (
        "ビアが基板端に近すぎます",
        "ビア銅箔端とEdge.Cutsの推定距離が、選択した加工方法の最小値を下回っています。",
        "ビアを基板内側へ移動するか、外形を広げてください。",
    ),
    "PAD_TO_EDGE": (
        "パッドが基板端に近すぎます",
        "パッド外形とEdge.Cutsの推定距離が、選択した加工方法の最小値を下回っています。",
        "フットプリントを内側へ移動するか、外形を広げてください。",
    ),
    "SILK_LINE_WIDTH": (
        "シルク線幅が推奨値未満です",
        "シルク文字または図形の線幅が、JLCPCB向けに設定した最小線幅を下回っています。",
        "線幅を制限値以上へ太くし、Gerber Viewerで可読性を確認してください。",
    ),
    "SILK_TEXT_HEIGHT": (
        "シルク文字高さが推奨値未満です",
        "シルク文字の高さが、JLCPCB向けに設定した最小文字高さを下回っています。",
        "文字を大きくするか、製造後に読めなくても問題ない補助表示かを確認してください。",
    ),
}


def localize_manufacturing_issue(
    code: str,
    title: str,
    description: str,
    recommendation: str,
) -> dict[str, dict[str, str]]:
    """Return English and Japanese text for one manufacturing issue."""

    ja_title, ja_description, ja_recommendation = _MANUFACTURING_TEXT_JA.get(
        code,
        (title, description, recommendation),
    )
    return {
        "en": {
            "title": title,
            "description": description,
            "recommendation": recommendation,
        },
        "ja": {
            "title": ja_title,
            "description": ja_description,
            "recommendation": ja_recommendation,
        },
    }


def _humanize_metric(value: str) -> str:
    """Return a compact English label for a machine-readable metric key."""

    return value.replace("_", " ").strip().title()
