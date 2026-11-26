"""Multi-file LaTeX project parser: dependency tree, outline, labels, citations, and packages."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .models import CiteUsage, LabelEntry, OutlineNode, ProjectStructure, RefUsage

_COMMENT_RE = re.compile(r"(?<!\\)%.*$")
_DOC_CLASS_RE = re.compile(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}")
_INPUT_RE = re.compile(r"\\(?:input|include|subfile)\{([^}]+)\}")
_PACKAGE_RE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}")
_BIB_RE = re.compile(r"\\(?:bibliography|addbibresource)(?:\[[^\]]*\])?\{([^}]+)\}")
_GRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
_SECTION_RE = re.compile(r"\\(part|chapter|section|subsection|subsubsection)\*?\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
_ENV_START_RE = re.compile(r"\\begin\{(figure|table|algorithm|algorithm2e)\*?\}")
_CAPTION_RE = re.compile(r"\\caption(?:\[[^\]]*\])?\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
_REF_RE = re.compile(r"\\(eq)?ref\{([^}]+)\}|\\(autoref|cref|Cref|pageref)\{([^}]+)\}")
_CITE_RE = re.compile(
    r"\\(cite|citep|citet|citealp|citealt|autocite|textcite|parencite|fullcite)\*?(?:\[[^\]]*\])*\{([^}]+)\}"
)
_MACRO_RE = re.compile(r"\\(?:newcommand|renewcommand|providecommand|DeclareMathOperator)\*?\{?(\\[A-Za-z@]+)\}?")

_SECTION_LEVELS = {
    "part": 0,
    "chapter": 1,
    "section": 2,
    "subsection": 3,
    "subsubsection": 4,
}


def strip_comments(line: str) -> str:
    return _COMMENT_RE.sub("", line)


def detect_main_file(workspace: Path, preferred: str = "main.tex") -> str:
    preferred_path = workspace / preferred
    if preferred_path.is_file():
        return preferred
    tex_files = sorted(workspace.rglob("*.tex"))
    for p in tex_files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _DOC_CLASS_RE.search(text):
            return p.relative_to(workspace).as_posix()
    return tex_files[0].relative_to(workspace).as_posix() if tex_files else preferred


def _resolve_tex_include(workspace: Path, current_file: Path, raw_target: str) -> Optional[str]:
    cleaned = raw_target.strip().strip('"')
    if not cleaned:
        return None
    candidates = [cleaned] if cleaned.endswith(".tex") else [f"{cleaned}.tex", cleaned]
    for base in (workspace, current_file.parent):
        for cand in candidates:
            target = (base / cand).resolve()
            if target.is_file() and target.is_relative_to(workspace.resolve()):
                return target.relative_to(workspace.resolve()).as_posix()
    return None


def _infer_label_kind(key: str, active_env: Optional[str]) -> str:
    if active_env:
        return active_env
    prefix = key.split(":", 1)[0].lower() if ":" in key else ""
    mapping = {
        "sec": "section", "subsec": "subsection", "chap": "chapter",
        "fig": "figure", "tab": "table", "eq": "equation",
        "alg": "algorithm", "thm": "theorem", "lem": "lemma",
        "def": "definition", "lst": "listing", "app": "appendix",
    }
    return mapping.get(prefix, "unknown")


def parse_project(workspace: Path, main_file: str = "main.tex") -> ProjectStructure:
    """Parse multi-file LaTeX workspace starting from *main_file*."""
    ws = workspace.resolve()
    resolved_main = detect_main_file(ws, main_file)

    visited: list[str] = []
    visited_set: set[str] = set()
    packages: list[str] = []
    bib_files: list[str] = []
    graphics_files: list[str] = []
    outline: list[OutlineNode] = []
    labels: list[LabelEntry] = []
    refs: list[RefUsage] = []
    cites: list[CiteUsage] = []
    macros: list[str] = []
    uses_biber = False
    needs_xelatex = False

    def walk_file(rel_path: str) -> None:
        nonlocal uses_biber, needs_xelatex
        if rel_path in visited_set:
            return
        file_path = (ws / rel_path).resolve()
        if not file_path.is_file() or not file_path.is_relative_to(ws):
            return
        visited_set.add(rel_path)
        visited.append(rel_path)

        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        active_env: Optional[str] = None
        pending_env_node: Optional[OutlineNode] = None

        for idx, raw_line in enumerate(lines, start=1):
            line = strip_comments(raw_line)
            if not line.strip():
                continue

            # Document class / Chinese or fontspec hints
            dc = _DOC_CLASS_RE.search(line)
            if dc and any(k in dc.group(1) for k in ("ctex", "xe", "thu", "ustc")):
                needs_xelatex = True

            for pkg_match in _PACKAGE_RE.finditer(line):
                for pkg in pkg_match.group(1).split(","):
                    p_clean = pkg.strip()
                    if p_clean and p_clean not in packages:
                        packages.append(p_clean)
                    if p_clean in {"ctex", "xeCJK", "fontspec", "unicode-math"}:
                        needs_xelatex = True
                    if p_clean == "biblatex":
                        uses_biber = True

            if "backend=biber" in line:
                uses_biber = True

            for bib_match in _BIB_RE.finditer(line):
                for b in bib_match.group(1).split(","):
                    b_clean = b.strip()
                    if not b_clean:
                        continue
                    if not b_clean.endswith(".bib"):
                        b_clean = f"{b_clean}.bib"
                    if b_clean not in bib_files:
                        bib_files.append(b_clean)

            for gfx_match in _GRAPHICS_RE.finditer(line):
                g_clean = gfx_match.group(1).strip()
                if g_clean and g_clean not in graphics_files:
                    graphics_files.append(g_clean)

            for macro_match in _MACRO_RE.finditer(line):
                m_name = macro_match.group(1)
                if m_name not in macros:
                    macros.append(m_name)

            # Environments (figure / table / algorithm)
            env_m = _ENV_START_RE.search(line)
            if env_m:
                env_name = "algorithm" if "algorithm" in env_m.group(1) else env_m.group(1)
                active_env = env_name
                pending_env_node = OutlineNode(
                    id=f"{rel_path}:{idx}",
                    level=3,
                    kind=env_name,  # type: ignore[arg-type]
                    title=f"[{env_name}]",
                    file=rel_path,
                    line=idx,
                )
                outline.append(pending_env_node)

            cap_m = _CAPTION_RE.search(line)
            if cap_m and pending_env_node is not None:
                pending_env_node.title = cap_m.group(1).strip()[:80]

            if active_env and f"\\end{{{active_env}" in line:
                active_env = None
                pending_env_node = None

            # Sections
            sec_m = _SECTION_RE.search(line)
            if sec_m:
                sec_kind = sec_m.group(1)
                outline.append(
                    OutlineNode(
                        id=f"{rel_path}:{idx}",
                        level=_SECTION_LEVELS.get(sec_kind, 2),
                        kind=sec_kind,  # type: ignore[arg-type]
                        title=sec_m.group(2).strip()[:100],
                        file=rel_path,
                        line=idx,
                    )
                )

            # Labels
            for lbl_m in _LABEL_RE.finditer(line):
                key = lbl_m.group(1).strip()
                labels.append(
                    LabelEntry(
                        key=key,
                        kind=_infer_label_kind(key, active_env),
                        file=rel_path,
                        line=idx,
                        context=line.strip()[:120],
                    )
                )
                if pending_env_node is not None and pending_env_node.label is None:
                    pending_env_node.label = key
                elif outline and outline[-1].file == rel_path and outline[-1].line >= idx - 3 and outline[-1].label is None:
                    outline[-1].label = key

            # Refs
            for ref_m in _REF_RE.finditer(line):
                if ref_m.group(2):
                    cmd = "eqref" if ref_m.group(1) == "eq" else "ref"
                    raw_keys = ref_m.group(2)
                else:
                    cmd = ref_m.group(3) or "ref"
                    raw_keys = ref_m.group(4) or ""
                for rk in raw_keys.split(","):
                    k = rk.strip()
                    if k:
                        refs.append(RefUsage(key=k, command=cmd, file=rel_path, line=idx))

            # Cites
            for cite_m in _CITE_RE.finditer(line):
                cmd = cite_m.group(1)
                keys = [k.strip() for k in cite_m.group(2).split(",") if k.strip()]
                if keys:
                    cites.append(CiteUsage(keys=keys, command=cmd, file=rel_path, line=idx))

            # Recurse into \input / \include
            for inc_m in _INPUT_RE.finditer(line):
                child = _resolve_tex_include(ws, file_path, inc_m.group(1))
                if child:
                    walk_file(child)

    walk_file(resolved_main)

    # Also discover orphan .bib files in workspace if none explicitly declared
    if not bib_files:
        for bib in sorted(ws.rglob("*.bib")):
            bib_files.append(bib.relative_to(ws).as_posix())

    rec_engine = "tectonic"
    if needs_xelatex:
        # Tectonic uses a XeTeX-derived engine natively and handles Unicode/ctex well,
        # while TeX Live / MiKTeX users should use xelatex for CJK/fontspec.
        rec_engine = "tectonic"

    return ProjectStructure(
        main_file=resolved_main,
        included_files=visited,
        packages=packages,
        bib_files=bib_files,
        graphics_files=graphics_files,
        recommended_engine=rec_engine,
        uses_biber=uses_biber,
        outline=outline,
        labels=labels,
        refs=refs,
        cites=cites,
        macros=macros,
    )
