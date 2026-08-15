"use strict";

const query = new URLSearchParams(window.location.search);
const sessionToken = query.get("token") || "";

const state = {
  status: null,
  config: null,
  analysis: null,
  preview: null,
  fixPlan: null,
  silkPlan: null,
  edgeProposal: null,
  stitchingPlan: null,
  placementPlan: null,
  manufacturingCatalog: null,
  manufacturingReport: null,
  language: "ja",
  previewViews: {},
  layerVisibility: {},
  activeFindingId: "",
  hoverFindingId: "",
  selectedFixIds: new Set(),
  selectedSilkIds: new Set(),
  selectedStitchingIds: new Set(),
  selectedPlacementIds: new Set(),
  selectionKeys: { fixes: "", silk: "", stitching: "", placement: "" },
  heartbeatTimer: null,
};

function syncPlanSelection(kind, items, idKey, defaultKey = "default_selected") {
  const key = (items || []).map((item) => String(item[idKey] || "")).sort().join("|");
  if (state.selectionKeys[kind] === key) return;
  state.selectionKeys[kind] = key;
  const setName = {
    fixes: "selectedFixIds",
    silk: "selectedSilkIds",
    stitching: "selectedStitchingIds",
    placement: "selectedPlacementIds",
  }[kind];
  state[setName] = new Set(
    (items || [])
      .filter((item) => item[defaultKey] !== false && !item.locked)
      .map((item) => String(item[idKey])),
  );
}

const translations = {
  ja: {
    activeBoard: "アクティブ基板", dashboard: "ダッシュボード", antennaFixes: "アンテナ修正", silkscreen: "シルク整備",
    boardOutline: "外形最適化", quantitative: "定量評価", settings: "設定",
    dashboardSubtitle: "基板を書き換える前に、形状由来のEMIリスクを確認します。", exportReport: "レポート出力", runScan: "解析を実行",
    boardScore: "基板スコア", criticalFindings: "重大／高リスク", requiresReview: "要レビュー", allFindings: "全指摘", mutationMode: "書き込みモード",
    boardPreview: "基板プレビュー", previewNote: "簡略化した基板形状上に指摘位置を表示します。", risk: "リスク", copper: "銅箔・配線",
    scanToPreview: "解析を実行するとプレビューを表示します", readOnlyScan: "解析だけでは基板を変更しません。", categoryScores: "カテゴリ別スコア", higherBetter: "高いほど良好です。",
    findings: "検出結果", findingsSubtitle: "根拠、確信度、推奨対応を確認できます。", allSeverities: "全重大度", allCategories: "全カテゴリ", noAnalysis: "解析結果がありません", runFirstScan: "最初の解析を実行してください。",
    fixHeroTitle: "アンテナ対策を安全性と効果で順位付け", fixHeroText: "GNDブリッジ、ステッチングビア、配線＋ビア、銅箔キープアウトを比較します。確信度閾値以上の候補だけが適用対象です。",
    planFixes: "修正案を作成", selectedActions: "選択された処置", estimatedReduction: "期待リスク低減", manualReview: "手動レビュー", proposedActions: "修正候補",
    fixTableSubtitle: "適用を明示確認するまで基板には何も書き込みません。", finding: "指摘", method: "方法", layer: "レイヤー", confidence: "確信度", utility: "効用", description: "説明", noFixPlan: "修正案がありません。",
    confirmReviewed: "提案内容を確認し、適用後にDRCを実行します。", applyFixes: "選択案を適用", safetyModel: "安全設計", safetyPreview: "修正案作成は形状評価のみで、基板を変更しません。",
    safetyGate: "Dry-runと最低確信度により、不確実な書き込みを遮断します。", safetyVerify: "書き込みは1つのUndo単位。ゾーン再塗りつぶし後にDRCを実施します。",
    silkHeroTitle: "途切れや衝突を避けて部品値を表示", silkHeroText: "デフォルトは0.8 × 0.8 mm、線幅0.10 mmです。パッド、ビア、基板端、既存文字を避けた位置を探索します。",
    planSilk: "シルク配置案を作成", placeableValues: "配置可能", skippedValues: "配置見送り", defaultSize: "既定サイズ", placementPlan: "配置案", silkTableSubtitle: "参照番号は、対応する値変更を適用する時だけ非表示になります。",
    reference: "参照番号", value: "値", placementScore: "配置コスト", noSilkPlan: "シルク配置案がありません。", confirmSilk: "値の表示・配置変更を確認しました。", applySilk: "シルク案を適用",
    edgeHeroTitle: "GND外周を維持しながら基板面積を削減", edgeHeroText: "外形頂点を指定グリッドへスナップし、全角にフィレットを付けます。連続GND帯を証明できない場合、自動置換は遮断されます。",
    planEdge: "外形案を作成", originalArea: "元の面積", proposedArea: "提案面積", areaReduction: "面積削減", gndPerimeter: "外周GND", outlinePreview: "外形プレビュー", outlinePreviewSubtitle: "スナップ済みポリゴンから丸角プリミティブを生成します。",
    noEdgeProposal: "外形案がありません", proposalChecks: "提案チェック", mode: "モード", grid: "グリッド", fillet: "フィレット", destructiveOperation: "破壊的操作",
    edgeApplyWarning: "現在のEdge.Cutsを削除して丸角案を作成します。設定時はバックアップも作成します。アクティブ基板名を正確に入力してください。", confirmEdge: "寸法、キープアウト、コネクタ、製造制約を確認しました。", replaceEdge: "Edge.Cutsを置換",
    quantHeroTitle: "形状を追跡可能な電気的推定値へ変換", quantHeroText: "伝搬、臨界長、1/4波長、インピーダンス、表皮深さ、結合指標を概算します。適合判定用のフルウェーブ解析ではありません。",
    exportSolver: "ソルバ用データ出力", quantDetails: "定量評価の詳細", quantDetailsSubtitle: "基板から取得したスタックアップ、または設定値を使用します。", fullWaveBoundary: "フルウェーブ解析との境界",
    fullWaveText: "有意なEM解析には、ポート、励振スペクトル、終端、筐体・ケーブル形状、材料分散、境界条件、収束したメッシュが必要です。出力バンドルは検証済み後工程へ形状と仮定を渡します。",
    general: "全般", antenna: "アンテナ", noiseChecks: "ノイズチェック", advancedJson: "詳細JSON", generalSettings: "全般と安全設定", generalSettingsText: "Dry-runは既定で有効です。修正案を確認した後だけ解除してください。",
    dryRun: "Dry-runモード", dryRunHelp: "全ての基板書き込みを遮断", minimumConfidence: "最低適用確信度", uiLanguage: "UI言語", reportDirectory: "レポート保存先",
    antennaSettings: "GNDアンテナ検出", groundNetRegex: "GNDネット正規表現", rasterStep: "ラスタ刻み (mm)", neckWidth: "細首幅 (mm)", groundConnectionWidth: "必須GND接続幅 t (mm)", padProtectionMargin: "パッド保護マージン (mm)", perimeterGroundProtection: "保護する外周GND帯幅 (mm)", minAppendageLength: "最小突起長 (mm)", maxAnchorDistance: "最大GND接続距離 (mm)", bridgeLength: "最大ブリッジ長 (mm)", viaDiameter: "ビア径 (mm)", viaDrill: "ビア穴径 (mm)",
    noiseSettings: "定性ノイズチェック", riseTime: "信号立上り時間 (ns)", parallelSpacing: "平行配線間隔警告 (mm)", parallelOverlap: "平行区間長警告 (mm)", cornerAngle: "折れ角警告 (deg)", traceLength: "配線長警告 (mm)", returnViaRadius: "リターンビア探索半径 (mm)",
    silkSettings: "シルク最適化", textWidth: "文字幅 (mm)", textHeight: "文字高さ (mm)", textThickness: "線幅 (mm)", viaClearance: "ビア離隔 (mm)", edgeClearance: "基板端離隔 (mm)", hideReference: "参照番号を非表示",
    edgeSettings: "外形最適化", outlineMode: "外形モード", vertexGrid: "頂点グリッド (mm)", filletRadius: "フィレット半径 (mm)", componentMargin: "部品余白 (mm)", groundBand: "最小GND帯 (mm)", maxReduction: "最大面積削減 (%)", allowDiagonal: "斜め辺を許可", allowEdgeReplacement: "破壊的置換を許可", edgeReplacementHelp: "GND証明と入力確認は引き続き必須",
    advancedJsonText: "全パラメータを編集できます。未知のキーは無視され、不正値は拒否されます。", reloadValues: "値を再読込", saveSettings: "設定を保存",
    scanComplete: "解析が完了しました。", reportExported: "レポートを出力しました。", solverExported: "ソルバ用バンドルを出力しました。", settingsSaved: "設定を保存しました。",
    planningComplete: "提案を作成しました。", changesApplied: "基板変更を適用しました。", verified: "確認済み", unverified: "未確認", enabled: "有効", blocked: "遮断", notScanned: "未解析",
    manufacturing: "JLCPCB製造", mfgHeroTitle: "低コスト制約を選択して基板を検証", mfgHeroText: "低コストは既知の微細ビア追加料金を避ける保守値、製造能力限界は高密度な局所配線向けの公開最小値です。",
    mfgExport: "JLCPCBバンドル出力", mfgCheck: "DFMチェック実行", mfgScore: "DFMスコア", mfgErrors: "エラー", mfgWarnings: "警告", mfgOrder: "選択中の発注条件",
    mfgProfileSettings: "プロファイルと発注条件", mfgProfileHelp: "適用すると自動修正用の配線・ビア寸法も更新します。開いているKiCadのスタックアップは勝手に変更しません。", mfgProfile: "制約プロファイル", mfgThickness: "基板厚 (mm)", mfgMaskColor: "レジスト色", mfgCopper: "外層銅厚 (oz)", mfgFinish: "表面処理", mfgSeparation: "基板分割方法", mfgColorNote: "白レジスト以外は白シルク、白レジストは黒シルクを自動選択します。",
    mfgRoutingPresets: "配線プリセット", mfgRoutingHelp: "複数選択できます。最小の選択値を自動対策の既定値として使用します。", mfgTrackWidth: "配線幅 (mm)", mfgViaPreset: "ビアプリセット", mfgApplySilk: "JLCPCBのシルク可読性制約を適用", mfgApplySilkHelp: "明示選択した場合だけ0.8 mm既定文字を変更します。", mfgApplyProfile: "プロファイルとプリセットを適用",
    mfgActiveConstraints: "有効な製造制約", mfgVerifiedDate: "参照値は版管理され、確認日を表示します。", mfgIpcNotice: "KiCad 10はIPCで検証し、板厚・色・カスタムルールは明示確認用に出力します。開いている基板ファイルをテキスト置換しません。",
    mfgIssues: "JLCPCB DFM指摘", mfgIssuesHelp: "エラーは有効な制約違反、警告はコスト・可読性・発注条件の確認事項です。", mfgSeverity: "重大度", mfgCode: "コード", mfgCategory: "分類", mfgMeasuredLimit: "測定値 / 制限", mfgRecommendation: "推奨対応", mfgNoReport: "JLCPCB DFMチェックが未実行です。", mfgDisclaimer: "この事前確認は見積または製造受入保証ではありません。発注前に最新のJLCPCB見積とDFM結果を確認してください。", mfgProfileApplied: "製造プロファイルを適用しました。", mfgCheckComplete: "JLCPCB DFMチェックが完了しました。", mfgBundleExported: "JLCPCB製造バンドルを出力しました。",
  },
  en: {
    activeBoard: "Active board", dashboard: "Dashboard", antennaFixes: "Antenna fixes", silkscreen: "Silkscreen", boardOutline: "Board outline", quantitative: "Quantitative", settings: "Settings",
    dashboardSubtitle: "Review geometry-derived EMI risks before changing the board.", exportReport: "Export report", runScan: "Run scan", boardScore: "Board score", criticalFindings: "Critical / high", requiresReview: "Requires review", allFindings: "All findings", mutationMode: "Mutation mode",
    boardPreview: "Board preview", previewNote: "Finding locations are shown over simplified geometry.", risk: "Risk", copper: "Copper", scanToPreview: "Run a scan to build the preview", readOnlyScan: "The scan is read-only.", categoryScores: "Category scores", higherBetter: "Higher is better.", findings: "Findings", findingsSubtitle: "Evidence, confidence, and recommended action.", allSeverities: "All severities", allCategories: "All categories", noAnalysis: "No analysis yet", runFirstScan: "Run the first scan to identify review targets.",
    fixHeroTitle: "Ranked, conservative antenna remediation", fixHeroText: "The planner compares a GND bridge, stitching via, combined bridge-and-via, and copper keepout. Only candidates above the confidence threshold can be applied.", planFixes: "Plan fixes", selectedActions: "Selected actions", estimatedReduction: "Expected risk reduction", manualReview: "Manual-review items", proposedActions: "Proposed actions", fixTableSubtitle: "No board item is written until Apply is confirmed.", finding: "Finding", method: "Method", layer: "Layer", confidence: "Confidence", utility: "Utility", description: "Description", noFixPlan: "No fix plan yet.", confirmReviewed: "I reviewed the proposed changes and will run DRC afterward.", applyFixes: "Apply selected fixes", safetyModel: "Safety model", safetyPreview: "Planning is geometry-only and never edits the board.", safetyGate: "Dry-run and minimum confidence block uncertain writes.", safetyVerify: "All writes use one Undo group; refill zones and run DRC.",
    silkHeroTitle: "Show component values without broken or colliding text", silkHeroText: "Values default to 0.8 × 0.8 mm with a 0.10 mm stroke. Candidate positions avoid pads, vias, board edges, and existing text.", planSilk: "Plan silkscreen", placeableValues: "Placeable values", skippedValues: "Skipped values", defaultSize: "Default size", placementPlan: "Placement plan", silkTableSubtitle: "References are hidden only when the corresponding value update is applied.", reference: "Reference", value: "Value", placementScore: "Placement cost", noSilkPlan: "No silkscreen plan yet.", confirmSilk: "I reviewed the value visibility and placement changes.", applySilk: "Apply silkscreen plan",
    edgeHeroTitle: "Reduce board area while preserving a verified GND perimeter", edgeHeroText: "The outline is snapped to the selected grid and every corner is filleted. Automatic replacement remains blocked unless the GND band can be proven.", planEdge: "Build proposal", originalArea: "Original area", proposedArea: "Proposed area", areaReduction: "Area reduction", gndPerimeter: "GND perimeter", outlinePreview: "Outline preview", outlinePreviewSubtitle: "Rounded primitives generated from the snapped polygon.", noEdgeProposal: "No outline proposal yet", proposalChecks: "Proposal checks", mode: "Mode", grid: "Grid", fillet: "Fillet", destructiveOperation: "Destructive operation", edgeApplyWarning: "Replacement removes current Edge.Cuts, writes the rounded proposal, and creates a backup when configured. Type the exact active board name.", confirmEdge: "I reviewed dimensions, keepouts, connectors, and manufacturing constraints.", replaceEdge: "Replace Edge.Cuts",
    quantHeroTitle: "Convert geometry into traceable electrical estimates", quantHeroText: "Closed-form propagation, critical-length, quarter-wave, impedance, skin-depth, and coupling proxies support prioritization. They are not a compliance-grade full-wave solution.", exportSolver: "Export solver bundle", quantDetails: "Quantitative details", quantDetailsSubtitle: "Values use the detected stackup or configured defaults.", fullWaveBoundary: "Full-wave boundary", fullWaveText: "A meaningful EM solve additionally needs ports, source spectra, terminations, enclosure and cable geometry, material dispersion, boundary conditions, and a converged mesh. The export bundle preserves geometry and assumptions for a validated downstream workflow.",
    general: "General", antenna: "Antenna", noiseChecks: "Noise checks", advancedJson: "Advanced JSON", generalSettings: "General and safety", generalSettingsText: "Dry-run is enabled by default. Disable it only after reviewing plans.", dryRun: "Dry-run mode", dryRunHelp: "Block all board writes", minimumConfidence: "Minimum apply confidence", uiLanguage: "UI language", reportDirectory: "Report directory", antennaSettings: "Ground antenna detector", groundNetRegex: "Ground-net regular expression", rasterStep: "Raster step (mm)", neckWidth: "Narrow-neck width (mm)", groundConnectionWidth: "Required GND connection width t (mm)", padProtectionMargin: "Pad protection margin (mm)", perimeterGroundProtection: "Protected perimeter GND band (mm)", minAppendageLength: "Minimum appendage length (mm)", maxAnchorDistance: "Maximum anchor distance (mm)", bridgeLength: "Maximum bridge length (mm)", viaDiameter: "Via diameter (mm)", viaDrill: "Via drill (mm)", noiseSettings: "Qualitative noise checks", riseTime: "Signal rise time (ns)", parallelSpacing: "Parallel spacing warning (mm)", parallelOverlap: "Parallel overlap warning (mm)", cornerAngle: "Corner-angle warning (deg)", traceLength: "Trace-length warning (mm)", returnViaRadius: "Return-via radius (mm)", silkSettings: "Silkscreen optimizer", textWidth: "Text width (mm)", textHeight: "Text height (mm)", textThickness: "Stroke thickness (mm)", viaClearance: "Via clearance (mm)", edgeClearance: "Edge clearance (mm)", hideReference: "Hide references", edgeSettings: "Board-outline optimizer", outlineMode: "Outline mode", vertexGrid: "Vertex grid (mm)", filletRadius: "Fillet radius (mm)", componentMargin: "Component margin (mm)", groundBand: "Minimum GND band (mm)", maxReduction: "Maximum area reduction (%)", allowDiagonal: "Allow diagonal edges", allowEdgeReplacement: "Allow destructive replacement", edgeReplacementHelp: "Still requires GND proof and typed confirmation", advancedJsonText: "Edit every parameter. Unknown keys are ignored; invalid values are rejected.", reloadValues: "Reload values", saveSettings: "Save settings",
    scanComplete: "Scan completed.", reportExported: "Report exported.", solverExported: "Solver bundle exported.", settingsSaved: "Settings saved.", planningComplete: "Proposal created.", changesApplied: "Board changes applied.", verified: "Verified", unverified: "Unverified", enabled: "Enabled", blocked: "Blocked", notScanned: "Not scanned",
    manufacturing: "JLCPCB manufacturing", mfgHeroTitle: "Choose cost-conscious constraints and verify the board", mfgHeroText: "Economy uses conservative dimensions intended to avoid known fine-via surcharges. Capability limit exposes published minimums for local dense routing.",
    mfgExport: "Export JLCPCB bundle", mfgCheck: "Run DFM check", mfgScore: "DFM score", mfgErrors: "Errors", mfgWarnings: "Warnings", mfgOrder: "Selected order",
    mfgProfileSettings: "Profile and order settings", mfgProfileHelp: "Applying a profile also updates automatic-fix track and via geometry. It does not silently edit the open KiCad stackup.", mfgProfile: "Constraint profile", mfgThickness: "Board thickness (mm)", mfgMaskColor: "Solder-mask color", mfgCopper: "Outer copper (oz)", mfgFinish: "Surface finish", mfgSeparation: "Board separation", mfgColorNote: "White silkscreen is selected automatically except on white solder mask.",
    mfgRoutingPresets: "Routing presets", mfgRoutingHelp: "The selected values are also used by automatic GND remediation.", mfgTrackWidth: "Track width (mm)", mfgViaPreset: "Via preset", mfgApplySilk: "Apply JLCPCB silkscreen readability limits", mfgApplySilkHelp: "Changes the 0.8 mm default text only when explicitly selected.", mfgApplyProfile: "Apply profile and presets",
    mfgActiveConstraints: "Active constraints", mfgVerifiedDate: "Source data is versioned and includes its verification date.", mfgIpcNotice: "KiCad 10 is validated through IPC; thickness, colors, and custom rules are exported for explicit review rather than text-editing an open board file.",
    mfgIssues: "JLCPCB DFM issues", mfgIssuesHelp: "Errors violate the active profile. Warnings identify cost, readability, or order-review risks.", mfgSeverity: "Severity", mfgCode: "Code", mfgCategory: "Category", mfgMeasuredLimit: "Measured / limit", mfgRecommendation: "Recommendation", mfgNoReport: "No JLCPCB DFM check yet.", mfgDisclaimer: "This pre-check is not a quotation or manufacturing acceptance guarantee. Confirm the live JLCPCB quote and DFM result before ordering.", mfgProfileApplied: "Manufacturing profile applied.", mfgCheckComplete: "JLCPCB DFM check completed.", mfgBundleExported: "JLCPCB manufacturing bundle exported.",
  },
};

Object.assign(translations.ja, {
  fitPreview: "全体表示", zoomIn: "拡大", zoomOut: "縮小", locateInKicad: "KiCadで場所を表示",
  locateComplete: "KiCad上で該当アイテムを選択しました。", locateUnavailable: "該当するKiCadアイテムを選択できませんでした。",
  fixPreviewTitle: "アンテナ修正プレビュー", fixPreviewHelp: "追加配線、ビア、ルールエリアを基板上に重ねて表示します。",
  silkPreviewTitle: "シルク配置プレビュー", silkPreviewHelp: "現在のシルクと提案する部品値をレイヤー別に確認できます。",
  idleTimeout: "無操作終了（分、0で無効）", heartbeatInterval: "KiCad接続確認間隔（秒）",
  cornerMinSegment: "折れ角判定の最小セグメント長 (mm)", longNetMode: "長配線の判定方式", longNetSevere: "単独超過の重大倍率", longNetScanBudget: "最長経路の探索上限",
  excludePadCorners: "同一ネットのパッド・ビア内部を折れ角判定から除外",
  outlineStrategy: "外形生成方式", targetVertices: "目標頂点数", preserveConcavities: "元の外形にある凹部だけを保持",
  layerAll: "全て", layerNone: "全て非表示", previewPads: "パッド", previewVias: "ビア", previewFootprints: "フットプリント",
  previewFindings: "指摘", previewFixes: "修正案", previewSilkPlan: "シルク案", noMatchingFindings: "条件に一致する指摘はありません。", atLeastOnePreset: "配線幅とビアは、それぞれ1つ以上選択してください。",
  descriptionHeading: "説明", recommendationHeading: "推奨対応", metricsHeading: "判定根拠", itemCount: "関連アイテム",
  connectionRestored: "KiCadとの接続を再確立しました。", connectionLost: "KiCadとの接続を確認できません。再接続を試みます。",
  multipleSelectionHelp: "複数選択できます。自動修正には有効な製造プロファイルを満たす既定寸法を安全に選びます。",
  vertexCount: "頂点数", strategy: "生成方式", preservedConcavity: "保持した凹部",
  locateInPreview: "プレビュー上で場所を表示", selectAllLayers: "レイヤーを全選択", clearLayers: "レイヤーを全解除",
  selectAll: "全採用", clearSelection: "全解除", adopt: "採用", angle: "角度", distance: "距離",
  smoothOutline: "現在の外形を滑らかにする", filletOutline: "現在の外形にフィレット", viaStitching: "GNDビアステッチング",
  viaStitchingHelp: "外層の両面に同じGNDネットがあり、クリアランスを満たす位置だけへ適度な密度で配置します。",
  rebuildPerimeterVias: "既存の外周ビアを安全条件付きで総修正", planStitching: "ステッチング案を作成", noStitchingPlan: "ステッチング案がありません。",
  confirmStitching: "追加ビアと削除対象を確認しました。", applyStitching: "選択したステッチングを適用", source: "生成根拠",
  initialPlacement: "初期配置", placementHeroTitle: "回路図ブロックごとに部品をまとめる", placementHeroText: "ロック部品を保持し、コネクタをブロック外周へ、デカップリングコンデンサを対応パッド近傍へ配置する初期案を作成します。",
  planPlacement: "初期配置案を作成", blockCount: "ブロック数", componentCount: "部品数", capacitorCount: "コンデンサ数", placementPreview: "初期配置プレビュー",
  placementPreviewHelp: "破線は移動案を示します。採用対象は強調表示されます。", noPlacementPlan: "初期配置案がありません。", group: "ブロック", reason: "理由",
  confirmPlacement: "部品移動案を確認しました。", applyPlacement: "選択した配置を適用", selectedCount: "選択数", removableVias: "削除候補ビア",
  edgeOperation: "処理", optimizeOperation: "面積最適化", smoothOperation: "滑らか化", filletOperation: "フィレット",
});
Object.assign(translations.en, {
  fitPreview: "Fit", zoomIn: "Zoom in", zoomOut: "Zoom out", locateInKicad: "Show location in KiCad",
  locateComplete: "Selected the finding evidence in KiCad.", locateUnavailable: "No matching KiCad item could be selected.",
  fixPreviewTitle: "Antenna-fix preview", fixPreviewHelp: "Overlay proposed tracks, vias, and rule areas on the board.",
  silkPreviewTitle: "Silkscreen placement preview", silkPreviewHelp: "Review current silkscreen and proposed values by layer.",
  idleTimeout: "Idle shutdown (minutes, 0 disables)", heartbeatInterval: "KiCad heartbeat interval (seconds)",
  cornerMinSegment: "Minimum segment for corner check (mm)", longNetMode: "Long-net trigger mode", longNetSevere: "Severe single-excess multiplier", longNetScanBudget: "Route-diameter scan budget",
  excludePadCorners: "Exclude corners inside same-net pads and vias",
  outlineStrategy: "Outline strategy", targetVertices: "Target vertex count", preserveConcavities: "Preserve only concavities already present",
  layerAll: "All", layerNone: "Hide all", previewPads: "Pads", previewVias: "Vias", previewFootprints: "Footprints",
  previewFindings: "Findings", previewFixes: "Fix plan", previewSilkPlan: "Silk plan", noMatchingFindings: "No matching findings.", atLeastOnePreset: "Select at least one track width and one via preset.",
  descriptionHeading: "Description", recommendationHeading: "Recommendation", metricsHeading: "Evidence", itemCount: "Related items",
  connectionRestored: "Reconnected to KiCad.", connectionLost: "KiCad connection is unavailable; retrying.",
  multipleSelectionHelp: "Multiple selections are supported. Automatic fixes safely use a profile-compliant default geometry.",
  vertexCount: "Vertices", strategy: "Strategy", preservedConcavity: "Preserved concavities",
  locateInPreview: "Show location in preview", selectAllLayers: "Show all layers", clearLayers: "Hide all layers",
  selectAll: "Select all", clearSelection: "Clear", adopt: "Adopt", angle: "Angle", distance: "Distance",
  smoothOutline: "Smooth current outline", filletOutline: "Fillet current outline", viaStitching: "GND via stitching",
  viaStitchingHelp: "Use moderate density only where the same GND net exists on both outer layers and clearance is safe.",
  rebuildPerimeterVias: "Safely rebuild existing perimeter vias", planStitching: "Plan stitching", noStitchingPlan: "No stitching plan yet.",
  confirmStitching: "I reviewed additions and any removals.", applyStitching: "Apply selected stitching vias", source: "Source",
  initialPlacement: "Initial placement", placementHeroTitle: "Group footprints by schematic block", placementHeroText: "Preserve locked footprints, keep connectors near block perimeters, and place decoupling capacitors close to associated pads.",
  planPlacement: "Plan initial placement", blockCount: "Blocks", componentCount: "Components", capacitorCount: "Capacitors", placementPreview: "Initial-placement preview",
  placementPreviewHelp: "Dashed vectors show proposed movement; selected proposals are emphasized.", noPlacementPlan: "No placement plan yet.", group: "Group", reason: "Reason",
  confirmPlacement: "I reviewed the proposed footprint movements.", applyPlacement: "Apply selected placements", selectedCount: "Selected", removableVias: "Removable vias",
  edgeOperation: "Operation", optimizeOperation: "Optimize area", smoothOperation: "Smooth", filletOperation: "Fillet",
});

const viewMetadata = {
  dashboard: ["dashboard", "dashboardSubtitle"],
  fixes: ["antennaFixes", "fixHeroText"],
  silkscreen: ["silkscreen", "silkHeroText"],
  edge: ["boardOutline", "edgeHeroText"],
  placement: ["initialPlacement", "placementHeroText"],
  manufacturing: ["manufacturing", "mfgHeroText"],
  quantitative: ["quantitative", "quantHeroText"],
  settings: ["settings", "generalSettingsText"],
};

function t(key) {
  return translations[state.language]?.[key] ?? translations.en[key] ?? key;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
  const method = options.method || "GET";
  const response = await fetch(path, {
    method,
    cache: "no-store",
    headers: {
      "X-EMI-Guardian-Token": sessionToken,
      "Content-Type": "application/json",
    },
    body: method === "GET" ? undefined : JSON.stringify(options.body || {}),
  });
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`HTTP ${response.status}`);
  }
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error?.message || `HTTP ${response.status}`);
  }
  return payload.data;
}

function setBusy(button, busy) {
  button.disabled = busy || button.dataset.permanentDisabled === "true";
  button.classList.toggle("loading", busy);
}

function showToast(message, kind = "success", timeout = 5000) {
  const region = document.getElementById("toastRegion");
  const toast = document.createElement("div");
  toast.className = `toast ${kind}`;
  toast.textContent = message;
  region.appendChild(toast);
  window.setTimeout(() => toast.remove(), timeout);
}

function showBanner(message, kind = "warning") {
  const banner = document.getElementById("globalBanner");
  banner.textContent = message;
  banner.className = `banner ${kind}`;
}

function clearBanner() {
  document.getElementById("globalBanner").classList.add("hidden");
}

function applyTranslations() {
  document.documentElement.lang = state.language;
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-title]").forEach((node) => {
    node.title = t(node.dataset.i18nTitle);
  });
  document.getElementById("languageButton").textContent = state.language === "ja" ? "EN" : "日本語";
  const active = document.querySelector(".nav-item.active")?.dataset.view || "dashboard";
  setViewTitle(active);
  loadManufacturingControls(true);
  renderAll();
}

function setViewTitle(view) {
  const [titleKey, subtitleKey] = viewMetadata[view] || viewMetadata.dashboard;
  document.getElementById("viewTitle").textContent = t(titleKey);
  document.getElementById("viewSubtitle").textContent = t(subtitleKey);
}

function switchView(view) {
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  document.querySelectorAll(".view").forEach((section) => section.classList.toggle("active", section.id === `view-${view}`));
  setViewTitle(view);
}

function initializeNavigation() {
  document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  document.querySelectorAll(".settings-link").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".settings-link").forEach((item) => item.classList.toggle("active", item === button));
      document.querySelectorAll(".settings-pane").forEach((pane) => pane.classList.toggle("active", pane.id === `settings-${button.dataset.settings}`));
    });
  });
}

function renderStatus() {
  if (!state.status) return;
  const connected = state.status.connection?.connected !== false;
  document.getElementById("connectionDot").classList.toggle("connected", connected);
  document.getElementById("boardName").textContent = state.status.board?.name || "—";
  const dryRun = Boolean(state.config?.fixes?.dry_run ?? state.status.dry_run);
  const badge = document.getElementById("dryRunBadge");
  badge.textContent = dryRun ? "DRY RUN" : "LIVE WRITE";
  badge.classList.toggle("live", !dryRun);
  document.getElementById("modeValue").textContent = dryRun ? t("blocked") : t("enabled");
  document.getElementById("modeSummary").textContent = state.language === "ja"
    ? (dryRun ? "基板への書き込みを停止中" : "明示確認後のみ書き込み")
    : (dryRun ? "Board writes disabled" : "Explicit confirmation required");
  updateApplyButtons();
}

function severityCount(analysis, levels) {
  return analysis?.findings?.filter((finding) => levels.includes(finding.severity)).length || 0;
}

function renderDashboard() {
  const analysis = state.analysis;
  document.getElementById("scoreValue").textContent = analysis ? Number(analysis.score).toFixed(1) : "—";
  document.getElementById("scoreLabel").textContent = analysis ? scoreLabel(analysis.score) : t("notScanned");
  document.getElementById("criticalValue").textContent = analysis ? severityCount(analysis, ["critical", "high"]) : "—";
  document.getElementById("findingValue").textContent = analysis ? analysis.findings.length : "—";
  if (analysis) {
    const medium = severityCount(analysis, ["medium"]);
    const lower = severityCount(analysis, ["low", "info"]);
    document.getElementById("findingSummary").textContent = state.language === "ja"
      ? `中 ${medium}件 · 低 ${lower}件`
      : `${medium} medium · ${lower} lower`;
  } else {
    document.getElementById("findingSummary").textContent = "—";
  }
  renderCategoryScores();
  renderFindings();
  renderBoardPreview();
}

function scoreLabel(score) {
  const value = Number(score);
  if (state.language === "ja") {
    if (value >= 90) return "良好";
    if (value >= 75) return "要確認";
    if (value >= 55) return "改善推奨";
    return "重大な改善が必要";
  }
  if (value >= 90) return "Good";
  if (value >= 75) return "Review";
  if (value >= 55) return "Improvement recommended";
  return "Major improvement required";
}

function categoryLabel(category) {
  const labels = state.language === "ja"
    ? { antenna: "アンテナ", parallel: "平行配線", corner: "折れ角", length: "配線長", return_path: "リターンパス", other: "その他" }
    : { antenna: "Antenna", parallel: "Parallel", corner: "Corners", length: "Length", return_path: "Return path", other: "Other" };
  return labels[category] || category;
}

function renderCategoryScores() {
  const container = document.getElementById("categoryScores");
  if (!state.analysis) {
    container.innerHTML = `<div class="empty-block"><span>${escapeHtml(t("noAnalysis"))}</span></div>`;
    return;
  }
  container.innerHTML = Object.entries(state.analysis.category_scores || {}).map(([name, value]) => `
    <div class="score-row"><span>${escapeHtml(categoryLabel(name))}</span><progress class="progress" max="100" value="${Math.max(0, Math.min(100, Number(value)))}"></progress><strong>${Number(value).toFixed(0)}</strong></div>
  `).join("");
}

function findingPresentation(finding) {
  const localized = finding?.localized?.[state.language] || finding?.localized?.en || {};
  return {
    title: localized.title || finding?.title || "",
    description: localized.description || finding?.description || "",
    recommendation: localized.recommendation || finding?.recommendation || "",
    metricLabels: localized.metric_labels || {},
  };
}

function metricValue(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return state.language === "ja" ? (value ? "はい" : "いいえ") : (value ? "Yes" : "No");
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : Number(value).toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function renderFindings() {
  const list = document.getElementById("findingList");
  const severity = document.getElementById("severityFilter").value;
  const category = document.getElementById("categoryFilter").value;
  if (!state.analysis) {
    list.innerHTML = `<div class="empty-block"><strong>${escapeHtml(t("noAnalysis"))}</strong><span>${escapeHtml(t("runFirstScan"))}</span></div>`;
    return;
  }
  const categories = [...new Set(state.analysis.findings.map((item) => item.category))].sort();
  const categorySelect = document.getElementById("categoryFilter");
  const current = categorySelect.value;
  categorySelect.innerHTML = `<option value="all">${escapeHtml(t("allCategories"))}</option>${categories.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(categoryLabel(item))}</option>`).join("")}`;
  if (["all", ...categories].includes(current)) categorySelect.value = current;
  const filtered = state.analysis.findings.filter((finding) => (severity === "all" || finding.severity === severity) && (category === "all" || finding.category === category));
  document.getElementById("findingsCaption").textContent = `${filtered.length} / ${state.analysis.findings.length}`;
  if (!filtered.length) {
    list.innerHTML = `<div class="empty-block"><strong>${escapeHtml(t("noMatchingFindings"))}</strong></div>`;
    return;
  }
  list.innerHTML = filtered.map((finding) => {
    const text = findingPresentation(finding);
    const selected = state.activeFindingId === finding.finding_id ? " selected" : "";
    return `<article class="finding-card${selected}" data-finding-id="${escapeHtml(finding.finding_id)}">
      <div class="severity-bar ${escapeHtml(finding.severity)}"></div>
      <div><div class="finding-title"><strong>${escapeHtml(text.title)}</strong><span class="pill ${escapeHtml(finding.severity)}">${escapeHtml(finding.severity)}</span><span class="pill">${escapeHtml(categoryLabel(finding.category))}</span></div><p>${escapeHtml(text.description)}</p><div class="finding-actions"><button type="button" class="finding-locate" data-preview-finding="${escapeHtml(finding.finding_id)}">◎ ${escapeHtml(t("locateInPreview"))}</button><button type="button" class="finding-locate" data-locate-finding="${escapeHtml(finding.finding_id)}">⌖ ${escapeHtml(t("locateInKicad"))}</button></div></div>
      <div class="finding-meta"><div>${Math.round(Number(finding.confidence) * 100)}%</div><div>−${Number(finding.score_penalty).toFixed(1)} pt</div></div>
    </article>`;
  }).join("");
  list.querySelectorAll(".finding-card").forEach((card) => {
    card.addEventListener("click", () => openFinding(card.dataset.findingId));
    card.addEventListener("mouseenter", () => setHoverFinding(card.dataset.findingId));
    card.addEventListener("mouseleave", () => setHoverFinding(""));
    card.addEventListener("focusin", () => setHoverFinding(card.dataset.findingId));
    card.addEventListener("focusout", () => setHoverFinding(""));
  });
  list.querySelectorAll("[data-preview-finding]").forEach((button) => button.addEventListener("click", (event) => {
    event.stopPropagation();
    focusFindingInPreview(button.dataset.previewFinding);
  }));
  list.querySelectorAll("[data-locate-finding]").forEach((button) => button.addEventListener("click", async (event) => {
    event.stopPropagation();
    await locateFinding(button.dataset.locateFinding, button);
  }));
}

function svgElement(name, attributes = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
}

function previewBounds(bounds) {
  const width = Math.max(1, Number(bounds.max_x) - Number(bounds.min_x));
  const height = Math.max(1, Number(bounds.max_y) - Number(bounds.min_y));
  const margin = Math.max(width, height) * 0.06;
  return { x: Number(bounds.min_x) - margin, y: Number(bounds.min_y) - margin, width: width + 2 * margin, height: height + 2 * margin };
}

function layerClass(layer) {
  const normalized = String(layer || "").toLowerCase().replaceAll(".", "-").replaceAll("_", "-");
  if (normalized.startsWith("in") && normalized.endsWith("-cu")) return "layer-inner-cu";
  return `layer-${normalized}`;
}

function previewLayerNames(options = {}) {
  const base = state.preview?.available_layers || [];
  const names = [...base];
  for (const pseudo of ["Pads", "Vias", "Footprints", "Findings"]) if (!names.includes(pseudo)) names.push(pseudo);
  if (options.fixes && !names.includes("Fix Preview")) names.push("Fix Preview");
  if (options.silk && !names.includes("Silk Preview")) names.push("Silk Preview");
  if (options.edge && !names.includes("Edge Proposal")) names.push("Edge Proposal");
  if (options.stitching && !names.includes("Stitching Preview")) names.push("Stitching Preview");
  if (options.placement && !names.includes("Placement Preview")) names.push("Placement Preview");
  return names;
}

function layerLabel(layer) {
  const labels = {
    Pads: t("previewPads"), Vias: t("previewVias"), Footprints: t("previewFootprints"), Findings: t("previewFindings"),
    "Fix Preview": t("previewFixes"), "Silk Preview": t("previewSilkPlan"), "Edge Proposal": t("boardOutline"),
    "Stitching Preview": t("viaStitching"), "Placement Preview": t("initialPlacement"),
  };
  return labels[layer] || layer;
}

function ensureLayerDefaults(names) {
  for (const name of names) {
    if (state.layerVisibility[name] === undefined) state.layerVisibility[name] = true;
  }
}

function renderLayerToggles(containerId, options = {}) {
  const container = document.getElementById(containerId);
  if (!container || !state.preview) return;
  const names = previewLayerNames(options);
  ensureLayerDefaults(names);
  container.innerHTML = `<button type="button" class="layer-toggle layer-toggle-action" data-layer-action="all">${escapeHtml(t("selectAllLayers"))}</button><button type="button" class="layer-toggle layer-toggle-action" data-layer-action="none">${escapeHtml(t("clearLayers"))}</button>${names.map((name) => `<button type="button" class="layer-toggle${state.layerVisibility[name] ? " active" : ""}" data-layer-toggle="${escapeHtml(name)}">${escapeHtml(layerLabel(name))}</button>`).join("")}`;
  container.querySelectorAll("[data-layer-action]").forEach((button) => button.addEventListener("click", () => {
    const visible = button.dataset.layerAction === "all";
    for (const name of names) state.layerVisibility[name] = visible;
    // Findings remain available even after clearing every physical layer so
    // the user cannot accidentally hide the review targets themselves.
    state.layerVisibility.Findings = true;
    renderAllPreviews();
  }));
  container.querySelectorAll("[data-layer-toggle]").forEach((button) => button.addEventListener("click", () => {
    const name = button.dataset.layerToggle;
    state.layerVisibility[name] = !state.layerVisibility[name];
    renderAllPreviews();
  }));
}

function isLayerVisible(layer) {
  return state.layerVisibility[layer] !== false;
}

function polygonPath(polygon) {
  const outline = polygon?.outline || polygon || [];
  if (!outline.length) return "";
  let path = `M ${outline.map((point) => `${point.x} ${point.y}`).join(" L ")} Z`;
  for (const hole of polygon?.holes || []) {
    if (hole.length) path += ` M ${hole.map((point) => `${point.x} ${point.y}`).join(" L ")} Z`;
  }
  return path;
}

function appendPreviewGeometry(fragment, options = {}) {
  const preview = state.preview;
  if (!preview) return;
  for (const zone of preview.zones || []) {
    const filledLayers = Object.entries(zone.filled || {});
    if (filledLayers.length) {
      for (const [layer, polygons] of filledLayers) {
        if (!isLayerVisible(layer)) continue;
        for (const polygon of polygons) {
          const d = polygonPath(polygon);
          if (d) fragment.appendChild(svgElement("path", { d, class: `preview-zone ${layerClass(layer)}`, "fill-rule": "evenodd", "data-layer": layer }));
        }
      }
    } else {
      const layer = zone.layers?.[0] || "F.Cu";
      if (isLayerVisible(layer) && zone.outline?.length) fragment.appendChild(svgElement("polygon", { points: zone.outline.map((p) => `${p.x},${p.y}`).join(" "), class: `preview-zone ${layerClass(layer)}`, "data-layer": layer }));
    }
  }
  for (const track of preview.tracks || []) {
    if (!isLayerVisible(track.layer)) continue;
    fragment.appendChild(svgElement("line", { x1: track.start.x, y1: track.start.y, x2: track.end.x, y2: track.end.y, class: `preview-track ${layerClass(track.layer)}`, "stroke-width": Math.max(0.35, Number(track.width)), "data-layer": track.layer, "data-item-id": track.source_item_id || track.item_id }));
  }
  if (isLayerVisible("Pads")) {
    for (const pad of preview.pads || []) {
      const b = pad.bounds;
      fragment.appendChild(svgElement("rect", { x: b.min_x, y: b.min_y, width: Math.max(0.05, b.max_x - b.min_x), height: Math.max(0.05, b.max_y - b.min_y), rx: 0.08, class: "preview-pad", "data-layer": "Pads", "data-item-id": pad.item_id }));
    }
  }
  if (isLayerVisible("Vias")) {
    for (const via of preview.vias || []) {
      fragment.appendChild(svgElement("circle", { cx: via.position.x, cy: via.position.y, r: Math.max(0.05, Number(via.diameter) / 2), class: "preview-via", "data-layer": "Vias", "data-item-id": via.item_id }));
      fragment.appendChild(svgElement("circle", { cx: via.position.x, cy: via.position.y, r: Math.max(0.025, Number(via.drill) / 2), class: "preview-drill", "data-layer": "Vias" }));
    }
  }
  if (isLayerVisible("Footprints")) {
    for (const footprint of preview.footprints || []) {
      const b = footprint.bounds;
      fragment.appendChild(svgElement("rect", { x: b.min_x, y: b.min_y, width: Math.max(0.05, b.max_x - b.min_x), height: Math.max(0.05, b.max_y - b.min_y), class: "preview-footprint", "data-layer": "Footprints", "data-item-id": footprint.item_id }));
    }
  }
  for (const text of preview.silkscreen || []) {
    if (!isLayerVisible(text.layer)) continue;
    const node = svgElement("text", { x: text.position.x, y: text.position.y, class: `preview-silk ${layerClass(text.layer)}`, "font-size": Math.max(0.35, Number(text.height)), "text-anchor": "middle", "dominant-baseline": "middle", transform: `rotate(${Number(text.angle_deg || 0)} ${text.position.x} ${text.position.y})`, "data-layer": text.layer });
    node.textContent = text.text;
    fragment.appendChild(node);
  }
  if (isLayerVisible("Edge.Cuts")) {
    for (const edge of preview.edges || []) {
      if (edge.kind === "arc" && edge.mid) fragment.appendChild(svgElement("path", { d: `M ${edge.start.x} ${edge.start.y} Q ${edge.mid.x} ${edge.mid.y} ${edge.end.x} ${edge.end.y}`, class: "board-edge", "data-layer": "Edge.Cuts" }));
      else fragment.appendChild(svgElement("line", { x1: edge.start.x, y1: edge.start.y, x2: edge.end.x, y2: edge.end.y, class: "board-edge", "data-layer": "Edge.Cuts" }));
    }
  }
  if (options.fixes && isLayerVisible("Fix Preview")) appendFixOverlays(fragment);
  if (options.silk && isLayerVisible("Silk Preview")) appendSilkOverlays(fragment);
  if (options.stitching && isLayerVisible("Stitching Preview")) appendStitchingOverlays(fragment);
  if (options.placement && isLayerVisible("Placement Preview")) appendPlacementOverlays(fragment);
  if (isLayerVisible("Findings")) appendFindingMarkers(fragment);
}

function appendFindingMarkers(fragment) {
  const view = state.previewViews.boardPreview?.base || previewBounds(state.preview.bounds);
  const radius = Math.max(view.width, view.height) * 0.0075;
  for (const finding of state.preview.findings || []) {
    if (!finding.location) continue;
    const selected = state.activeFindingId === finding.id ? " selected" : "";
    const hovered = state.hoverFindingId === finding.id ? " hovered" : "";
    const marker = svgElement("circle", { cx: finding.location.x, cy: finding.location.y, r: radius, class: `finding-marker ${finding.severity}${selected}${hovered}`, tabindex: "0", role: "button", "data-finding-id": finding.id, "data-layer": "Findings" });
    const full = findingById(finding.id);
    const title = svgElement("title");
    title.textContent = full ? findingPresentation(full).title : finding.id;
    marker.appendChild(title);
    fragment.appendChild(marker);
  }
}

function appendFixOverlays(fragment) {
  for (const action of state.fixPlan?.actions || []) {
    const selected = state.selectedFixIds.has(action.action_id);
    const selectionClass = selected ? " proposal-selected" : " proposal-unselected";
    if (action.start && action.end) fragment.appendChild(svgElement("line", { x1: action.start.x, y1: action.start.y, x2: action.end.x, y2: action.end.y, class: `fix-track${selectionClass}`, "stroke-width": Math.max(0.05, Number(action.parameters?.width_mm || state.config?.fixes?.track_width_mm || 0.2)), "data-action-id": action.action_id, "data-layer": "Fix Preview" }));
    if (action.position) fragment.appendChild(svgElement("circle", { cx: action.position.x, cy: action.position.y, r: Math.max(0.2, Number(action.parameters?.diameter_mm || 0.6) / 2), class: `fix-via${selectionClass}`, "data-action-id": action.action_id, "data-layer": "Fix Preview" }));
    if (action.polygon?.outline?.length) fragment.appendChild(svgElement("path", { d: polygonPath(action.polygon), class: `fix-rule-area${selectionClass}`, "fill-rule": "evenodd", "data-action-id": action.action_id, "data-layer": "Fix Preview" }));
  }
}

function appendSilkOverlays(fragment) {
  for (const placement of state.silkPlan?.placements || []) {
    const selected = state.selectedSilkIds.has(placement.placement_id);
    const node = svgElement("text", { x: placement.position.x, y: placement.position.y, class: `silk-proposal${selected ? " proposal-selected" : " proposal-unselected"}`, "font-size": Math.max(0.35, Number(placement.text_height_mm || 0.8)), "text-anchor": "middle", "dominant-baseline": "middle", transform: `rotate(${Number(placement.angle_deg || 0)} ${placement.position.x} ${placement.position.y})`, "data-placement-id": placement.placement_id, "data-layer": "Silk Preview" });
    node.textContent = placement.value;
    fragment.appendChild(node);
  }
}

function appendStitchingOverlays(fragment) {
  for (const candidate of state.stitchingPlan?.candidates || []) {
    const selected = state.selectedStitchingIds.has(candidate.candidate_id);
    fragment.appendChild(svgElement("circle", {
      cx: candidate.position.x,
      cy: candidate.position.y,
      r: Math.max(0.2, Number(candidate.diameter_mm || 0.6) / 2),
      class: `stitching-via${candidate.critical_vertex ? " critical-vertex" : ""}${selected ? " proposal-selected" : " proposal-unselected"}`,
      "data-candidate-id": candidate.candidate_id,
      "data-layer": "Stitching Preview",
    }));
  }
  const removable = new Set(state.stitchingPlan?.removable_via_ids || []);
  for (const via of state.preview?.vias || []) {
    if (!removable.has(via.item_id)) continue;
    fragment.appendChild(svgElement("circle", {
      cx: via.position.x,
      cy: via.position.y,
      r: Math.max(0.3, Number(via.diameter || 0.6) / 2 + 0.2),
      class: "stitching-remove",
      "data-layer": "Stitching Preview",
    }));
  }
}

function appendPlacementOverlays(fragment) {
  for (const group of state.placementPlan?.groups || []) {
    const b = group.bounds;
    fragment.appendChild(svgElement("rect", {
      x: b.min_x,
      y: b.min_y,
      width: Math.max(0.05, Number(b.max_x) - Number(b.min_x)),
      height: Math.max(0.05, Number(b.max_y) - Number(b.min_y)),
      class: "placement-group-box",
      "data-layer": "Placement Preview",
    }));
    const title = svgElement("text", {
      x: b.min_x + 0.5,
      y: b.min_y + 0.9,
      class: "placement-group-label",
      "font-size": 0.8,
      "text-anchor": "start",
      "data-layer": "Placement Preview",
    });
    title.textContent = group.title || group.group_id;
    fragment.appendChild(title);
  }
  for (const placement of state.placementPlan?.placements || []) {
    const selected = state.selectedPlacementIds.has(placement.placement_id);
    const selectionClass = selected ? " proposal-selected" : " proposal-unselected";
    const lockedClass = placement.locked ? " locked" : "";
    const className = `placement-proposal${selectionClass}${lockedClass}`;
    fragment.appendChild(svgElement("line", {
      x1: placement.old_position.x,
      y1: placement.old_position.y,
      x2: placement.position.x,
      y2: placement.position.y,
      class: `${className} placement-vector`,
      "data-placement-id": placement.placement_id,
      "data-layer": "Placement Preview",
    }));

    const bounds = placement.destination_bounds;
    if (bounds) {
      fragment.appendChild(svgElement("rect", {
        x: bounds.min_x,
        y: bounds.min_y,
        width: Math.max(0.05, Number(bounds.max_x) - Number(bounds.min_x)),
        height: Math.max(0.05, Number(bounds.max_y) - Number(bounds.min_y)),
        class: `${className} placement-footprint-body`,
        "data-placement-id": placement.placement_id,
        "data-layer": "Placement Preview",
      }));
    }
    for (const pad of placement.preview_pads || []) {
      const b = pad.bounds;
      fragment.appendChild(svgElement("rect", {
        x: b.min_x,
        y: b.min_y,
        width: Math.max(0.05, Number(b.max_x) - Number(b.min_x)),
        height: Math.max(0.05, Number(b.max_y) - Number(b.min_y)),
        class: `${className} placement-pad`,
        "data-placement-id": placement.placement_id,
        "data-layer": "Placement Preview",
      }));
    }
    for (const text of placement.preview_texts || []) {
      if (!text.visible && text.kind !== "reference") continue;
      const node = svgElement("text", {
        x: text.position.x,
        y: text.position.y,
        class: `${className} placement-field placement-field-${text.kind}`,
        "font-size": Math.max(0.45, Number(text.height || 0.8)),
        "text-anchor": "middle",
        "dominant-baseline": "middle",
        transform: `rotate(${Number(text.angle_deg || 0)} ${text.position.x} ${text.position.y})`,
        "data-placement-id": placement.placement_id,
        "data-layer": "Placement Preview",
      });
      node.textContent = text.text;
      fragment.appendChild(node);
    }
    const labelY = bounds ? Number(bounds.min_y) - 0.65 : Number(placement.position.y) - 0.65;
    const label = svgElement("text", {
      x: placement.position.x,
      y: labelY,
      class: `${className} placement-identity-label`,
      "font-size": 0.75,
      "text-anchor": "middle",
      "dominant-baseline": "auto",
      "data-placement-id": placement.placement_id,
      "data-layer": "Placement Preview",
    });
    label.textContent = `${placement.reference}${placement.value ? ` · ${placement.value}` : ""}`;
    const title = svgElement("title");
    title.textContent = `${placement.reference} ${placement.value || ""} → (${Number(placement.position.x).toFixed(2)}, ${Number(placement.position.y).toFixed(2)})`;
    label.appendChild(title);
    fragment.appendChild(label);
    fragment.appendChild(svgElement("circle", {
      cx: placement.position.x,
      cy: placement.position.y,
      r: 0.28,
      class: `${className} placement-target`,
      "data-placement-id": placement.placement_id,
      "data-layer": "Placement Preview",
    }));
  }
}

function setPreviewView(svgId, view) {
  const svg = document.getElementById(svgId);
  if (!svg || !view) return;
  svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.width} ${view.height}`);
}

function fitPreview(svgId) {
  const existing = state.previewViews[svgId];
  if (existing?.base) {
    existing.view = { ...existing.base };
    setPreviewView(svgId, existing.view);
    return;
  }
  const bounds = state.preview?.bounds;
  if (!bounds) return;
  const base = previewBounds(bounds);
  state.previewViews[svgId] = { base: { ...base }, view: { ...base } };
  setPreviewView(svgId, base);
}

function zoomPreview(svgId, factor, center = null) {
  const holder = state.previewViews[svgId];
  if (!holder) return;
  const view = holder.view;
  const cx = center?.x ?? (view.x + view.width / 2);
  const cy = center?.y ?? (view.y + view.height / 2);
  const nextWidth = Math.max(holder.base.width * 0.02, Math.min(holder.base.width * 20, view.width * factor));
  const nextHeight = Math.max(holder.base.height * 0.02, Math.min(holder.base.height * 20, view.height * factor));
  holder.view = { x: cx - (cx - view.x) * nextWidth / view.width, y: cy - (cy - view.y) * nextHeight / view.height, width: nextWidth, height: nextHeight };
  setPreviewView(svgId, holder.view);
}

function svgPointFromEvent(svg, event) {
  const point = svg.createSVGPoint();
  point.x = event.clientX; point.y = event.clientY;
  const matrix = svg.getScreenCTM();
  return matrix ? point.matrixTransform(matrix.inverse()) : { x: 0, y: 0 };
}

function findingById(id) {
  return state.analysis?.findings?.find((item) => item.finding_id === id) || null;
}

function refreshFindingMarkerClasses() {
  document.querySelectorAll(".finding-marker[data-finding-id]").forEach((marker) => {
    const id = marker.dataset.findingId;
    marker.classList.toggle("selected", state.activeFindingId === id);
    marker.classList.toggle("hovered", state.hoverFindingId === id);
  });
  document.querySelectorAll(".finding-card[data-finding-id]").forEach((card) => {
    const id = card.dataset.findingId;
    card.classList.toggle("selected", state.activeFindingId === id);
    card.classList.toggle("hovered", state.hoverFindingId === id);
  });
}

function setHoverFinding(id) {
  state.hoverFindingId = id || "";
  refreshFindingMarkerClasses();
}

function showPreviewTooltip(svgId, findingId, event) {
  const stage = document.querySelector(`[data-preview-stage="${svgId}"]`);
  const tooltip = document.querySelector(`[data-preview-tooltip="${svgId}"]`);
  const finding = findingById(findingId);
  if (!stage || !tooltip || !finding) return;
  const text = findingPresentation(finding);
  const rect = stage.getBoundingClientRect();
  tooltip.innerHTML = `<strong>${escapeHtml(text.title)}</strong><span>${escapeHtml(categoryLabel(finding.category))} · ${escapeHtml(finding.severity)} · ${Math.round(Number(finding.confidence) * 100)}%</span>`;
  tooltip.style.left = `${Math.max(8, Math.min(rect.width - 230, event.clientX - rect.left + 12))}px`;
  tooltip.style.top = `${Math.max(8, Math.min(rect.height - 72, event.clientY - rect.top + 12))}px`;
  tooltip.classList.remove("hidden");
}

function hidePreviewTooltip(svgId) {
  const tooltip = document.querySelector(`[data-preview-tooltip="${svgId}"]`);
  if (tooltip) tooltip.classList.add("hidden");
}

function focusPointInPreview(svgId, point, scale = 0.18) {
  if (!point || !state.preview?.bounds) return;
  if (!state.previewViews[svgId]) fitPreview(svgId);
  const holder = state.previewViews[svgId];
  if (!holder) return;
  const width = Math.max(holder.base.width * 0.025, holder.base.width * scale);
  const height = Math.max(holder.base.height * 0.025, holder.base.height * scale);
  holder.view = { x: Number(point.x) - width / 2, y: Number(point.y) - height / 2, width, height };
  setPreviewView(svgId, holder.view);
}

function focusFindingInPreview(id, svgId = "boardPreview", switchToDashboard = true) {
  const finding = state.preview?.findings?.find((item) => item.id === id);
  if (!finding?.location) return false;
  state.activeFindingId = id;
  if (switchToDashboard) switchView("dashboard");
  focusPointInPreview(svgId, finding.location);
  refreshFindingMarkerClasses();
  const card = [...document.querySelectorAll(".finding-card[data-finding-id]")]
    .find((item) => item.dataset.findingId === id);
  if (card) card.scrollIntoView({ behavior: "smooth", block: "center" });
  return true;
}

function bindPreviewInteraction(svgId) {
  const svg = document.getElementById(svgId);
  const stage = document.querySelector(`[data-preview-stage="${svgId}"]`);
  if (!svg || !stage || stage.dataset.previewBound === "true") return;
  stage.dataset.previewBound = "true";
  stage.addEventListener("wheel", (event) => { event.preventDefault(); zoomPreview(svgId, event.deltaY < 0 ? 0.82 : 1.22, svgPointFromEvent(svg, event)); }, { passive: false });
  let dragStart = null;
  stage.addEventListener("pointerdown", (event) => {
    dragStart = {
      point: svgPointFromEvent(svg, event),
      clientX: event.clientX,
      clientY: event.clientY,
      moved: false,
      view: { ...state.previewViews[svgId]?.view },
    };
    stage.setPointerCapture(event.pointerId);
  });
  stage.addEventListener("pointermove", (event) => {
    if (!dragStart || !state.previewViews[svgId]) return;
    const screenDistance = Math.hypot(event.clientX - dragStart.clientX, event.clientY - dragStart.clientY);
    if (!dragStart.moved && screenDistance < 4) return;
    dragStart.moved = true;
    stage.classList.add("dragging");
    const current = svgPointFromEvent(svg, event);
    const initial = dragStart.view;
    state.previewViews[svgId].view = { ...initial, x: initial.x + dragStart.point.x - current.x, y: initial.y + dragStart.point.y - current.y };
    setPreviewView(svgId, state.previewViews[svgId].view);
  });
  const stop = () => { dragStart = null; stage.classList.remove("dragging"); };
  stage.addEventListener("pointerup", stop); stage.addEventListener("pointercancel", stop);
  svg.addEventListener("click", (event) => {
    const marker = event.target.closest?.(".finding-marker[data-finding-id]");
    if (!marker) return;
    event.stopPropagation();
    openFinding(marker.dataset.findingId);
  });
  svg.addEventListener("pointerover", (event) => {
    const marker = event.target.closest?.(".finding-marker[data-finding-id]");
    if (!marker) return;
    setHoverFinding(marker.dataset.findingId);
    showPreviewTooltip(svgId, marker.dataset.findingId, event);
  });
  svg.addEventListener("pointermove", (event) => {
    const marker = event.target.closest?.(".finding-marker[data-finding-id]");
    if (marker) showPreviewTooltip(svgId, marker.dataset.findingId, event);
  });
  svg.addEventListener("pointerout", (event) => {
    const marker = event.target.closest?.(".finding-marker[data-finding-id]");
    if (!marker || marker.contains(event.relatedTarget)) return;
    setHoverFinding("");
    hidePreviewTooltip(svgId);
  });
  svg.addEventListener("keydown", (event) => {
    const marker = event.target.closest?.(".finding-marker[data-finding-id]");
    if (marker && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      openFinding(marker.dataset.findingId);
    }
  });
}

function boundsFromPoints(points) {
  const valid = (points || []).filter((point) => Number.isFinite(Number(point?.x)) && Number.isFinite(Number(point?.y)));
  if (!valid.length) return null;
  return {
    min_x: Math.min(...valid.map((point) => Number(point.x))),
    min_y: Math.min(...valid.map((point) => Number(point.y))),
    max_x: Math.max(...valid.map((point) => Number(point.x))),
    max_y: Math.max(...valid.map((point) => Number(point.y))),
  };
}

function previewOverlayBounds(options = {}) {
  let bounds = null;
  if (options.fixes) {
    const points = [];
    for (const action of state.fixPlan?.actions || []) {
      if (action.start) points.push(action.start);
      if (action.end) points.push(action.end);
      if (action.position) points.push(action.position);
      points.push(...(action.polygon?.outline || []));
    }
    bounds = unionBounds(bounds, boundsFromPoints(points));
  }
  if (options.silk) {
    bounds = unionBounds(bounds, boundsFromPoints((state.silkPlan?.placements || []).map((item) => item.position)));
  }
  if (options.stitching) {
    bounds = unionBounds(bounds, boundsFromPoints((state.stitchingPlan?.candidates || []).map((item) => item.position)));
  }
  if (options.placement) {
    const points = [];
    for (const item of state.placementPlan?.placements || []) {
      if (item.old_position) points.push(item.old_position);
      if (item.position) points.push(item.position);
    }
    bounds = unionBounds(bounds, boundsFromPoints(points));
  }
  return bounds;
}

function setPreviewBase(svgId, bounds) {
  if (!bounds) return;
  const base = previewBounds(bounds);
  const existing = state.previewViews[svgId];
  const changed = !existing?.base
    || Math.abs(existing.base.x - base.x) > 1.0e-6
    || Math.abs(existing.base.y - base.y) > 1.0e-6
    || Math.abs(existing.base.width - base.width) > 1.0e-6
    || Math.abs(existing.base.height - base.height) > 1.0e-6;
  if (changed) state.previewViews[svgId] = { base: { ...base }, view: { ...base } };
  setPreviewView(svgId, state.previewViews[svgId].view);
}

function renderInteractivePreview(svgId, emptyId, toggleId, options = {}) {
  const svg = document.getElementById(svgId);
  const empty = document.getElementById(emptyId);
  if (!svg || !empty) return;
  svg.replaceChildren();
  if (!state.preview?.bounds) { empty.classList.remove("hidden"); return; }
  if (
    (options.fixes && !state.fixPlan?.actions?.length)
    || (options.silk && !state.silkPlan?.placements?.length)
    || (options.placement && !state.placementPlan?.placements?.length)
  ) {
    empty.classList.remove("hidden");
  } else {
    empty.classList.add("hidden");
  }
  setPreviewBase(svgId, unionBounds(state.preview.bounds, previewOverlayBounds(options)));
  const fragment = document.createDocumentFragment();
  appendPreviewGeometry(fragment, options);
  svg.appendChild(fragment);
  renderLayerToggles(toggleId, options);
  bindPreviewInteraction(svgId);
}

function renderBoardPreview() {
  renderInteractivePreview("boardPreview", "previewEmpty", "boardLayerToggles");
}

function renderAllPreviews() {
  renderInteractivePreview("boardPreview", "previewEmpty", "boardLayerToggles");
  renderInteractivePreview("fixPreview", "fixPreviewEmpty", "fixLayerToggles", { fixes: true });
  renderInteractivePreview("silkPreview", "silkPreviewEmpty", "silkLayerToggles", { silk: true });
  renderEdgePreview();
  renderInteractivePreview("placementPreview", "placementPreviewEmpty", "placementLayerToggles", { placement: true });
}

function openFinding(id) {
  const finding = state.analysis?.findings?.find((item) => item.finding_id === id);
  if (!finding) return;
  state.activeFindingId = id;
  const text = findingPresentation(finding);
  document.getElementById("modalTitle").textContent = text.title;
  const metrics = Object.entries(finding.metrics || {}).map(([key, value]) => `<div><dt>${escapeHtml(text.metricLabels[key] || humanize(key))}</dt><dd>${escapeHtml(metricValue(value))}</dd></div>`).join("");
  document.getElementById("modalContent").innerHTML = `
    <div class="finding-title"><span class="pill ${escapeHtml(finding.severity)}">${escapeHtml(finding.severity)}</span><span class="pill">${escapeHtml(categoryLabel(finding.category))}</span><span class="pill">${Math.round(Number(finding.confidence) * 100)}%</span><span class="pill">${escapeHtml(t("itemCount"))}: ${(finding.item_ids || []).length}</span></div>
    <div class="modal-section"><h3>${escapeHtml(t("descriptionHeading"))}</h3><p>${escapeHtml(text.description)}</p></div>
    <div class="modal-section"><h3>${escapeHtml(t("recommendationHeading"))}</h3><p>${escapeHtml(text.recommendation)}</p></div>
    <div class="modal-section"><h3>${escapeHtml(t("metricsHeading"))}</h3><dl>${metrics || "—"}</dl></div>`;
  const locateButton = document.getElementById("locateFindingButton");
  locateButton.dataset.findingId = id;
  locateButton.disabled = !(finding.item_ids || []).length;
  const previewButton = document.getElementById("previewLocateFindingButton");
  previewButton.dataset.findingId = id;
  previewButton.disabled = !state.preview?.findings?.some((item) => item.id === id && item.location);
  document.getElementById("detailsModal").classList.remove("hidden");
  refreshFindingMarkerClasses();
}

async function locateFinding(id, button = null) {
  if (!id) return;
  try {
    if (button) setBusy(button, true);
    const result = await api("/api/locate", { method: "POST", body: { finding_id: id } });
    const selected = Number(result?.selected_count || 0);
    showToast(selected > 0 ? t("locateComplete") : t("locateUnavailable"), selected > 0 ? "success" : "error");
  } catch (error) {
    showToast(error.message, "error", 8000);
  } finally {
    if (button) setBusy(button, false);
  }
}

function renderFixPlan() {
  const plan = state.fixPlan;
  syncPlanSelection("fixes", plan?.actions || [], "action_id");
  const selectedActions = (plan?.actions || []).filter((item) => state.selectedFixIds.has(item.action_id));
  document.getElementById("fixSelectedCount").textContent = plan ? selectedActions.length : "—";
  document.getElementById("fixReduction").textContent = plan ? selectedActions.reduce((sum, item) => sum + Number(item.expected_risk_reduction || 0), 0).toFixed(2) : "—";
  document.getElementById("fixWarningCount").textContent = plan ? plan.warnings.length : "—";
  const body = document.getElementById("fixTableBody");
  if (!plan?.actions?.length) {
    body.innerHTML = `<tr><td colspan="7" class="table-empty">${escapeHtml(t("noFixPlan"))}</td></tr>`;
  } else {
    body.innerHTML = plan.actions.map((action) => `
      <tr class="${state.selectedFixIds.has(action.action_id) ? "row-selected" : "row-unselected"}" data-action-row="${escapeHtml(action.action_id)}" data-finding-id="${escapeHtml(action.finding_id)}"><td><input type="checkbox" data-fix-select="${escapeHtml(action.action_id)}" ${state.selectedFixIds.has(action.action_id) ? "checked" : ""}></td><td><code>${escapeHtml(action.finding_id)}</code></td><td><span class="pill">${escapeHtml(fixKindLabel(action.kind))}</span></td><td>${escapeHtml(action.layer)}</td><td>${Math.round(Number(action.confidence) * 100)}%</td><td>${Number(action.expected_risk_reduction * action.confidence - action.implementation_cost).toFixed(2)}</td><td>${escapeHtml(localizedFixDescription(action))}</td></tr>`).join("");
  }
  body.querySelectorAll("[data-fix-select]").forEach((checkbox) => checkbox.addEventListener("change", () => {
    const id = checkbox.dataset.fixSelect;
    if (checkbox.checked) state.selectedFixIds.add(id); else state.selectedFixIds.delete(id);
    renderFixPlan();
  }));
  body.querySelectorAll("[data-finding-id]").forEach((row) => {
    row.addEventListener("mouseenter", () => setHoverFinding(row.dataset.findingId));
    row.addEventListener("mouseleave", () => setHoverFinding(""));
  });
  renderInteractivePreview("fixPreview", "fixPreviewEmpty", "fixLayerToggles", { fixes: true });
  updateApplyButtons();
}

function fixKindLabel(kind) {
  const labels = state.language === "ja"
    ? { track_bridge: "GND配線", stitching_via: "GNDビア", track_and_via: "配線＋ビア", rule_area: "ルールエリア" }
    : { track_bridge: "GND bridge", stitching_via: "Stitching via", track_and_via: "Bridge + via", rule_area: "Rule area" };
  return labels[kind] || kind;
}

function localizedFixDescription(action) {
  const width = Number(action?.parameters?.width_mm);
  const widthText = Number.isFinite(width) && width > 0
    ? (state.language === "ja" ? `（配線幅 ${width.toFixed(2)} mm）` : ` (${width.toFixed(2)} mm wide)`)
    : "";
  if (state.language !== "ja") return `${action.description || ""}${widthText}`;
  const labels = {
    track_bridge: "既存ベタ上へ重ねるだけではないことを確認し、別のGND導体へ低インダクタンスの短い太配線を追加します。",
    stitching_via: "アンテナ候補位置へGNDステッチングビアを追加します。",
    track_and_via: "別レイヤーのGND銅箔へ到達する短い太配線とステッチングビアを組み合わせます。",
    rule_area: "検出した細長いGND突出部の形状に沿って、銅箔ベタだけを禁止するルールエリアを配置します。",
  };
  return `${labels[action.kind] || action.description || ""}${widthText}`;
}

function renderSilkPlan() {
  const plan = state.silkPlan;
  syncPlanSelection("silk", plan?.placements || [], "placement_id");
  const selectedPlacements = (plan?.placements || []).filter((item) => state.selectedSilkIds.has(item.placement_id));
  document.getElementById("silkPlaced").textContent = plan ? selectedPlacements.filter((item) => item.show_value).length : "—";
  document.getElementById("silkSkipped").textContent = plan ? plan.summary.skipped : "—";
  if (state.config?.silkscreen) document.getElementById("silkSize").textContent = `${state.config.silkscreen.text_width_mm} × ${state.config.silkscreen.text_height_mm}`;
  const body = document.getElementById("silkTableBody");
  if (!plan?.placements?.length) {
    body.innerHTML = `<tr><td colspan="7" class="table-empty">${escapeHtml(t("noSilkPlan"))}</td></tr>`;
  } else {
    body.innerHTML = plan.placements.slice(0, 800).map((placement) => `<tr class="${state.selectedSilkIds.has(placement.placement_id) ? "row-selected" : "row-unselected"}"><td><input type="checkbox" data-silk-select="${escapeHtml(placement.placement_id)}" ${state.selectedSilkIds.has(placement.placement_id) ? "checked" : ""}></td><td>${escapeHtml(placement.reference)}</td><td>${escapeHtml(placement.value)}</td><td>${escapeHtml(placement.layer)}</td><td>${Number(placement.angle_deg || 0).toFixed(0)}°</td><td>${Number(placement.distance_from_footprint_mm || 0).toFixed(2)} mm${placement.manual_review ? ` · ${escapeHtml(t("manualReview"))}` : ""}</td><td>${Number(placement.score).toFixed(2)}</td></tr>`).join("");
  }
  body.querySelectorAll("[data-silk-select]").forEach((checkbox) => checkbox.addEventListener("change", () => {
    const id = checkbox.dataset.silkSelect;
    if (checkbox.checked) state.selectedSilkIds.add(id); else state.selectedSilkIds.delete(id);
    renderSilkPlan();
  }));
  renderInteractivePreview("silkPreview", "silkPreviewEmpty", "silkLayerToggles", { silk: true });
  updateApplyButtons();
}

function renderEdgeProposal() {
  const proposal = state.edgeProposal;
  document.getElementById("edgeOriginal").textContent = proposal ? Number(proposal.original_area_mm2).toFixed(1) : "—";
  document.getElementById("edgeProposed").textContent = proposal ? Number(proposal.proposed_area_mm2).toFixed(1) : "—";
  document.getElementById("edgeReduction").textContent = proposal ? Number(proposal.reduction_percent).toFixed(1) : "—";
  document.getElementById("edgeGround").textContent = proposal ? (proposal.ground_band_verified ? t("verified") : t("unverified")) : "—";
  const details = document.getElementById("edgeDetails");
  details.innerHTML = proposal ? `<div><dt>${escapeHtml(t("mode"))}</dt><dd>${escapeHtml(localizedEdgeMode(proposal.mode))}</dd></div><div><dt>${escapeHtml(t("strategy"))}</dt><dd>${escapeHtml(localizedEdgeStrategy(proposal.outline_strategy || "—"))}</dd></div><div><dt>${escapeHtml(t("vertexCount"))}</dt><dd>${Number(proposal.actual_vertex_count || proposal.polygon?.outline?.length || 0)} / ${Number(proposal.target_vertex_count || 0)}</dd></div><div><dt>${escapeHtml(t("preservedConcavity"))}</dt><dd>${Number(proposal.preserved_concavity_count || 0)}</dd></div><div><dt>${escapeHtml(t("grid"))}</dt><dd>${Number(proposal.grid_mm).toFixed(2)} mm</dd></div><div><dt>${escapeHtml(t("fillet"))}</dt><dd>${Number(proposal.fillet_radius_mm).toFixed(2)} mm</dd></div>` : `<div><dt>${escapeHtml(t("mode"))}</dt><dd>—</dd></div>`;
  const warningBox = document.getElementById("edgeWarnings");
  warningBox.innerHTML = proposal ? `${proposal.ground_band_verified ? `<div class="notice success">${escapeHtml(t("verified"))}: ${escapeHtml(state.language === "ja" ? "連続GND帯のサンプリングを通過しました。" : "Continuous GND-band sampling passed.")}</div>` : ""}${(proposal.warnings || []).map((warning) => `<div class="notice">${escapeHtml(localizedEdgeWarning(warning))}</div>`).join("")}` : "";
  if (state.config?.edge) {
    document.getElementById("edgeGridInput").value = state.config.edge.grid_mm;
    document.getElementById("edgeFilletInput").value = state.config.edge.fillet_radius_mm;
  }
  renderEdgePreview();
  renderStitchingPlan();
  updateApplyButtons();
}

function localizedEdgeMode(mode) {
  if (state.language !== "ja") return mode || "";
  return { orthogonal: "直交線のみ", diagonal: "斜め線を許可", preserve_current: "現在外形を保持" }[mode] || mode || "";
}

function localizedEdgeStrategy(strategy) {
  if (state.language !== "ja") return strategy || "";
  return {
    convex: "凸多角形",
    convex_preserve_existing_concavities: "凸形状を基本に既存凹部だけ保持",
    legacy_concave: "従来の凹形状最適化",
  }[strategy] || strategy || "";
}

function localizedEdgeWarning(warning) {
  if (state.language !== "ja") return warning;
  const mappings = [
    [/uses (\d+) vertices instead of the requested (\d+)/, "安全条件を満たすため、要求頂点数ではなく実現可能な頂点数を使用しました。"],
    [/Preserved .* concave vertices/, "元のEdge.Cutsに存在した凹頂点だけを保持しました。"],
    [/convex safety fallback/, "凹部を安全に保持できなかったため、凸形状へ戻しました。"],
    [/maximum permitted area reduction/, "最大面積削減率を超えないよう外形を拡張しました。"],
    [/rounded corners remain outside/, "フィレット後も保護対象を切り込まないよう外形を外側へ調整しました。"],
    [/would increase board area/, "生成案が基板面積を増やすため、現在のEdge.Cutsを保持しました。"],
    [/continuous GND band could not be proven/, "提案外周の全周で連続GND帯を証明できないため、自動置換を遮断しました。"],
    [/Destructive Edge.Cuts replacement is disabled/, "破壊的なEdge.Cuts置換は既定で無効です。現在はプレビューのみです。"],
  ];
  return mappings.find(([pattern]) => pattern.test(warning))?.[1] || warning;
}

function proposalBounds(proposal) {
  const points = proposal?.polygon?.outline || [];
  if (!points.length) return null;
  return {
    min_x: Math.min(...points.map((point) => Number(point.x))),
    min_y: Math.min(...points.map((point) => Number(point.y))),
    max_x: Math.max(...points.map((point) => Number(point.x))),
    max_y: Math.max(...points.map((point) => Number(point.y))),
  };
}

function unionBounds(first, second) {
  if (!first) return second;
  if (!second) return first;
  return {
    min_x: Math.min(Number(first.min_x), Number(second.min_x)),
    min_y: Math.min(Number(first.min_y), Number(second.min_y)),
    max_x: Math.max(Number(first.max_x), Number(second.max_x)),
    max_y: Math.max(Number(first.max_y), Number(second.max_y)),
  };
}

function edgeProposalPath(proposal) {
  let pathData = "";
  for (const [index, primitive] of (proposal?.primitives || []).entries()) {
    if (index === 0) pathData += `M ${primitive.start.x} ${primitive.start.y} `;
    if (primitive.kind === "arc" && primitive.mid) pathData += `Q ${primitive.mid.x} ${primitive.mid.y} ${primitive.end.x} ${primitive.end.y} `;
    else pathData += `L ${primitive.end.x} ${primitive.end.y} `;
  }
  const points = proposal?.polygon?.outline || [];
  return pathData || (points.length ? `M ${points.map((point) => `${point.x} ${point.y}`).join(" L ")} Z` : "");
}

function renderEdgePreview() {
  const svg = document.getElementById("edgePreview");
  svg.replaceChildren();
  const empty = document.getElementById("edgePreviewEmpty");
  const proposal = state.edgeProposal;
  if (!state.preview?.bounds && !proposal?.polygon?.outline?.length) { empty.classList.remove("hidden"); return; }
  empty.classList.toggle("hidden", Boolean(proposal?.polygon?.outline?.length || state.stitchingPlan?.candidates?.length));
  const bounds = unionBounds(state.preview?.bounds, proposalBounds(proposal));
  const base = previewBounds(bounds);
  const previousBase = state.previewViews.edgePreview?.base;
  if (!state.previewViews.edgePreview || !previousBase || Math.abs(previousBase.width - base.width) > 1.0e-6 || Math.abs(previousBase.height - base.height) > 1.0e-6) {
    state.previewViews.edgePreview = { base: { ...base }, view: { ...base } };
  }
  setPreviewView("edgePreview", state.previewViews.edgePreview.view);
  const fragment = document.createDocumentFragment();
  appendPreviewGeometry(fragment, { stitching: true });
  if (proposal && isLayerVisible("Edge Proposal")) {
    const pathData = edgeProposalPath(proposal);
    if (pathData) fragment.appendChild(svgElement("path", { d: pathData, class: "proposal-line", "data-layer": "Edge Proposal" }));
  }
  svg.appendChild(fragment);
  renderLayerToggles("edgeLayerToggles", { edge: true, stitching: true });
  bindPreviewInteraction("edgePreview");
}

function renderStitchingPlan() {
  const plan = state.stitchingPlan;
  syncPlanSelection("stitching", plan?.candidates || [], "candidate_id");
  const selected = (plan?.candidates || []).filter((item) => state.selectedStitchingIds.has(item.candidate_id));
  const summary = document.getElementById("stitchingSummary");
  if (summary) {
    summary.innerHTML = plan ? `<span>${escapeHtml(t("selectedCount"))}: <strong>${selected.length}</strong></span><span>${escapeHtml(t("vertexCount"))}: <strong>${Number(plan.summary?.vertex_candidate_count || 0)}</strong></span><span>${escapeHtml(t("removableVias"))}: <strong>${Number(plan.summary?.removable_count || 0)}</strong></span><span>${escapeHtml(plan.net || "")}</span>` : "";
  }
  const body = document.getElementById("stitchingTableBody");
  if (!body) return;
  if (!plan?.candidates?.length) {
    body.innerHTML = `<tr><td colspan="6" class="table-empty">${escapeHtml(t("noStitchingPlan"))}</td></tr>`;
  } else {
    body.innerHTML = plan.candidates.map((item) => `<tr class="${state.selectedStitchingIds.has(item.candidate_id) ? "row-selected" : "row-unselected"}"><td><input type="checkbox" data-stitching-select="${escapeHtml(item.candidate_id)}" ${state.selectedStitchingIds.has(item.candidate_id) ? "checked" : ""}></td><td><code>${escapeHtml(item.candidate_id)}</code></td><td>${Number(item.position.x).toFixed(2)}</td><td>${Number(item.position.y).toFixed(2)}</td><td>${escapeHtml(item.critical_vertex ? (state.language === "ja" ? "頂点優先" : "Vertex priority") : item.source)}</td><td>${Math.round(Number(item.confidence) * 100)}%</td></tr>`).join("");
  }
  body.querySelectorAll("[data-stitching-select]").forEach((checkbox) => checkbox.addEventListener("change", () => {
    const id = checkbox.dataset.stitchingSelect;
    if (checkbox.checked) state.selectedStitchingIds.add(id); else state.selectedStitchingIds.delete(id);
    renderStitchingPlan();
  }));
  renderEdgePreview();
  updateApplyButtons();
}

function renderPlacementPlan() {
  const plan = state.placementPlan;
  syncPlanSelection("placement", plan?.placements || [], "placement_id");
  document.getElementById("placementGroupCount").textContent = plan ? Number(plan.summary?.group_count || 0) : "—";
  document.getElementById("placementCount").textContent = plan ? Number(plan.summary?.placement_count || 0) : "—";
  document.getElementById("placementCapacitorCount").textContent = plan ? Number(plan.summary?.capacitor_count || 0) : "—";
  const body = document.getElementById("placementTableBody");
  if (!plan?.placements?.length) {
    body.innerHTML = `<tr><td colspan="6" class="table-empty">${escapeHtml(t("noPlacementPlan"))}</td></tr>`;
  } else {
    body.innerHTML = plan.placements.map((item) => `<tr class="${state.selectedPlacementIds.has(item.placement_id) ? "row-selected" : "row-unselected"}"><td><input type="checkbox" data-placement-select="${escapeHtml(item.placement_id)}" ${state.selectedPlacementIds.has(item.placement_id) ? "checked" : ""} ${item.locked ? "disabled" : ""}></td><td>${escapeHtml(item.reference)}</td><td>${escapeHtml(item.group_id)}</td><td>${escapeHtml(localizedPlacementReason(item.reason))}</td><td>${Number(item.position.x).toFixed(2)}</td><td>${Number(item.position.y).toFixed(2)}</td></tr>`).join("");
  }
  body.querySelectorAll("[data-placement-select]").forEach((checkbox) => checkbox.addEventListener("change", () => {
    const id = checkbox.dataset.placementSelect;
    if (checkbox.checked) state.selectedPlacementIds.add(id); else state.selectedPlacementIds.delete(id);
    renderPlacementPlan();
  }));
  renderInteractivePreview("placementPreview", "placementPreviewEmpty", "placementLayerToggles", { placement: true });
  updateApplyButtons();
}

function localizedPlacementReason(reason) {
  if (state.language !== "ja") return reason || "";
  const labels = {
    locked_preserved: "ロック済みのため現在位置を保持",
    connector_at_block_perimeter: "コネクタを回路ブロック外周へ配置",
    core_component: "主要部品を大きさ順に配置",
    capacitor_near_matching_pad: "対応する電源パッド近傍へコンデンサを配置",
    capacitor_near_block_core: "主要部品近傍へコンデンサを配置",
    capacitor_fallback_row: "関連パッドを特定できないためブロック内の予備列へ配置",
    unclassified_preserved: "分類根拠が不足しているため現在位置を保持",
  };
  return labels[reason] || reason || "";
}

function renderQuantitative() {
  const quantitative = state.analysis?.quantitative;
  const cards = document.getElementById("quantitativeCards");
  const json = document.getElementById("quantitativeJson");
  if (!quantitative) {
    cards.innerHTML = "";
    json.textContent = "Run a scan to calculate estimates.";
    return;
  }
  const summaries = flattenNumeric(quantitative).slice(0, 8);
  cards.innerHTML = summaries.map(([key, value]) => `<article class="metric-card"><span>${escapeHtml(humanize(key))}</span><strong>${formatMetric(value)}</strong></article>`).join("");
  json.textContent = JSON.stringify(quantitative, null, 2);
}

function flattenNumeric(value, prefix = "") {
  const output = [];
  if (!value || typeof value !== "object") return output;
  for (const [key, child] of Object.entries(value)) {
    const name = prefix ? `${prefix}.${key}` : key;
    if (typeof child === "number" && Number.isFinite(child)) output.push([name, child]);
    else if (child && typeof child === "object" && !Array.isArray(child)) output.push(...flattenNumeric(child, name));
  }
  return output;
}

function humanize(value) {
  return value.split(".").at(-1).replaceAll("_", " ");
}

function formatMetric(value) {
  const absolute = Math.abs(Number(value));
  if (absolute >= 1000) return Number(value).toFixed(0);
  if (absolute >= 10) return Number(value).toFixed(1);
  return Number(value).toFixed(3);
}

function manufacturingProfileById(profileId) {
  return state.manufacturingCatalog?.profiles?.find((item) => item.profile_id === profileId) || null;
}

function manufacturingViaPresetById(presetId) {
  return state.manufacturingCatalog?.via_presets?.find((item) => item.preset_id === presetId) || null;
}

function replaceSelectOptions(element, values, selectedValue, labelFunction = (value) => String(value)) {
  if (!element) return;
  element.innerHTML = values.map((value) => {
    const raw = typeof value === "object" ? value.value : value;
    const label = typeof value === "object" ? value.label : labelFunction(value);
    return `<option value="${escapeHtml(raw)}"${String(raw) === String(selectedValue) ? " selected" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
}

function loadManufacturingControls(preserveCurrent = false) {
  const catalog = state.manufacturingCatalog;
  const selected = state.config?.manufacturing || catalog?.selected;
  if (!catalog || !selected) return;

  const previous = preserveCurrent ? {
    profile: document.getElementById("mfgProfileSelect").value,
    thickness: document.getElementById("mfgThicknessSelect").value,
    mask: document.getElementById("mfgMaskColorSelect").value,
    copper: document.getElementById("mfgCopperSelect").value,
    finish: document.getElementById("mfgFinishSelect").value,
    separation: document.getElementById("mfgSeparationSelect").value,
    tracks: [...document.querySelectorAll("#mfgTrackPresetGrid .preset-button.active")].map((button) => Number(button.dataset.value)),
    vias: [...document.querySelectorAll("#mfgViaPresetGrid .via-card.active")].map((button) => button.dataset.presetId),
  } : {};

  const profileId = previous.profile || selected.profile_id;
  replaceSelectOptions(
    document.getElementById("mfgProfileSelect"),
    catalog.profiles.map((item) => ({
      value: item.profile_id,
      label: state.language === "ja" ? item.name_ja : item.name_en,
    })),
    profileId,
  );
  replaceSelectOptions(
    document.getElementById("mfgThicknessSelect"),
    catalog.board_thicknesses_mm,
    previous.thickness || selected.board_thickness_mm,
    (value) => Number(value).toFixed(1),
  );
  replaceSelectOptions(
    document.getElementById("mfgMaskColorSelect"),
    catalog.solder_mask_colors,
    previous.mask || selected.solder_mask_color,
    localizedManufacturingOption,
  );
  replaceSelectOptions(
    document.getElementById("mfgCopperSelect"),
    catalog.copper_weights_oz,
    previous.copper || selected.copper_weight_oz,
    (value) => String(Number(value)),
  );
  replaceSelectOptions(
    document.getElementById("mfgFinishSelect"),
    catalog.surface_finishes,
    previous.finish || selected.surface_finish,
    localizedManufacturingOption,
  );
  replaceSelectOptions(
    document.getElementById("mfgSeparationSelect"),
    catalog.board_separation_methods,
    previous.separation || selected.board_separation,
    localizedManufacturingOption,
  );

  const selectedTracks = new Set((previous.tracks?.length ? previous.tracks : (selected.selected_track_widths_mm || [selected.selected_track_width_mm])).map(Number));
  document.getElementById("mfgTrackPresetGrid").innerHTML = catalog.track_width_presets_mm.map((width) => {
    const active = [...selectedTracks].some((selectedWidth) => Math.abs(Number(width) - selectedWidth) < 1e-9);
    return `<button type="button" class="preset-button${active ? " active" : ""}" aria-pressed="${active}" data-value="${Number(width)}">${Number(width).toFixed(1)}</button>`;
  }).join("");

  const selectedVias = new Set(previous.vias?.length ? previous.vias : (selected.selected_via_preset_ids || [selected.selected_via_preset_id]));
  document.getElementById("mfgViaPresetGrid").innerHTML = catalog.via_presets.map((preset) => {
    const name = state.language === "ja" ? preset.name_ja : preset.name_en;
    const description = state.language === "ja" ? preset.description_ja : preset.description_en;
    const risk = preset.surcharge_risk ? `<span class="cost-risk">${state.language === "ja" ? "追加料金リスク" : "Cost risk"}</span>` : "";
    return `<button type="button" class="via-card${selectedVias.has(preset.preset_id) ? " active" : ""}" aria-pressed="${selectedVias.has(preset.preset_id)}" data-preset-id="${escapeHtml(preset.preset_id)}"><strong>${escapeHtml(name)}</strong><span class="via-geometry">Ø${Number(preset.diameter_mm).toFixed(2)} / ${Number(preset.drill_mm).toFixed(2)} mm</span><small>${escapeHtml(description)} ${risk}</small></button>`;
  }).join("");
  document.getElementById("mfgApplySilk").checked = Boolean(selected.apply_profile_to_silkscreen);
  renderManufacturingSelection();
}

function localizedManufacturingOption(value) {
  const raw = String(value);
  const ja = {
    green: "緑", purple: "紫", red: "赤", yellow: "黄", blue: "青", white: "白", black: "黒",
    hasl_leaded: "有鉛HASL", hasl_lead_free: "鉛フリーHASL", enig: "ENIG（金メッキ）",
    routing: "ルーター", v_cut: "Vカット",
  };
  const en = {
    green: "Green", purple: "Purple", red: "Red", yellow: "Yellow", blue: "Blue", white: "White", black: "Black",
    hasl_leaded: "Leaded HASL", hasl_lead_free: "Lead-free HASL", enig: "ENIG",
    routing: "Routing", v_cut: "V-cut",
  };
  return (state.language === "ja" ? ja : en)[raw] || raw;
}

function renderManufacturingSelection() {
  const catalog = state.manufacturingCatalog;
  if (!catalog) return;
  const profileId = document.getElementById("mfgProfileSelect").value || state.config?.manufacturing?.profile_id;
  const profile = manufacturingProfileById(profileId);
  if (profile) {
    const name = state.language === "ja" ? profile.name_ja : profile.name_en;
    const intent = state.language === "ja" ? profile.intent_ja : profile.intent_en;
    const warning = state.language === "ja" ? profile.cost_warning_ja : profile.cost_warning_en;
    document.getElementById("mfgProfileDescription").innerHTML = `<strong>${escapeHtml(name)}</strong>${escapeHtml(intent)}<br><small>${escapeHtml(warning)}</small>`;
  }
  const color = document.getElementById("mfgMaskColorSelect").value || "green";
  const colorMap = { green: "#178744", purple: "#7141a8", red: "#b22b35", yellow: "#d6af18", blue: "#235ba7", white: "#f4f4ef", black: "#1f2326" };
  document.getElementById("mfgColorSwatch").style.background = colorMap[color] || color;
  document.getElementById("mfgColorName").textContent = localizedManufacturingOption(color);
}

function selectManufacturingProfileDefaults(profileId) {
  const profile = manufacturingProfileById(profileId);
  if (!profile) return;
  document.getElementById("mfgThicknessSelect").value = String(profile.default_board_thickness_mm);
  document.getElementById("mfgMaskColorSelect").value = profile.default_solder_mask_color;
  document.getElementById("mfgCopperSelect").value = String(profile.default_copper_weight_oz);
  document.getElementById("mfgFinishSelect").value = profile.default_surface_finish;
  document.querySelectorAll("#mfgTrackPresetGrid .preset-button").forEach((button) => {
    button.classList.toggle("active", Math.abs(Number(button.dataset.value) - Number(profile.default_track_width_mm)) < 1e-9);
  });
  document.querySelectorAll("#mfgViaPresetGrid .via-card").forEach((button) => {
    button.classList.toggle("active", button.dataset.presetId === profile.default_via_preset_id);
  });
  renderManufacturingSelection();
}

function selectedManufacturingTrackWidths() {
  const selected = [...document.querySelectorAll("#mfgTrackPresetGrid .preset-button.active")]
    .map((button) => Number(button.dataset.value))
    .filter((value) => Number.isFinite(value) && value > 0)
    .sort((left, right) => left - right);
  return selected.length ? selected : [Number(state.config?.manufacturing?.selected_track_width_mm || 0.2)];
}

function selectedManufacturingTrackWidth() {
  return selectedManufacturingTrackWidths()[0];
}

function selectedManufacturingViaPresets() {
  const selected = [...document.querySelectorAll("#mfgViaPresetGrid .via-card.active")]
    .map((button) => button.dataset.presetId)
    .filter(Boolean);
  return selected.length ? selected : [state.config?.manufacturing?.selected_via_preset_id || "kicad_default"];
}

function selectedManufacturingViaPreset() {
  return selectedManufacturingViaPresets()[0];
}

function renderManufacturing() {
  const config = state.config?.manufacturing;
  const report = state.manufacturingReport;
  if (config) {
    document.getElementById("mfgOrderSummary").textContent = `${config.layer_count}L · ${Number(config.board_thickness_mm).toFixed(1)} mm`;
    document.getElementById("mfgColorSummary").textContent = `${localizedManufacturingOption(config.solder_mask_color)} · ${Number(config.copper_weight_oz).toFixed(1)} oz`;
    document.getElementById("mfgVerifiedBadge").textContent = `${state.language === "ja" ? "確認日" : "Verified"}: ${config.verified_date}`;
    const constraints = [
      [state.language === "ja" ? "最小配線幅" : "Min track", config.minimum_track_width_mm, "mm"],
      [state.language === "ja" ? "最小クリアランス" : "Min clearance", config.minimum_clearance_mm, "mm"],
      [state.language === "ja" ? "最小ビア径" : "Min via diameter", config.minimum_via_diameter_mm, "mm"],
      [state.language === "ja" ? "最小ビア穴" : "Min via drill", config.minimum_via_drill_mm, "mm"],
      [state.language === "ja" ? "穴間隔" : "Hole spacing", config.minimum_hole_to_hole_mm, "mm"],
      [state.language === "ja" ? "ビア・配線間隔" : "Via-to-track", config.minimum_via_to_track_mm, "mm"],
      [state.language === "ja" ? "銅箔・基板端" : "Copper-to-edge", config.board_separation === "v_cut" ? config.minimum_copper_to_v_cut_mm : config.minimum_copper_to_routed_edge_mm, "mm"],
      [state.language === "ja" ? "シルク線幅" : "Silk line", config.minimum_silkscreen_line_width_mm, "mm"],
      [state.language === "ja" ? "シルク文字高さ" : "Silk height", config.minimum_silkscreen_text_height_mm, "mm"],
      [state.language === "ja" ? "マスクブリッジ" : "Mask bridge", config.minimum_solder_mask_bridge_mm, "mm"],
    ];
    document.getElementById("mfgConstraintGrid").innerHTML = constraints.map(([label, value, unit]) => `<div class="constraint-card"><span>${escapeHtml(label)}</span><strong>${Number(value).toFixed(3)} ${unit}</strong></div>`).join("");
  }

  const statistics = report?.statistics || {};
  document.getElementById("mfgScore").textContent = report ? Number(report.score).toFixed(1) : "—";
  document.getElementById("mfgStatus").textContent = report ? localizedManufacturingStatus(report.status) : t("notScanned");
  document.getElementById("mfgErrorCount").textContent = report ? Number(statistics.error_count || 0) : "—";
  document.getElementById("mfgWarningCount").textContent = report ? Number(statistics.warning_count || 0) : "—";
  renderManufacturingIssues();
  renderManufacturingSelection();
}

function localizedManufacturingStatus(status) {
  const values = state.language === "ja" ? { pass: "合格", review: "要確認", fail: "不適合" } : { pass: "Pass", review: "Review", fail: "Fail" };
  return values[status] || status;
}

function renderManufacturingIssues() {
  const body = document.getElementById("mfgIssueTableBody");
  const filter = document.getElementById("mfgSeverityFilter").value;
  const issues = (state.manufacturingReport?.issues || []).filter((item) => filter === "all" || item.severity === filter);
  if (!state.manufacturingReport) {
    body.innerHTML = `<tr><td colspan="6" class="table-empty">${escapeHtml(t("mfgNoReport"))}</td></tr>`;
    return;
  }
  if (!issues.length) {
    body.innerHTML = `<tr><td colspan="6" class="table-empty">${escapeHtml(state.language === "ja" ? "該当する指摘はありません。" : "No matching issues.")}</td></tr>`;
    return;
  }
  body.innerHTML = issues.map((issue) => {
    const measured = issue.measured === null || issue.measured === undefined ? "—" : String(issue.measured);
    const limit = issue.limit === null || issue.limit === undefined ? "—" : String(issue.limit);
    const localized = issue?.localized?.[state.language] || issue?.localized?.en || {};
    const title = localized.title || issue.title;
    const description = localized.description || issue.description;
    const recommendation = localized.recommendation || issue.recommendation;
    return `<tr><td><span class="severity-chip ${escapeHtml(issue.severity)}">${escapeHtml(issue.severity)}</span></td><td><code>${escapeHtml(issue.code)}</code></td><td>${escapeHtml(issue.category)}</td><td><strong>${escapeHtml(title)}</strong><br><span class="muted">${escapeHtml(description)}</span></td><td>${escapeHtml(measured)} / ${escapeHtml(limit)} ${escapeHtml(issue.unit || "")}</td><td>${escapeHtml(recommendation)}</td></tr>`;
  }).join("");
}


function renderAll() {
  renderStatus();
  renderDashboard();
  renderFixPlan();
  renderSilkPlan();
  renderEdgeProposal();
  renderPlacementPlan();
  renderManufacturing();
  renderQuantitative();
}

function getAtPath(object, path) {
  return path.split(".").reduce((current, key) => current?.[key], object);
}

function setAtPath(object, path, value) {
  const parts = path.split(".");
  let current = object;
  parts.slice(0, -1).forEach((key) => {
    if (!current[key] || typeof current[key] !== "object") current[key] = {};
    current = current[key];
  });
  current[parts.at(-1)] = value;
}

function loadConfigIntoForm() {
  if (!state.config) return;
  document.querySelectorAll("[data-config]").forEach((input) => {
    const value = getAtPath(state.config, input.dataset.config);
    if (input.type === "checkbox") input.checked = Boolean(value);
    else input.value = value ?? "";
  });
  synchronizeEdgeModeControls();
  document.getElementById("configJson").value = JSON.stringify(state.config, null, 2);
}

function synchronizeEdgeModeControls() {
  const mode = document.querySelector('[data-config="edge.mode"]');
  const allowDiagonal = document.querySelector('[data-config="edge.allow_diagonal_edges"]');
  if (!mode || !allowDiagonal) return;
  if (mode.value === "diagonal") {
    allowDiagonal.checked = true;
    allowDiagonal.disabled = true;
  } else {
    allowDiagonal.disabled = false;
  }
}

function collectConfigFromForm() {
  let draft;
  try {
    draft = JSON.parse(document.getElementById("configJson").value || "{}");
  } catch (error) {
    throw new Error(`Invalid configuration JSON: ${error.message}`);
  }
  document.querySelectorAll("[data-config]").forEach((input) => {
    const existing = getAtPath(draft, input.dataset.config);
    let value;
    if (input.type === "checkbox") value = input.checked;
    else if (typeof existing === "number" || input.type === "number") {
      value = Number(input.value);
      if (!Number.isFinite(value)) throw new Error(`${input.dataset.config} must be a number.`);
    } else value = input.value;
    setAtPath(draft, input.dataset.config, value);
  });
  return draft;
}

function updateApplyButtons() {
  const writable = state.config && !state.config.fixes.dry_run;
  const fixEnabled = writable && state.selectedFixIds.size > 0 && document.getElementById("fixConfirm").checked;
  document.getElementById("applyFixesButton").disabled = !fixEnabled;
  const silkEnabled = writable && state.selectedSilkIds.size > 0 && document.getElementById("silkConfirm").checked;
  document.getElementById("applySilkButton").disabled = !silkEnabled;
  const activeBoard = state.status?.board?.name || "";
  const edgeEnabled = writable && Boolean(state.edgeProposal?.ground_band_verified) && Boolean(state.config?.edge?.allow_destructive_edge_replacement) && document.getElementById("edgeConfirm").checked && document.getElementById("edgeBoardConfirm").value === activeBoard;
  document.getElementById("applyEdgeButton").disabled = !edgeEnabled;
  const stitchingEnabled = writable && state.selectedStitchingIds.size > 0 && document.getElementById("stitchingConfirm").checked;
  document.getElementById("applyStitchingButton").disabled = !stitchingEnabled;
  const placementEnabled = writable && !state.config?.placement?.dry_run_only && state.selectedPlacementIds.size > 0 && document.getElementById("placementConfirm").checked;
  document.getElementById("applyPlacementButton").disabled = !placementEnabled;
}

async function runOperation(button, callback, successMessage) {
  clearBanner();
  setBusy(button, true);
  try {
    const result = await callback();
    if (successMessage) showToast(successMessage, "success");
    return result;
  } catch (error) {
    showToast(error.message, "error", 8000);
    showBanner(error.message, "error");
    throw error;
  } finally {
    setBusy(button, false);
    updateApplyButtons();
  }
}

function replaceSelection(setName, values) {
  state[setName] = new Set(values.map((value) => String(value)));
}

async function saveEdgeQuickSettings() {
  const grid = Number(document.getElementById("edgeGridInput").value || state.config?.edge?.grid_mm || 0.5);
  const fillet = Number(document.getElementById("edgeFilletInput").value || state.config?.edge?.fillet_radius_mm || 1.0);
  const mode = state.config?.edge?.mode || "diagonal";
  const patch = {
    edge: {
      grid_mm: grid,
      fillet_radius_mm: fillet,
      mode,
      allow_diagonal_edges: mode === "diagonal" ? true : Boolean(state.config?.edge?.allow_diagonal_edges),
    },
  };
  state.config = await api("/api/config", { method: "POST", body: patch });
  loadConfigIntoForm();
}

async function planEdgeOperation(button, operation) {
  await saveEdgeQuickSettings();
  state.edgeProposal = await runOperation(
    button,
    () => api("/api/edge/plan", { method: "POST", body: { operation } }),
    t("planningComplete"),
  );
  state.stitchingPlan = null;
  state.selectionKeys.stitching = "";
  delete state.previewViews.edgePreview;
  renderEdgeProposal();
}

function bindActions() {
  document.getElementById("languageButton").addEventListener("click", () => {
    state.language = state.language === "ja" ? "en" : "ja";
    applyTranslations();
  });
  document.getElementById("severityFilter").addEventListener("change", renderFindings);
  document.getElementById("categoryFilter").addEventListener("change", renderFindings);
  document.getElementById("mfgSeverityFilter").addEventListener("change", renderManufacturingIssues);
  document.getElementById("mfgProfileSelect").addEventListener("change", (event) => selectManufacturingProfileDefaults(event.target.value));
  document.getElementById("mfgMaskColorSelect").addEventListener("change", renderManufacturingSelection);
  const edgeModeControl = document.querySelector('[data-config="edge.mode"]');
  if (edgeModeControl) edgeModeControl.addEventListener("change", synchronizeEdgeModeControls);
  synchronizeEdgeModeControls();
  document.getElementById("mfgTrackPresetGrid").addEventListener("click", (event) => {
    const button = event.target.closest(".preset-button");
    if (!button) return;
    const activeCount = document.querySelectorAll("#mfgTrackPresetGrid .preset-button.active").length;
    if (button.classList.contains("active") && activeCount === 1) {
      showToast(t("atLeastOnePreset"), "error");
      return;
    }
    button.classList.toggle("active");
    button.setAttribute("aria-pressed", String(button.classList.contains("active")));
  });
  document.getElementById("mfgViaPresetGrid").addEventListener("click", (event) => {
    const button = event.target.closest(".via-card");
    if (!button) return;
    const activeCount = document.querySelectorAll("#mfgViaPresetGrid .via-card.active").length;
    if (button.classList.contains("active") && activeCount === 1) {
      showToast(t("atLeastOnePreset"), "error");
      return;
    }
    button.classList.toggle("active");
    button.setAttribute("aria-pressed", String(button.classList.contains("active")));
  });
  document.getElementById("modalClose").addEventListener("click", () => document.getElementById("detailsModal").classList.add("hidden"));
  document.getElementById("detailsModal").addEventListener("click", (event) => {
    if (event.target.id === "detailsModal") event.currentTarget.classList.add("hidden");
  });
  document.getElementById("locateFindingButton").addEventListener("click", async (event) => {
    await locateFinding(event.currentTarget.dataset.findingId, event.currentTarget);
  });
  document.getElementById("previewLocateFindingButton").addEventListener("click", (event) => {
    const id = event.currentTarget.dataset.findingId;
    document.getElementById("detailsModal").classList.add("hidden");
    focusFindingInPreview(id);
  });
  document.querySelectorAll("[data-preview-action]").forEach((button) => button.addEventListener("click", () => {
    const target = button.dataset.previewTarget;
    const action = button.dataset.previewAction;
    if (action === "fit") fitPreview(target);
    else if (action === "zoom-in") zoomPreview(target, 0.78);
    else if (action === "zoom-out") zoomPreview(target, 1.28);
  }));
  ["fixConfirm", "silkConfirm", "edgeConfirm", "edgeBoardConfirm", "stitchingConfirm", "placementConfirm"].forEach((id) => document.getElementById(id).addEventListener("input", updateApplyButtons));
  document.getElementById("selectAllFixesButton").addEventListener("click", () => {
    replaceSelection("selectedFixIds", (state.fixPlan?.actions || []).map((item) => item.action_id));
    renderFixPlan();
  });
  document.getElementById("clearFixesButton").addEventListener("click", () => {
    replaceSelection("selectedFixIds", []);
    renderFixPlan();
  });
  document.getElementById("selectAllSilkButton").addEventListener("click", () => {
    replaceSelection("selectedSilkIds", (state.silkPlan?.placements || []).filter((item) => !item.manual_review).map((item) => item.placement_id));
    renderSilkPlan();
  });
  document.getElementById("clearSilkButton").addEventListener("click", () => {
    replaceSelection("selectedSilkIds", []);
    renderSilkPlan();
  });
  document.getElementById("selectAllPlacementButton").addEventListener("click", () => {
    replaceSelection("selectedPlacementIds", (state.placementPlan?.placements || []).filter((item) => !item.locked).map((item) => item.placement_id));
    renderPlacementPlan();
  });
  document.getElementById("clearPlacementButton").addEventListener("click", () => {
    replaceSelection("selectedPlacementIds", []);
    renderPlacementPlan();
  });

  document.getElementById("scanButton").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const data = await runOperation(button, () => api("/api/analyze", { method: "POST", body: { refresh: true } }), t("scanComplete"));
    state.analysis = data.analysis;
    state.preview = data.preview;
    state.fixPlan = null;
    state.silkPlan = null;
    state.edgeProposal = null;
    state.stitchingPlan = null;
    state.placementPlan = null;
    state.selectionKeys = { fixes: "", silk: "", stitching: "", placement: "" };
    state.manufacturingReport = data.manufacturing || null;
    state.previewViews = {};
    renderAll();
  });

  document.getElementById("planFixesButton").addEventListener("click", async (event) => {
    state.fixPlan = await runOperation(event.currentTarget, () => api("/api/fixes/plan", { method: "POST" }), t("planningComplete"));
    renderFixPlan();
  });
  document.getElementById("applyFixesButton").addEventListener("click", async (event) => {
    const data = await runOperation(event.currentTarget, () => api("/api/fixes/apply", { method: "POST", body: { confirmed: true, action_ids: [...state.selectedFixIds] } }), t("changesApplied"));
    state.analysis = data.analysis; state.preview = data.preview; state.manufacturingReport = data.manufacturing || null; state.fixPlan = null; document.getElementById("fixConfirm").checked = false; renderAll();
  });

  document.getElementById("planSilkButton").addEventListener("click", async (event) => {
    state.silkPlan = await runOperation(event.currentTarget, () => api("/api/silkscreen/plan", { method: "POST" }), t("planningComplete"));
    renderSilkPlan();
  });
  document.getElementById("applySilkButton").addEventListener("click", async (event) => {
    const data = await runOperation(event.currentTarget, () => api("/api/silkscreen/apply", { method: "POST", body: { confirmed: true, placement_ids: [...state.selectedSilkIds] } }), t("changesApplied"));
    state.analysis = data.analysis; state.preview = data.preview; state.manufacturingReport = data.manufacturing || null; state.silkPlan = null; document.getElementById("silkConfirm").checked = false; renderAll();
  });

  document.querySelectorAll("[data-edge-operation]").forEach((button) => button.addEventListener("click", async (event) => {
    await planEdgeOperation(event.currentTarget, event.currentTarget.dataset.edgeOperation);
  }));
  document.getElementById("applyEdgeButton").addEventListener("click", async (event) => {
    const data = await runOperation(event.currentTarget, () => api("/api/edge/apply", { method: "POST", body: { confirmed: true, board_name: document.getElementById("edgeBoardConfirm").value } }), t("changesApplied"));
    state.analysis = data.analysis; state.preview = data.preview; state.manufacturingReport = data.manufacturing || null; state.edgeProposal = null; document.getElementById("edgeConfirm").checked = false; document.getElementById("edgeBoardConfirm").value = ""; renderAll();
  });

  document.getElementById("planStitchingButton").addEventListener("click", async (event) => {
    state.stitchingPlan = await runOperation(event.currentTarget, () => api("/api/stitching/plan", { method: "POST", body: { rebuild_perimeter: document.getElementById("rebuildPerimeterVias").checked, use_edge_proposal: true } }), t("planningComplete"));
    state.selectionKeys.stitching = "";
    renderStitchingPlan();
  });
  document.getElementById("applyStitchingButton").addEventListener("click", async (event) => {
    const data = await runOperation(event.currentTarget, () => api("/api/stitching/apply", { method: "POST", body: { confirmed: true, candidate_ids: [...state.selectedStitchingIds], rebuild_perimeter: document.getElementById("rebuildPerimeterVias").checked } }), t("changesApplied"));
    state.analysis = data.analysis; state.preview = data.preview; state.manufacturingReport = data.manufacturing || null; state.stitchingPlan = null; state.selectionKeys.stitching = ""; document.getElementById("stitchingConfirm").checked = false; renderAll();
  });

  document.getElementById("planPlacementButton").addEventListener("click", async (event) => {
    state.placementPlan = await runOperation(event.currentTarget, () => api("/api/placement/plan", { method: "POST" }), t("planningComplete"));
    state.selectionKeys.placement = "";
    delete state.previewViews.placementPreview;
    renderPlacementPlan();
  });
  document.getElementById("applyPlacementButton").addEventListener("click", async (event) => {
    const data = await runOperation(event.currentTarget, () => api("/api/placement/apply", { method: "POST", body: { confirmed: true, placement_ids: [...state.selectedPlacementIds] } }), t("changesApplied"));
    state.analysis = data.analysis; state.preview = data.preview; state.manufacturingReport = data.manufacturing || null; state.placementPlan = null; state.selectionKeys.placement = ""; document.getElementById("placementConfirm").checked = false; renderAll();
  });

  document.getElementById("applyManufacturingProfileButton").addEventListener("click", async (event) => {
    const payload = {
      profile_id: document.getElementById("mfgProfileSelect").value,
      board_thickness_mm: Number(document.getElementById("mfgThicknessSelect").value),
      solder_mask_color: document.getElementById("mfgMaskColorSelect").value,
      copper_weight_oz: Number(document.getElementById("mfgCopperSelect").value),
      surface_finish: document.getElementById("mfgFinishSelect").value,
      board_separation: document.getElementById("mfgSeparationSelect").value,
      track_width_mm: selectedManufacturingTrackWidth(),
      track_widths_mm: selectedManufacturingTrackWidths(),
      via_preset_id: selectedManufacturingViaPreset(),
      via_preset_ids: selectedManufacturingViaPresets(),
      apply_silkscreen_limits: document.getElementById("mfgApplySilk").checked,
    };
    const data = await runOperation(event.currentTarget, () => api("/api/manufacturing/profile", { method: "POST", body: payload }), t("mfgProfileApplied"));
    state.config = data.config;
    state.manufacturingCatalog = data.catalog;
    state.manufacturingReport = data.report;
    state.fixPlan = null; state.silkPlan = null; state.edgeProposal = null; state.stitchingPlan = null; state.placementPlan = null;
    loadConfigIntoForm(); loadManufacturingControls(false); renderAll();
  });
  document.getElementById("checkManufacturingButton").addEventListener("click", async (event) => {
    state.manufacturingReport = await runOperation(event.currentTarget, () => api("/api/manufacturing/check", { method: "POST", body: { refresh: true } }), t("mfgCheckComplete"));
    renderManufacturing();
  });
  document.getElementById("exportManufacturingButton").addEventListener("click", async (event) => {
    const paths = await runOperation(event.currentTarget, () => api("/api/manufacturing/export", { method: "POST" }), t("mfgBundleExported"));
    showToast(Object.values(paths).join("\n"), "success", 10000);
  });

  document.getElementById("exportReportButton").addEventListener("click", async (event) => {
    const paths = await runOperation(event.currentTarget, () => api("/api/report/export", { method: "POST" }), t("reportExported"));
    showToast(Object.values(paths).join("\n"), "success", 10000);
  });
  document.getElementById("exportSolverButton").addEventListener("click", async (event) => {
    const paths = await runOperation(event.currentTarget, () => api("/api/solver/export", { method: "POST" }), t("solverExported"));
    showToast(Object.values(paths).join("\n"), "success", 10000);
  });

  document.getElementById("saveConfigButton").addEventListener("click", async (event) => {
    const draft = collectConfigFromForm();
    state.config = await runOperation(event.currentTarget, () => api("/api/config", { method: "POST", body: draft }), t("settingsSaved"));
    state.fixPlan = null; state.silkPlan = null; state.edgeProposal = null; state.stitchingPlan = null; state.placementPlan = null; state.manufacturingReport = null;
    if (state.manufacturingCatalog) state.manufacturingCatalog.selected = state.config.manufacturing;
    loadConfigIntoForm(); loadManufacturingControls(false); renderAll(); startHeartbeat();
    document.getElementById("settingsState").textContent = new Date().toLocaleTimeString();
  });
  document.getElementById("resetConfigButton").addEventListener("click", loadConfigIntoForm);
}

async function heartbeat() {
  try {
    const result = await api("/api/ping");
    const wasDisconnected = state.status?.connection?.connected === false;
    if (!state.status) state.status = {};
    state.status.connection = { connected: result?.connected !== false, message: result?.message || "", reconnected: Boolean(result?.reconnected) };
    renderStatus();
    if (wasDisconnected && state.status.connection.connected) showToast(t("connectionRestored"), "success");
  } catch (error) {
    if (!state.status) state.status = {};
    const firstFailure = state.status.connection?.connected !== false;
    state.status.connection = { connected: false, message: error.message, reconnected: false };
    renderStatus();
    if (firstFailure) showToast(t("connectionLost"), "error", 8000);
  }
}

function startHeartbeat() {
  if (state.heartbeatTimer) window.clearInterval(state.heartbeatTimer);
  const seconds = Math.max(5, Number(state.config?.ui?.heartbeat_seconds || 20));
  state.heartbeatTimer = window.setInterval(heartbeat, seconds * 1000);
}

async function initialize() {
  initializeNavigation();
  bindActions();
  if (!sessionToken) {
    showBanner("Missing dashboard session token.", "error");
    return;
  }
  try {
    const [status, config, analysisData, fixPlan, silkPlan, edgeProposal, stitchingPlan, placementPlan, manufacturingCatalog, manufacturingReport] = await Promise.all([
      api("/api/status"), api("/api/config"), api("/api/analysis"), api("/api/fix-plan"), api("/api/silkscreen-plan"), api("/api/edge-proposal"), api("/api/stitching-plan"), api("/api/placement-plan"), api("/api/manufacturing/catalog"), api("/api/manufacturing/report"),
    ]);
    state.status = status;
    state.config = config;
    state.analysis = analysisData?.analysis || null;
    state.preview = analysisData?.preview || null;
    state.fixPlan = fixPlan;
    state.silkPlan = silkPlan;
    state.edgeProposal = edgeProposal;
    state.stitchingPlan = stitchingPlan;
    state.placementPlan = placementPlan;
    state.manufacturingCatalog = manufacturingCatalog;
    state.manufacturingReport = manufacturingReport || analysisData?.manufacturing || null;
    const configuredLanguage = config.ui?.language;
    state.language = configuredLanguage === "en" || configuredLanguage === "ja" ? configuredLanguage : (navigator.language.toLowerCase().startsWith("ja") ? "ja" : "en");
    loadConfigIntoForm();
    loadManufacturingControls(false);
    applyTranslations();
    renderAll();
    startHeartbeat();
  } catch (error) {
    showBanner(error.message, "error");
  }
}

window.addEventListener("DOMContentLoaded", initialize);
