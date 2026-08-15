# EMI Guardian for KiCad 10+

**EMI Guardian 0.0.2** is a bilingual IPC plugin for KiCad 10.0.5 and later. It combines geometry-based EMI screening, ranked ground-pour remediation, interactive board/fix/silkscreen previews, JLCPCB two-layer DFM checks, footprint-value silkscreen cleanup, and filleted board-outline proposals.

> EMI Guardian is an engineering screening and workflow-assistance tool. It is not an EMC compliance instrument, a proof that no EMI source exists, a JLCPCB quotation engine, or a manufacturing-acceptance guarantee. Review every finding and proposal, run KiCad DRC, inspect Gerbers, and confirm the live manufacturer quote and DFM result before fabrication.

## Version 0.0.2 highlights

- Uses a blue visual theme and provides complete Japanese or English finding titles, descriptions, evidence labels, and recommendations.
- Rebuilds GND-appendage detection around a protected geometry backbone: every pad area and launch margin is non-removable, while GND pads, vias, explicit traces, broad plane copper, and the existing perimeter band are connected with a configurable width-`t` protected corridor before any residual copper can be reported.
- Generates a rule area only from an exact connectivity-proven residual and repeats that proof against the current board before planning. It rejects stale or unproven keepouts and any polygon that touches a pad, mandatory GND corridor, explicit GND trace, protected perimeter GND, or leaves Edge.Cuts.
- Rejects new tracks and vias unless their complete copper geometry stays inside Edge.Cuts, including concavities and internal cutouts, and clears other-net filled zones as well as tracks, vias, and pads.
- Relaxes two-layer return-path findings with minimum route length, endpoint breakout exclusion, sustained missing-reference fraction, common power-net exclusion, and stricter GND-detour ratio/excess thresholds.
- Shows simplified `F.Cu`, `B.Cu`, `F.SilkS`, `B.SilkS`, pad, via, footprint, zone, edge, finding, fix, silkscreen, stitching, and placement layers in zoomable and pannable SVG previews. Finding markers remain visible when ordinary layers are hidden.
- Adds **Show location in KiCad**. It selects the evidence items, activates the relevant layer where supported, and requests a zoom-to-selection action. KiCad 10's public IPC does not expose stable custom DRC-marker creation, so this is deliberately non-destructive DRC-like navigation rather than a persistent DRC violation.
- Corrects corner scoring: ordinary 90-degree routing is not classified as a sharp corner by default; pad/via regions, complex junctions, short segments, and arc-approximation joints are excluded. The default acute threshold is 75 degrees.
- Corrects electrically-long-net screening by estimating the longest connected endpoint-to-endpoint route instead of summing every branch in a net.
- Prevents category scores from collapsing to exactly zero through unbounded linear penalty accumulation; category impact now uses bounded diminishing returns.
- Keeps the local dashboard alive by default, sends a KiCad heartbeat every 20 seconds, and retries stale IPC connections twice. Idle shutdown is disabled unless the user explicitly enables it.
- Makes track-width and via presets multi-select. The selected catalogue is preserved, while automatic repairs use a profile-compatible default.
- Defaults the outline optimizer to a convex support polygon with eight target vertices. It may preserve only concavities that already existed in the original Edge.Cuts and that pass safety checks.
- Adds self-contained install/update/uninstall packages for Windows, macOS, and Linux. Updates do not copy the previous plugin to any backup location, leave no backup under KiCad's plugin scan path, and remove legacy backup/staging directories.
- Adds GitHub-ready CI, release documentation, checksums, deterministic archives, and a complete source release.

## Core functions

- Detect narrow ground-pour appendages only outside the protected pad/via/track/perimeter GND backbone, and identify truly disconnected ground islands from combined zone/track/via/pad connectivity.
- Rank shape-matched copper-pour keepout rule areas, same-net GND bridges, stitching vias, and combined bridge-and-via actions. Tracks already covered by same-net fill are rejected as redundant.
- Score dangling stubs, parallel coupling, sharp corners, long/electrically long routes, missing return vias, edge-proximate signals, and differential-pair mismatch.
- Estimate microstrip/stripline impedance, propagation delay, critical length, quarter-wave resonance, skin depth, and a normalized crosstalk proxy.
- Reposition footprint values with a default **0.8 mm × 0.8 mm** text size and **0.10 mm** stroke while avoiding pads, vias, board edges, and existing text.
- Propose, smooth, or fillet orthogonal/diagonal board outlines on a selectable grid; reject area-increasing replacements; and preview optional safe perimeter-via rebuilding.
- Use KiCad's official IPC API through `kicad-python`, with API compatibility isolated in one adapter module.
- Default to dry-run; writes require explicit confirmation and an undo transaction where supported.
- Plan moderate-density GND via stitching with vertex-priority candidates and full-annulus copper/clearance checks.
- Produce a dry-run initial footprint placement grouped by schematic sheet path, keeping locked parts fixed and placing likely decoupling capacitors near matching power pads.

## JLCPCB two-layer profiles

The default **economy** profile uses two layers, 1.6 mm FR-4, green solder mask, white silkscreen, 1 oz outer copper, leaded HASL, a 0.20/0.20 mm design baseline, and a 0.60/0.30 mm automatic-fix via. The separate **capability-limit** profile exposes 0.10/0.10 mm routing and a 0.25/0.15 mm via for local dense escape routing, with explicit cost and process-margin warnings.

Track-width presets are **0.1, 0.2, 0.3, 0.4, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, and 5.0 mm**. Both requested via presets are included. Multiple choices can be retained as a routing catalogue; the automatic antenna-fix geometry remains compatible with the active manufacturing profile.

KiCad 10's public IPC is used to read the active board and available stackup information. EMI Guardian does not silently rewrite `.kicad_pcb` text to force board thickness, solder-mask color, or project design rules. It stores the selected order assumptions, compares them with readable KiCad data, and exports a reviewable `kicad_dru` template plus order records.

The bundled JLCPCB data was verified against public capability information on **2026-08-13**. Manufacturing capabilities and price rules can change; the live quote remains authoritative.

## Installation and launch

Use the package for your operating system:

- Windows: extract the Windows installer ZIP and run `Install-or-Update.cmd`.
- macOS: extract the macOS installer ZIP and run `install-or-update.command`.
- Linux: extract the Linux installer ZIP and run `./install-or-update.sh`.

Close KiCad before install, update, or uninstall. The scripts install for the current user and create **no installer backup** of the previous plugin, including in the operating-system temporary directory. The existing plugin is removed only after the new payload has been copied and checked in a temporary staging directory. If final placement fails, the incomplete destination is removed and the installer must be run again; automatic rollback is intentionally disabled. Legacy `_emi-guardian-backups` and stale staging directories are removed, and the managed Python environment is cleared so KiCad can recreate it on the next launch.

In KiCad, enable the API under **Preferences/Settings → Preferences → Plugins**, confirm the Python interpreter, restart KiCad, open a board in PCB Editor, and launch:

```text
Tools / ツール
└── External Plugins / 外部プラグイン
    └── Open EMI Guardian
```

Python 3.9 is supported. The plugin manifest declares Python 3.9 as the minimum version.

See the [English user manual](docs/en/user-manual.md), [日本語取扱説明書](docs/ja/user-manual.md), [English installation guide](docs/en/installation.md), or [日本語インストール手順](docs/ja/installation.md).

## Release artifacts

Run `python scripts/build_package.py` to generate:

- `dist/emi-guardian-0.0.2-windows-installer.zip`
- `dist/emi-guardian-0.0.2-macos-installer.zip`
- `dist/emi-guardian-0.0.2-linux-installer.zip`
- `dist/emi-guardian-0.0.2-all-platform-installers.zip`
- `dist/emi-guardian-0.0.2-manual-install.zip`
- `dist/openai-emi-guardian-0.0.2-pcm.zip`
- `dist/kicad-emi-guardian-0.0.2-source.zip`
- `dist/emi-guardian-0.0.2-demo-report.zip`
- `dist/emi-guardian-0.0.2-user-manuals.zip`
- `dist/SHA256SUMS` and `dist/BUILD-INFO.json`

## Development and verification

```bash
python -m pip install -e ".[test,docs,quality]"
python -m coverage run -m pytest -q
python -m coverage report --fail-under=68
ruff check plugin tests scripts docs/conf.py
ruff format --check plugin tests scripts docs/conf.py
mypy plugin/emi_guardian
bandit -r plugin/emi_guardian plugin/open_dashboard.py plugin/quick_scan.py -ll
python -m compileall -q plugin tests scripts
node --check plugin/emi_guardian/web/app.js
sphinx-build -W --keep-going -b html docs docs/_build/html
pip-audit --strict --requirement plugin/requirements.txt
python scripts/check_package.py
python scripts/build_package.py
```

The runtime dependency is `kicad-python>=0.7.1,<1.0`. KiCad normally provisions plugin requirements in its managed environment. The analysis, DFM, preview-data, and planning cores are unit-testable using KiCad-independent board snapshots.

The repository includes Python 3.9/3.13/3.14 CI, strict static and documentation checks, dependency auditing, reproducible release validation, CodeQL, Dependabot, and release instructions:

- [Publishing on GitHub](docs/en/github-release.md)
- [GitHubへの公開手順](docs/ja/github-release.md)
- [Release checklist](RELEASE_CHECKLIST.md)

## Documentation

- [English user manual](docs/en/user-manual.md) / [日本語取扱説明書](docs/ja/user-manual.md)
- [JLCPCB profiles](docs/en/manufacturing-jlcpcb.md) / [JLCPCBプロファイル](docs/ja/manufacturing-jlcpcb.md)
- [Safety and limitations](docs/en/safety-and-limitations.md) / [安全性と制限](docs/ja/safety-and-limitations.md)
- [Requirement traceability](docs/en/implementation-status.md) / [要件対応表](docs/ja/implementation-status.md)
- [Acceptance test](docs/en/acceptance-test.md) / [受入試験](docs/ja/acceptance-test.md)
- [Default configuration](plugin/default-config.json)

## License

MIT. Copyright (c) 2026 OpenAI and Ryo Nishikawa. See [LICENSE](LICENSE).

---

# KiCad 10+向け EMI Guardian

**EMI Guardian 0.0.2**は、KiCad 10.0.5以降を対象とする日英対応IPC Pluginです。青系UI、完全な日本語検出結果、拡大・移動・レイヤー切替が可能な基板／修正／シルクプレビュー、KiCad上での選択とズーム、補正済みの折れ角・電気的長配線判定、JLCPCB 2層DFM、GNDアンテナ対策、シルク整理、凸形状を基本とする外形最適化を統合します。

「KiCadで場所を表示」は、公開IPCで該当アイテムを選択し、可能なら該当レイヤーへ切り替えて選択範囲へズームします。永続的なカスタムDRCマーカーを生成する機能ではありません。

Windows、macOS、Linux用のインストール／更新／アンインストールスクリプトを同梱しています。KiCadを終了してから各OS用パッケージを実行し、再起動後にPCB Editorの**ツール → 外部プラグイン → Open EMI Guardian**から起動してください。

詳しい操作は[日本語取扱説明書](docs/ja/user-manual.md)、GitHub公開方法は[GitHubへの公開手順](docs/ja/github-release.md)を参照してください。

ライセンスはMITです。Copyright (c) 2026 OpenAI and Ryo Nishikawa。詳細は[LICENSE](LICENSE)を参照してください。
