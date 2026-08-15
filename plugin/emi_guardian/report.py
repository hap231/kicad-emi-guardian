"""HTML, JSON, and Markdown report generation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from html import escape
from pathlib import Path
from typing import Any

from .models import AnalysisReport, FixPlan


def write_report_bundle(
    directory: Path,
    report: AnalysisReport,
    fix_plan: FixPlan | None = None,
    silkscreen_plan: Mapping[str, Any] | None = None,
    edge_proposal: Mapping[str, Any] | None = None,
    manufacturing_report: Mapping[str, Any] | None = None,
) -> dict[str, Path]:
    """Write a complete report bundle and return its paths."""

    directory.mkdir(parents=True, exist_ok=True)
    payload = _payload(
        report,
        fix_plan,
        silkscreen_plan,
        edge_proposal,
        manufacturing_report,
    )
    json_path = directory / "emi-guardian-report.json"
    html_path = directory / "emi-guardian-report.html"
    markdown_path = directory / "emi-guardian-report.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    html_path.write_text(render_html(payload), encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": json_path, "html": html_path, "markdown": markdown_path}


def render_html(payload: Mapping[str, Any]) -> str:
    """Render a self-contained modern HTML report."""

    score = float(payload["analysis"]["score"])
    category_scores = payload["analysis"]["category_scores"]
    findings = payload["analysis"]["findings"]
    cards = "".join(_finding_card(finding) for finding in findings)
    category_rows = "".join(
        f"<tr><td>{escape(str(category))}</td><td>{float(value):.1f}</td>"
        f"<td><div class='bar'><span style='width:{max(0.0, min(100.0, float(value))):.1f}%'></span></div></td></tr>"
        for category, value in sorted(category_scores.items())
    )
    caveats = "".join(f"<li>{escape(str(item))}</li>" for item in payload["analysis"]["caveats"])
    manufacturing_section = _manufacturing_section(payload.get("manufacturing_report"))
    fix_section = _fix_section(payload.get("fix_plan"))
    silk_section = _generic_section("Silkscreen plan", payload.get("silkscreen_plan"))
    edge_section = _generic_section("Edge.Cuts proposal", payload.get("edge_proposal"))
    quantitative = escape(
        json.dumps(payload["analysis"]["quantitative"], ensure_ascii=False, indent=2, sort_keys=True)
    )
    data_json = escape(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EMI Guardian Report</title>
<style>
:root {{ color-scheme: light dark; --bg:#0b1020; --panel:#151c31; --line:#2a3555; --text:#eef3ff; --muted:#a9b4ce; --accent:#64d2ff; --ok:#5ee29a; --warn:#ffcc66; --bad:#ff718b; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font-family:Inter,Segoe UI,Helvetica,Arial,sans-serif; background:linear-gradient(135deg,#090d19,#101a33); color:var(--text); }}
main {{ width:min(1180px,94vw); margin:32px auto 80px; }} .hero {{ display:grid; grid-template-columns:220px 1fr; gap:24px; align-items:center; }}
.score {{ width:190px; height:190px; border-radius:50%; display:grid; place-items:center; background:conic-gradient(var(--accent) {score:.1f}%,#26314f 0); position:relative; }}
.score:after {{ content:''; position:absolute; inset:17px; border-radius:50%; background:var(--panel); }} .score strong {{ z-index:1; font-size:48px; }}
h1 {{ font-size:clamp(30px,5vw,54px); margin:0 0 8px; }} .muted {{ color:var(--muted); }} .panel {{ background:rgba(21,28,49,.94); border:1px solid var(--line); border-radius:18px; padding:22px; margin-top:22px; box-shadow:0 16px 40px rgba(0,0,0,.20); }}
table {{ width:100%; border-collapse:collapse; }} td,th {{ padding:10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }} .bar {{ height:10px; background:#26314f; border-radius:99px; overflow:hidden; }} .bar span {{ display:block; height:100%; background:linear-gradient(90deg,var(--bad),var(--warn),var(--ok)); }}
.findings {{ display:grid; gap:14px; }} .finding {{ border:1px solid var(--line); border-left:5px solid var(--accent); border-radius:12px; padding:16px; background:#11182b; }}
.finding.high,.finding.critical,.issue.error {{ border-left-color:var(--bad); }} .finding.medium,.issue.warning {{ border-left-color:var(--warn); }} .issue.info {{ border-left-color:var(--accent); }} .pill {{ display:inline-block; border:1px solid var(--line); border-radius:99px; padding:3px 9px; margin-right:6px; color:var(--muted); font-size:12px; }}
.summary-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }} .summary-card {{ border:1px solid var(--line); background:#11182b; border-radius:12px; padding:14px; }} .summary-card strong {{ display:block; font-size:25px; margin-top:5px; }}
pre {{ white-space:pre-wrap; word-break:break-word; background:#090e1b; border:1px solid var(--line); padding:14px; border-radius:10px; overflow:auto; }} details summary {{ cursor:pointer; font-weight:700; }}
@media(max-width:700px) {{ .hero {{ grid-template-columns:1fr; }} .score {{ width:150px; height:150px; }} }}
</style>
</head>
<body><main>
<section class="hero"><div class="score"><strong>{score:.0f}</strong></div><div><h1>EMI Guardian</h1><p class="muted">{escape(str(payload["analysis"]["board_name"]))} · KiCad {escape(str(payload["analysis"]["kicad_version"]))}</p><p>Geometric EMI screening, JLCPCB DFM validation, remediation planning, silkscreen cleanup, and outline review.</p></div></section>
<section class="panel"><h2>Category scores</h2><table><thead><tr><th>Category</th><th>Score</th><th>Relative quality</th></tr></thead><tbody>{category_rows}</tbody></table></section>
{manufacturing_section}
<section class="panel"><h2>Findings ({len(findings)})</h2><div class="findings">{cards or "<p>No findings at the configured thresholds.</p>"}</div></section>
{fix_section}{silk_section}{edge_section}
<section class="panel"><details><summary>Quantitative estimates</summary><pre>{quantitative}</pre></details></section>
<section class="panel"><h2>Important caveats</h2><ul>{caveats}</ul></section>
<section class="panel"><details><summary>Machine-readable report payload</summary><pre id="raw">{data_json}</pre></details></section>
</main></body></html>"""


def render_markdown(payload: Mapping[str, Any]) -> str:
    """Render a compact Markdown report."""

    analysis = payload["analysis"]
    lines = [
        "# EMI Guardian Report",
        "",
        f"- Board: `{analysis['board_name']}`",
        f"- KiCad: `{analysis['kicad_version']}`",
        f"- EMI screening score: **{float(analysis['score']):.1f}/100**",
        "",
        "## Category scores",
        "",
    ]
    lines.extend(
        f"- {name}: {float(value):.1f}" for name, value in sorted(analysis["category_scores"].items())
    )
    manufacturing = payload.get("manufacturing_report")
    if isinstance(manufacturing, Mapping):
        lines.extend(_manufacturing_markdown(manufacturing))
    lines.extend(["", "## Findings", ""])
    for finding in analysis["findings"]:
        lines.extend(
            [
                f"### {finding['finding_id']} — {finding['title']}",
                "",
                f"- Severity: **{finding['severity']}**",
                f"- Confidence: {float(finding['confidence']):.0%}",
                f"- Category: `{finding['category']}`",
                "",
                str(finding["description"]),
                "",
                f"Recommendation: {finding['recommendation']}",
                "",
            ]
        )
    lines.extend(["## Caveats", ""])
    lines.extend(f"- {item}" for item in analysis["caveats"])
    return "\n".join(lines) + "\n"


def _payload(
    report: AnalysisReport,
    fix_plan: FixPlan | None,
    silkscreen_plan: Mapping[str, Any] | None,
    edge_proposal: Mapping[str, Any] | None,
    manufacturing_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build one serializable report payload."""

    return {
        "schema_version": 2,
        "analysis": report.to_dict(),
        "manufacturing_report": dict(manufacturing_report) if manufacturing_report else None,
        "fix_plan": fix_plan.to_dict() if fix_plan else None,
        "silkscreen_plan": dict(silkscreen_plan) if silkscreen_plan else None,
        "edge_proposal": dict(edge_proposal) if edge_proposal else None,
    }


def _manufacturing_section(value: Any) -> str:
    """Render a concise JLCPCB DFM section."""

    if not isinstance(value, Mapping):
        return ""
    summary = value.get("statistics", value.get("summary", {}))
    constraints = value.get("constraints", {})
    order = value.get("order_settings", {})
    issues = value.get("issues", [])
    issue_cards = "".join(_manufacturing_issue_card(issue) for issue in issues)
    status = escape(str(value.get("status", "unknown")))
    profile = escape(
        str(value.get("profile_name_en", value.get("profile_name", value.get("profile_id", "JLCPCB"))))
    )
    score = float(value.get("score", 0.0))
    errors = (
        int(summary.get("error_count", summary.get("error", summary.get("errors", 0))))
        if isinstance(summary, Mapping)
        else 0
    )
    warnings = (
        int(summary.get("warning_count", summary.get("warning", summary.get("warnings", 0))))
        if isinstance(summary, Mapping)
        else 0
    )
    info = int(summary.get("info_count", summary.get("info", 0))) if isinstance(summary, Mapping) else 0
    order_json = escape(json.dumps(order, ensure_ascii=False, indent=2, sort_keys=True))
    constraints_json = escape(json.dumps(constraints, ensure_ascii=False, indent=2, sort_keys=True))
    return f"""<section class='panel'><h2>JLCPCB manufacturability</h2>
<p><span class='pill'>{profile}</span><span class='pill'>{status}</span></p>
<div class='summary-grid'><div class='summary-card'>DFM score<strong>{score:.1f}</strong></div><div class='summary-card'>Errors<strong>{errors}</strong></div><div class='summary-card'>Warnings<strong>{warnings}</strong></div><div class='summary-card'>Information<strong>{info}</strong></div></div>
<h3>Issues ({len(issues)})</h3><div class='findings'>{issue_cards or "<p>No JLCPCB DFM issues at the active profile thresholds.</p>"}</div>
<details><summary>Order settings</summary><pre>{order_json}</pre></details>
<details><summary>Active constraints</summary><pre>{constraints_json}</pre></details>
<p class='muted'>This is a deterministic design-for-manufacturing check, not a quotation or acceptance guarantee. Verify the live JLCPCB quote and DFM result before ordering.</p></section>"""


def _manufacturing_issue_card(issue: Mapping[str, Any]) -> str:
    """Render one manufacturing issue card."""

    severity = escape(str(issue.get("severity", "info")))
    code = escape(str(issue.get("code", "DFM")))
    title = escape(str(issue.get("title", code)))
    description = escape(str(issue.get("description", "")))
    recommendation = escape(str(issue.get("recommendation", "")))
    location = issue.get("location")
    location_text = ""
    if isinstance(location, Mapping) and "x" in location and "y" in location:
        location_text = f" · ({float(location['x']):.2f}, {float(location['y']):.2f}) mm"
    return f"""<article class='finding issue {severity}'><div><span class='pill'>{code}</span><span class='pill'>{severity}</span></div><h3>{title}</h3><p>{description}</p><p><strong>Recommendation:</strong> {recommendation}</p><p class='muted'>{escape(location_text)}</p></article>"""


def _manufacturing_markdown(value: Mapping[str, Any]) -> list[str]:
    """Render manufacturing data as Markdown lines."""

    summary = value.get("statistics", value.get("summary", {}))
    lines = [
        "",
        "## JLCPCB manufacturability",
        "",
        f"- Profile: `{value.get('profile_name_en', value.get('profile_name', value.get('profile_id', 'unknown')))}`",
        f"- Status: **{value.get('status', 'unknown')}**",
        f"- DFM score: **{float(value.get('score', 0.0)):.1f}/100**",
    ]
    if isinstance(summary, Mapping):
        lines.extend(
            [
                f"- Errors: {int(summary.get('error', summary.get('errors', 0)))}",
                f"- Warnings: {int(summary.get('warning', summary.get('warnings', 0)))}",
                f"- Information: {int(summary.get('info', 0))}",
            ]
        )
    lines.extend(["", "### JLCPCB DFM issues", ""])
    issues = value.get("issues", [])
    if not issues:
        lines.append("No issues were found at the active profile thresholds.")
    for issue in issues:
        lines.extend(
            [
                f"#### {issue.get('code', 'DFM')} — {issue.get('title', '')}",
                "",
                f"- Severity: **{issue.get('severity', 'info')}**",
                f"- Recommendation: {issue.get('recommendation', '')}",
                "",
                str(issue.get("description", "")),
                "",
            ]
        )
    lines.extend(
        [
            "> This check is not a quotation or manufacturing acceptance guarantee. Confirm the live JLCPCB DFM result before ordering.",
            "",
        ]
    )
    return lines


def _finding_card(finding: Mapping[str, Any]) -> str:
    """Render one finding card."""

    location = finding.get("location")
    location_text = ""
    if isinstance(location, Mapping):
        location_text = f" · ({float(location['x']):.2f}, {float(location['y']):.2f}) mm"
    metrics = escape(json.dumps(finding.get("metrics", {}), ensure_ascii=False, indent=2, sort_keys=True))
    severity = escape(str(finding["severity"]))
    return f"""<article class="finding {severity}">
<div><span class="pill">{escape(str(finding["finding_id"]))}</span><span class="pill">{severity}</span><span class="pill">confidence {float(finding["confidence"]):.0%}</span></div>
<h3>{escape(str(finding["title"]))}</h3><p>{escape(str(finding["description"]))}</p><p><strong>Recommendation:</strong> {escape(str(finding["recommendation"]))}</p>
<p class="muted">Category: {escape(str(finding["category"]))}{escape(location_text)}</p><details><summary>Evidence</summary><pre>{metrics}</pre></details></article>"""


def _fix_section(fix_plan: Any) -> str:
    """Render the automatic-fix section."""

    if not fix_plan:
        return ""
    actions = fix_plan.get("actions", [])
    rows = "".join(
        f"<tr><td>{escape(str(action['action_id']))}</td><td>{escape(str(action['kind']))}</td>"
        f"<td>{escape(str(action['description']))}</td><td>{float(action['confidence']):.0%}</td></tr>"
        for action in actions
    )
    warnings = "".join(f"<li>{escape(str(item))}</li>" for item in fix_plan.get("warnings", []))
    return f"<section class='panel'><h2>Automatic remediation plan</h2><table><thead><tr><th>ID</th><th>Kind</th><th>Operation</th><th>Confidence</th></tr></thead><tbody>{rows}</tbody></table><ul>{warnings}</ul></section>"


def _generic_section(title: str, value: Any) -> str:
    """Render a generic JSON details section."""

    if not value:
        return ""
    content = escape(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return f"<section class='panel'><details><summary>{escape(title)}</summary><pre>{content}</pre></details></section>"
