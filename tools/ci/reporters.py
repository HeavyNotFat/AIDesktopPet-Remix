from __future__ import annotations

import json
from typing import Iterable

from .core import Report, Severity

_ORDER = (Severity.ERROR, Severity.WARNING, Severity.INFO)


def render_text(
    report: Report,
    *,
    color: bool = False,
    show_ok: bool = True,
    limit: int | None = None,
) -> str:
    def paint(text: str, severity: Severity | None) -> str:
        if not color:
            return text
        codes = {Severity.ERROR: "31", Severity.WARNING: "33", Severity.INFO: "36"}
        return f"\033[{codes[severity]}m{text}\033[0m" if severity else text

    lines: list[str] = []
    by_check: dict[str, list] = {}
    for item in report.findings:
        by_check.setdefault(item.check, []).append(item)

    printed = 0
    hidden = 0
    for result in report.results:
        findings = by_check.get(result.id, [])
        if result.crash:
            lines.append(paint(f"✗ {result.id} 检查自身崩溃", Severity.ERROR))
            lines.append(f"    {result.crash.splitlines()[0]}")
            continue
        if not findings and not show_ok:
            continue
        head = "✓" if not findings else "✗"
        lines.append(paint(f"{head} {result.id} — {result.title}", findings[0].severity if findings else None))
        for item in findings:
            if limit and printed >= limit:
                hidden += 1
                continue
            printed += 1
            lines.append(f"    {item.severity.value.upper():7s} {item.location}")
            lines.append(f"            {item.message}")
            if item.hint:
                lines.append(f"            → {item.hint}")

    counts = report.counts()
    duration = sum(r.duration for r in report.results)
    lines.append("")
    if hidden:
        lines.append(f"（另有 {hidden} 条问题未显示，去掉 --max-findings 可查看全部）")
    lines.append(
        f"合计：{counts['error']} error / {counts['warning']} warning / {counts['info']} info"
        f"（{len(report.results)} 个检查，{duration:.2f}s"
        + (f"，抑制 {report.suppressed} 条" if report.suppressed else "")
        + "）"
    )
    return "\n".join(lines)


def render_json(report: Report) -> str:
    payload = {
        "summary": {
            **report.counts(),
            "checks": len(report.results),
            "crashes": len(report.crashes),
            "suppressed": report.suppressed,
            "exit_code": report.exit_code(),
        },
        "results": [
            {
                "id": result.id,
                "title": result.title,
                "category": result.category,
                "duration": round(result.duration, 4),
                "skipped": result.skipped,
                "crash": result.crash,
                "suppressed": result.suppressed,
                "findings": [item.as_dict() for item in result.findings],
            }
            for result in report.results
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_markdown(report: Report) -> str:
    counts = report.counts()
    lines = [
        "## UI / 架构质量门禁",
        "",
        f"- 检查项：**{len(report.results)}**",
        f"- 问题：**{counts['error']}** error / **{counts['warning']}** warning / **{counts['info']}** info",
        f"- 退出码：`{report.exit_code()}`",
        "",
    ]

    grouped: dict[str, list] = {}
    for item in report.findings:
        grouped.setdefault(item.check, []).append(item)

    if not report.findings and not report.crashes:
        lines.append("✅ 全部通过。")
        return "\n".join(lines)

    lines.append("| 检查 | 等级 | 位置 | 说明 |")
    lines.append("| --- | --- | --- | --- |")
    for result in report.results:
        for item in grouped.get(result.id, []):
            message = item.message.replace("|", "\\|")
            lines.append(
                f"| `{item.check}` | {_icon(item.severity)} | `{item.location}` | {message} |"
            )
    for result in report.crashes:
        lines.append(f"| `{result.id}` | 💥 | - | 检查崩溃：{result.crash.splitlines()[0]} |")
    return "\n".join(lines)


def render_github(report: Report) -> str:
    lines: list[str] = []
    for item in report.findings:
        command = {
            Severity.ERROR: "error",
            Severity.WARNING: "warning",
            Severity.INFO: "notice",
        }[item.severity]
        message = item.message + (f" → {item.hint}" if item.hint else "")
        lines.append(
            f"::{command} file={_escape(item.location.path, prop=True)},"
            f"line={item.location.line},"
            f"col={max(1, item.location.column + 1)},"
            f"title={_escape(item.check, prop=True)}::{_escape(message)}"
        )
    if not lines:
        lines.append("::notice::UI/架构质量门禁通过")
    return "\n".join(lines)


def render_sarif(report: Report) -> str:
    rules: dict[str, dict] = {}
    results: list[dict] = []
    for result in report.results:
        for item in result.findings:
            rules.setdefault(
                item.check,
                {
                    "id": item.check,
                    "name": item.check,
                    "shortDescription": {"text": result.title},
                    "defaultConfiguration": {"level": _sarif_level(item.severity)},
                    "help": {"text": item.hint or result.title},
                },
            )
            results.append(
                {
                    "ruleId": item.check,
                    "level": _sarif_level(item.severity),
                    "message": {"text": item.message + (f" → {item.hint}" if item.hint else "")},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": item.location.path},
                                "region": {
                                    "startLine": item.location.line,
                                    "startColumn": max(1, item.location.column + 1),
                                },
                            }
                        }
                    ],
                }
            )

    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "adpci",
                        "informationUri": "https://github.com/HeavyNotFat/AIDesktopPet-Remix",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _sarif_level(severity: Severity) -> str:
    return {Severity.ERROR: "error", Severity.WARNING: "warning", Severity.INFO: "note"}[severity]


def _icon(severity: Severity) -> str:
    return {Severity.ERROR: "🛑 error", Severity.WARNING: "⚠️ warning", Severity.INFO: "ℹ️ info"}[severity]


def _escape(text: str, *, prop: bool = False) -> str:
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if prop:
        text = text.replace(",", "%2C").replace(":", "%3A")
    return text


RENDERERS = {
    "text": render_text,
    "json": render_json,
    "markdown": render_markdown,
    "github": render_github,
    "sarif": render_sarif,
}


def render(report: Report, fmt: str, **kwargs) -> str:
    try:
        renderer = RENDERERS[fmt]
    except KeyError as exc:  # pragma: no cover - argparse 已经限制取值
        raise ValueError(f"未知输出格式：{fmt}") from exc
    return renderer(report, **kwargs) if fmt == "text" else renderer(report)
