"""Consistency, citation, math balance, acronym, and double-blind pre-flight checks."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Optional

from .bibtex import parse_bib, validate_bib
from .models import CheckIssue, CheckReport, CompileResult, ProjectMeta
from .project_parser import parse_project, strip_comments
from .syntax_guard import count_project_words

_BEGIN_ENV_RE = re.compile(r"\\begin\{([A-Za-z0-9*]+)\}")
_END_ENV_RE = re.compile(r"\\end\{([A-Za-z0-9*]+)\}")
_ACRONYM_RE = re.compile(r"\b([A-Z]{3,7})\b")
_FUNDING_RE = re.compile(
    r"(?:NSFC|National Natural Science|grant\s+no\.?|supported\s+by|funded\s+by|基金项目|资助编号)",
    re.IGNORECASE,
)
_PERSONAL_URL_RE = re.compile(r"https?://(?:github\.com|gitlab\.com|gitee\.com)/[A-Za-z0-9_-]+", re.IGNORECASE)
_ACK_RE = re.compile(r"\\section\*?\{[^}]*(?:acknowledg|致谢)|\\begin\{acks\}", re.IGNORECASE)
_AUTHOR_BLOCK_RE = re.compile(r"\\author(?:\[[^\]]*\])?\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", re.S)


def run_preflight_check(
    meta: ProjectMeta,
    *,
    compile_result: Optional[CompileResult] = None,
    check_double_blind: Optional[bool] = None,
) -> CheckReport:
    """Audit multi-file LaTeX project for consistency, citations, math syntax, and venue compliance."""
    ws = Path(meta.workspace_dir).resolve()
    structure = parse_project(ws, meta.main_file)
    issues: list[CheckIssue] = []
    double_blind = meta.double_blind if check_double_blind is None else check_double_blind

    # 1. Labels & References
    label_counts = Counter(l.key for l in structure.labels)
    for l in structure.labels:
        if label_counts[l.key] > 1:
            issues.append(CheckIssue(
                category="consistency", severity="error", file=l.file, line=l.line,
                title=f"重复定义的标签 \\label{{{l.key}}}",
                detail=f"标签 `{l.key}` 在工程中出现了 {label_counts[l.key]} 次，会导致交叉引用编号错乱。",
                suggestion="为不同章节或图表分配唯一前缀（如 fig:, tab:, eq:, sec:）。",
            ))

    label_keys = set(label_counts.keys())
    ref_keys = {r.key for r in structure.refs}
    for r in structure.refs:
        if r.key not in label_keys:
            issues.append(CheckIssue(
                category="consistency", severity="error", file=r.file, line=r.line,
                title=f"未定义的交叉引用 \\{r.command}{{{r.key}}}",
                detail=f"正文引用了 `{r.key}`，但所有已扫描的 .tex 文件中未找到对应的 \\label{{{r.key}}}。",
                suggestion="检查拼写或补充对应 \\label{}。",
            ))

    for l in structure.labels:
        if l.kind in {"figure", "table", "algorithm", "equation"} and l.key not in ref_keys:
            issues.append(CheckIssue(
                category="consistency", severity="warning", file=l.file, line=l.line,
                title=f"未被引用的图表/公式 \\label{{{l.key}}}",
                detail=f"{l.kind} 标签 `{l.key}` 定义后未在正文中通过 \\ref / \\eqref 引用。",
                suggestion="学术规范要求每个图表均应在正文中被显式讨论并引用。",
            ))

    # 2. Graphics existence
    for gfx in structure.graphics_files:
        found = False
        for ext in ("", ".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg"):
            cand = (ws / f"{gfx}{ext}").resolve()
            if cand.is_file() and cand.is_relative_to(ws):
                found = True
                break
        if not found:
            issues.append(CheckIssue(
                category="consistency", severity="error", file=structure.main_file, line=None,
                title=f"缺失图片资源: {gfx}",
                detail=f"正文中调用 \\includegraphics{{{gfx}}}，但工作区未找到对应文件。",
                suggestion="检查图片路径或上传对应图片文件。",
            ))

    # 3. Citations & BibTeX audit
    bib_entries = []
    for bib_rel in structure.bib_files:
        bib_path = (ws / bib_rel).resolve()
        if not bib_path.is_file():
            issues.append(CheckIssue(
                category="citation", severity="error", file=structure.main_file, line=None,
                title=f"缺失参考文献库: {bib_rel}",
                detail=f"工程声明了 {bib_rel}，但文件不存在。",
            ))
            continue
        parsed_bib = parse_bib(bib_path.read_text(encoding="utf-8", errors="replace"))
        bib_entries.extend(parsed_bib)
        for bi in validate_bib(parsed_bib):
            issues.append(CheckIssue(
                category="citation",
                severity="error" if bi["severity"] == "error" else "warning",
                file=bib_rel,
                line=bi.get("line"),
                title=f"BibTeX 规范问题: {bi['key']}",
                detail=bi["message"],
            ))

    bib_keys = {e.key for e in bib_entries}
    cited_keys: set[str] = set()
    for c in structure.cites:
        for k in c.keys:
            cited_keys.add(k)
            if bib_keys and k not in bib_keys:
                issues.append(CheckIssue(
                    category="citation", severity="error", file=c.file, line=c.line,
                    title=f"未定义的文献引用 \\{c.command}{{{k}}}",
                    detail=f"引用 Key `{k}` 不在当前项目的 .bib 文件中。",
                    suggestion="使用 DOI / arXiv ID 自动拉取或核对 Key 拼写。",
                ))
    for k in sorted(bib_keys - cited_keys):
        issues.append(CheckIssue(
            category="citation", severity="info", file=structure.bib_files[0] if structure.bib_files else "refs.bib",
            line=None, title=f"未被引用的文献条目: {k}",
            detail=f".bib 中的 `{k}` 在正文从未被 \\cite。",
        ))

    # 4. File-level math balance, acronyms, and double-blind checks
    acronym_counts: Counter[str] = Counter()
    acronym_first_loc: dict[str, tuple[str, int]] = {}
    acronym_defined: set[str] = set()
    ignore_acronyms = {"IEEE", "ACM", "CCF", "PDF", "URL", "DOI", "API", "GPU", "CPU", "RAM", "TPS", "RGB", "UTF", "SVG", "HTML", "XML", "HTTP", "HTTPS"}

    for rel in structure.included_files:
        fp = (ws / rel).resolve()
        if not fp.is_file():
            continue
        raw_text = fp.read_text(encoding="utf-8", errors="replace")
        lines = raw_text.splitlines()
        env_stack: list[tuple[str, int]] = []

        if double_blind:
            for am in _AUTHOR_BLOCK_RE.finditer(raw_text):
                author_body = am.group(1)
                if not re.search(r"anonymous|anonymized|双盲|匿名", author_body, re.IGNORECASE):
                    ln = raw_text.count("\n", 0, am.start()) + 1
                    issues.append(CheckIssue(
                        category="double_blind", severity="error", file=rel, line=ln,
                        title="双盲模式疑似泄露作者信息",
                        detail=f"\\author{{...}} 中未包含 Anonymous 标记: {author_body.strip()[:80]}",
                        suggestion="双盲投稿阶段请替换为 Anonymous Author(s) 或启用模板 anonymous 选项。",
                    ))

        for idx, raw_line in enumerate(lines, start=1):
            line = strip_comments(raw_line)
            if not line.strip():
                continue

            # Env balance
            for bm in _BEGIN_ENV_RE.finditer(line):
                env_stack.append((bm.group(1), idx))
            for em in _END_ENV_RE.finditer(line):
                ename = em.group(1)
                if not env_stack or env_stack[-1][0] != ename:
                    issues.append(CheckIssue(
                        category="math", severity="error", file=rel, line=idx,
                        title=f"环境不匹配: \\end{{{ename}}}",
                        detail=f"此处结束 \\end{{{ename}}} 与栈顶环境不一致。",
                    ))
                else:
                    env_stack.pop()

            # Unescaped inline $ count check (single-line)
            dollars = len(re.findall(r"(?<!\\)\$", line.replace("$$", "")))
            if dollars % 2 == 1 and "\\begin{" not in line:
                issues.append(CheckIssue(
                    category="math", severity="warning", file=rel, line=idx,
                    title="行内公式 $ 符号可能未成对闭合",
                    detail=line.strip()[:100],
                ))

            # Acronyms
            for ac_m in _ACRONYM_RE.finditer(line):
                ac = ac_m.group(1)
                if ac in ignore_acronyms:
                    continue
                acronym_counts[ac] += 1
                acronym_first_loc.setdefault(ac, (rel, idx))
                if f"({ac})" in line or f"（{ac}）" in line or f"\\acro{{{ac}}}" in line:
                    acronym_defined.add(ac)

            # Double-blind scans
            if double_blind:
                if _FUNDING_RE.search(line):
                    issues.append(CheckIssue(
                        category="double_blind", severity="error", file=rel, line=idx,
                        title="双盲模式疑似包含基金/致谢信息",
                        detail=line.strip()[:120],
                        suggestion="审稿版本应移除基金项目号与致谢段落。",
                    ))
                if _ACK_RE.search(line):
                    issues.append(CheckIssue(
                        category="double_blind", severity="warning", file=rel, line=idx,
                        title="双盲模式包含致谢章节",
                        detail=line.strip()[:100],
                    ))
                url_m = _PERSONAL_URL_RE.search(line)
                if url_m:
                    issues.append(CheckIssue(
                        category="double_blind", severity="warning", file=rel, line=idx,
                        title="双盲模式包含可能暴露身份的代码仓库链接",
                        detail=f"检测到仓库链接 `{url_m.group(0)}`。",
                        suggestion="建议使用匿名仓库（如 anonymous.4open.science）并在录用后再恢复真实地址。",
                    ))

        for ename, open_ln in env_stack:
            issues.append(CheckIssue(
                category="math", severity="error", file=rel, line=open_ln,
                title=f"未闭合的环境 \\begin{{{ename}}}",
                detail=f"第 {open_ln} 行开启的 `{ename}` 环境缺少对应的 \\end{{{ename}}}。",
            ))

    for ac, cnt in acronym_counts.items():
        if cnt >= 2 and ac not in acronym_defined:
            f_name, ln = acronym_first_loc[ac]
            issues.append(CheckIssue(
                category="acronym", severity="info", file=f_name, line=ln,
                title=f"缩略语 `{ac}` 首次出现未展开全称",
                detail=f"`{ac}` 共出现 {cnt} 次，首次出现于 {f_name}:{ln}，未检测到 `({ac})` 展开定义。",
            ))

    # 5. Layout / compile result integration
    if compile_result is not None:
        for ov in compile_result.overfulls:
            issues.append(CheckIssue(
                category="layout", severity="warning", file=ov.file, line=ov.line,
                title="排版溢出 (Overfull hbox/vbox)",
                detail=ov.message,
                suggestion="尝试改写长词、调整公式断行或表格列宽。",
            ))
        if meta.page_limit and compile_result.page_count and compile_result.page_count > meta.page_limit:
            issues.append(CheckIssue(
                category="layout", severity="error", file=structure.main_file, line=None,
                title=f"超出会议页数上限 ({compile_result.page_count} > {meta.page_limit} 页)",
                detail=f"当前编译生成 {compile_result.page_count} 页，超过目标限制 {meta.page_limit} 页。",
                suggestion="可使用 AI 语法保护精简功能压缩冗长段落。",
            ))

    word_count = count_project_words(ws, structure.included_files)
    summary = {
        "errors": sum(1 for i in issues if i.severity == "error"),
        "warnings": sum(1 for i in issues if i.severity == "warning"),
        "infos": sum(1 for i in issues if i.severity == "info"),
    }
    return CheckReport(
        ok=summary["errors"] == 0,
        summary=summary,
        word_count=word_count,
        issues=issues,
    )
