"""LaTeX token/AST protection for safe AI rewriting, unified diff, and word counting."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Order matters: larger/block constructs first, inline constructs after.
_PROTECTED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ENV_MATH", re.compile(r"\\begin\{(equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{\1\*?\}", re.S)),
    ("ENV_CODE", re.compile(r"\\begin\{(verbatim|lstlisting|minted|algorithm|algorithm2e)\*?\}.*?\\end\{\1\*?\}", re.S)),
    ("DISP_MATH_BRACKET", re.compile(r"\\\[.*?\\\]", re.S)),
    ("DISP_MATH_DOLLAR", re.compile(r"\$\$.*?\$\$", re.S)),
    ("INLINE_MATH_PAREN", re.compile(r"\\\(.*?\\\)", re.S)),
    ("INLINE_MATH_DOLLAR", re.compile(r"(?<!\\)\$[^$\n]+?(?<!\\)\$")),
    ("CITE_CMD", re.compile(r"\\(?:cite|citep|citet|citealp|citealt|autocite|textcite|parencite|fullcite)\*?(?:\[[^\]]*\])*\{[^}]+\}")),
    ("REF_CMD", re.compile(r"\\(?:eq)?ref\{[^}]+\}|\\(?:autoref|cref|Cref|pageref|label)\{[^}]+\}")),
    ("URL_CMD", re.compile(r"\\(?:url|href|texttt|includegraphics)(?:\[[^\]]*\])*\{[^}]+\}(?:\{[^}]+\})?")),
    ("STRUCT_CMD", re.compile(r"\\(?:part|chapter|section|subsection|subsubsection|paragraph)\*?\{[^}]+\}|\\(?:begin|end)\{[^}]+\}|\\item\b")),
    ("COMMENT", re.compile(r"(?<!\\)%[^\n]*")),
]

_PLACEHOLDER_RE = re.compile(r"\[\[LTX_(\d{4})\]\]")


@dataclass
class ProtectedText:
    masked_text: str
    tokens: dict[str, str]
    critical_keys: list[str]


def protect_latex_tokens(text: str) -> ProtectedText:
    """Replace sensitive LaTeX commands, math, citations, and labels with [[LTX_XXXX]] placeholders."""
    tokens: dict[str, str] = {}
    critical_keys: list[str] = []
    counter = 0
    working = text

    # Mask sequentially while skipping already-inserted [[LTX_XXXX]] placeholders
    for kind, pattern in _PROTECTED_PATTERNS:
        parts: list[str] = []
        last = 0
        for m in pattern.finditer(working):
            span = m.group(0)
            if "[[LTX_" in span:
                continue
            counter += 1
            placeholder = f"[[LTX_{counter:04d}]]"
            tokens[placeholder] = span
            if kind in {"CITE_CMD", "REF_CMD", "ENV_MATH", "DISP_MATH_BRACKET", "DISP_MATH_DOLLAR", "INLINE_MATH_DOLLAR", "INLINE_MATH_PAREN", "STRUCT_CMD"}:
                critical_keys.append(placeholder)
            parts.append(working[last : m.start()])
            parts.append(placeholder)
            last = m.end()
        parts.append(working[last:])
        working = "".join(parts)

    return ProtectedText(masked_text=working, tokens=tokens, critical_keys=critical_keys)


def restore_latex_tokens(masked_output: str, protected: ProtectedText) -> tuple[str, bool, list[str]]:
    """Restore placeholders and verify no critical citation/ref/math tokens were dropped or corrupted."""
    errors: list[str] = []
    found = set(_PLACEHOLDER_RE.findall(masked_output))
    for placeholder in protected.critical_keys:
        num = placeholder[6:10]
        if num not in found:
            errors.append(f"丢失关键 LaTeX 指令 {placeholder}: {protected.tokens[placeholder][:60]}")

    for m in _PLACEHOLDER_RE.finditer(masked_output):
        ph = m.group(0)
        if ph not in protected.tokens:
            errors.append(f"出现未知占位符 {ph}")

    restored = masked_output
    for placeholder, original in protected.tokens.items():
        restored = restored.replace(placeholder, original)
    return restored, len(errors) == 0, errors


def compute_unified_diff(original: str, updated: str, *, filename: str = "section.tex") -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )


def strip_latex_for_word_count(text: str) -> str:
    """Strip preamble, comments, math, and commands to estimate readable prose words."""
    if "\\begin{document}" in text:
        text = text.split("\\begin{document}", 1)[1]
    if "\\end{document}" in text:
        text = text.split("\\end{document}", 1)[0]
    text = re.sub(r"(?<!\\)%.*$", "", text, flags=re.M)
    text = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.S)
    text = re.sub(r"\\\[.*?\\\]", " ", text, flags=re.S)
    text = re.sub(r"(?<!\\)\$[^$\n]+?(?<!\\)\$", " ", text)
    text = re.sub(r"\\(?:cite|citep|citet|ref|eqref|label|usepackage|documentclass|bibliographystyle|bibliography)\*?(?:\[[^\]]*\])*\{[^}]*\}", " ", text)
    text = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    return text


def count_words_in_text(text: str) -> dict[str, int]:
    prose = strip_latex_for_word_count(text)
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", prose))
    en_words = len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", prose))
    return {"en_words": en_words, "cjk_chars": cjk_chars, "total_units": en_words + cjk_chars}


def count_project_words(workspace: Path, tex_files: list[str]) -> dict[str, Any]:
    per_file: list[dict[str, Any]] = []
    tot_en = 0
    tot_cjk = 0
    for rel in tex_files:
        p = (workspace / rel).resolve()
        if not p.is_file():
            continue
        counts = count_words_in_text(p.read_text(encoding="utf-8", errors="replace"))
        tot_en += counts["en_words"]
        tot_cjk += counts["cjk_chars"]
        per_file.append({"file": rel, **counts})
    return {
        "en_words": tot_en,
        "cjk_chars": tot_cjk,
        "total_units": tot_en + tot_cjk,
        "files": per_file,
    }
