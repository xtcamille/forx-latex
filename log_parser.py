"""Structured LaTeX .log and Tectonic output parser."""
from __future__ import annotations

import re
from pathlib import Path

from .models import DiagnosticItem

_FILE_OPEN_RE = re.compile(r"\((?P<path>(?:\./|\.\\|[A-Za-z]:\\|/)?[^\s()\"']+\.(?:tex|sty|cls|bbl|aux))")
_ERROR_LINE_RE = re.compile(r"^!\s*(.+)$")
_FILE_LINE_ERR_RE = re.compile(r"^([^\s:]+\.(?:tex|sty|cls)):(\d+):\s*(.+)$")
_LINE_NUM_RE = re.compile(r"^l\.(\d+)\s*(.*)$")
_OVERFULL_RE = re.compile(r"^(Overfull|Underfull)\s+\\(hbox|vbox)\s+\(([^)]+)\)(?:.*?\bat lines?\s+(\d+)(?:--(\d+))?)?")
_WARNING_RE = re.compile(r"^(?:LaTeX|Package\s+[^\s]+|Class\s+[^\s]+)\s+Warning:\s*(.+)$")
_TECTONIC_DIAG_RE = re.compile(r"^(error|warning):\s*(.+)$", re.IGNORECASE)


def _norm_file(raw: str, main_file: str) -> str:
    cleaned = raw.strip().replace("\\", "/")
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned or main_file


def parse_compile_log(log_text: str, stderr_text: str = "", *, main_file: str = "main.tex") -> dict[str, list[DiagnosticItem]]:
    """Parse LaTeX .log and compiler stderr into structured errors, warnings, and overfulls."""
    errors: list[DiagnosticItem] = []
    warnings: list[DiagnosticItem] = []
    overfulls: list[DiagnosticItem] = []
    seen: set[tuple[str, str, int | None, str]] = set()

    file_stack: list[str] = [main_file]
    lines = log_text.splitlines()
    i = 0

    def add_item(bucket: list[DiagnosticItem], severity: str, file_name: str, line_no: int | None, msg: str, code: str = "", snippet: str = "") -> None:
        key = (severity, file_name, line_no, msg[:120])
        if key in seen:
            return
        seen.add(key)
        bucket.append(
            DiagnosticItem(
                severity=severity,  # type: ignore[arg-type]
                file=file_name,
                line=line_no,
                message=msg.strip(),
                code=code,
                snippet=snippet.strip(),
            )
        )

    while i < len(lines):
        line = lines[i]
        # Track paren-based TeX file stack
        for m in _FILE_OPEN_RE.finditer(line):
            file_stack.append(_norm_file(m.group("path"), main_file))
        closes = line.count(")") - line.count("(")
        if closes > 0:
            for _ in range(min(closes, max(0, len(file_stack) - 1))):
                file_stack.pop()

        current_file = file_stack[-1] if file_stack else main_file

        # 1. File:line: error style (-file-line-error)
        fl_m = _FILE_LINE_ERR_RE.match(line)
        if fl_m:
            add_item(errors, "error", _norm_file(fl_m.group(1), main_file), int(fl_m.group(2)), fl_m.group(3), code="latex_error")
            i += 1
            continue

        # 2. Classic `! Error` followed by `l.<num>`
        err_m = _ERROR_LINE_RE.match(line)
        if err_m:
            err_msg = err_m.group(1).strip()
            line_no = None
            snippet = ""
            for j in range(i + 1, min(i + 8, len(lines))):
                ln_m = _LINE_NUM_RE.match(lines[j].strip())
                if ln_m:
                    line_no = int(ln_m.group(1))
                    snippet = ln_m.group(2)
                    break
            add_item(errors, "error", current_file, line_no, err_msg, code="tex_error", snippet=snippet)
            i += 1
            continue

        # 3. Overfull / Underfull hbox
        ov_m = _OVERFULL_RE.match(line)
        if ov_m:
            kind = ov_m.group(1)
            box = ov_m.group(2)
            metric = ov_m.group(3)
            ln = int(ov_m.group(4)) if ov_m.group(4) else None
            if kind == "Overfull":
                add_item(overfulls, "overfull", current_file, ln, f"{kind} \\{box} ({metric})", code=f"overfull_{box}")
            i += 1
            continue

        # 4. LaTeX / Package Warnings
        w_m = _WARNING_RE.match(line)
        if w_m:
            msg = w_m.group(1)
            ln_match = re.search(r"on input line (\d+)", msg)
            ln = int(ln_match.group(1)) if ln_match else None
            add_item(warnings, "warning", current_file, ln, msg, code="latex_warning")
            i += 1
            continue

        i += 1

    # Also inspect stderr (e.g. Tectonic messages)
    for raw in stderr_text.splitlines():
        s = raw.strip()
        if not s:
            continue
        td = _TECTONIC_DIAG_RE.match(s)
        if td:
            sev = td.group(1).lower()
            msg = td.group(2)
            ln_match = re.search(r"([^\s:]+\.tex):(\d+)", msg)
            fname = _norm_file(ln_match.group(1), main_file) if ln_match else main_file
            ln = int(ln_match.group(2)) if ln_match else None
            if sev == "error":
                add_item(errors, "error", fname, ln, msg, code="tectonic_error")
            else:
                add_item(warnings, "warning", fname, ln, msg, code="tectonic_warning")

    return {"errors": errors, "warnings": warnings, "overfulls": overfulls}
