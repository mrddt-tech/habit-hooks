from __future__ import annotations

import sys


def split_diagnostics(findings: list[dict]) -> tuple[list[dict], list[dict]]:
    coaching, diagnostics = [], []
    for finding in findings:
        target = diagnostics if finding.get("details", {}).get("diagnostic") is True else coaching
        target.append(finding)
    return coaching, diagnostics


def diagnostic_line(issue: dict) -> str:
    details = issue["details"]
    file = details.get("file", issue["key"])
    line, column = details.get("line", 1), details.get("column", 1)
    return f"{file}:{line}:{column}: {details.get('source', '')} {details.get('message', '')}"


def write_diagnostics(findings: list[dict]) -> None:
    for finding in findings:
        tool = finding["details"].get("tool", "diagnostics")
        lines = "\n".join(diagnostic_line(issue) for issue in finding["issues"])
        sys.stdout.write(f"\n── {tool} ──\n{lines}\n")
