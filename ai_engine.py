"""Host-LLM powered academic LaTeX engine: syntax-protected rewrite, compile auto-heal, table/formula/TikZ generation."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from .models import CompileResult, ProjectChatPlan, ProjectFilePatch, ProjectMeta, RewriteResult
from .storage import LatexStore
from .syntax_guard import compute_unified_diff, protect_latex_tokens, restore_latex_tokens

_REWRITE_PROMPTS = {
    "polish": "你是顶级计算机与区块链期刊审稿人兼英文学术润色专家。请对下方文本进行学术润色，提升专业性、简洁性与连贯性。",
    "zh2en": "你是计算机顶会学术翻译专家。请将下方中文论文草稿翻译为地道、紧凑、符合 IEEE/ACM 风格的学术英文。",
    "en2zh": "你是中文计算机核心期刊编辑。请将下方英文学术文本精准译为规范的中文学术表达。",
    "compress": "你是资深顶会作者，擅长在保持所有核心论点、实验数字与技术细节的前提下，大幅压缩文字冗余以减少篇幅。",
    "expand": "你是资深学术合作者，请根据上下文补充严谨的技术阐述与过渡句，使论证更饱满。",
    "deai": "请去除文本中常见的模板化 AI 腔（如空洞套话、过度排比与同义反复），使表达更像一线研究者亲笔撰写。",
}


class HealPatch(BaseModel):
    file: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    replacement: str
    explanation: str = ""


class HealPlan(BaseModel):
    summary: str
    patches: list[HealPatch] = Field(default_factory=list)


def get_llm(client: Any = None):
    if client is not None:
        return client
    from agent.plugin_llm import PluginLlm
    return PluginLlm(plugin_id="hermes-latex")


def csv_to_booktabs(raw_csv: str, *, caption: str = "Experimental Results", label: str = "tab:results", highlight_best: str = "none") -> str:
    """Deterministic CSV/TSV/Markdown-table -> LaTeX booktabs table converter (works offline without LLM)."""
    text = raw_csv.strip()
    if not text:
        raise ValueError("输入表格数据为空")

    rows: list[list[str]] = []
    if "|" in text.splitlines()[0]:
        for line in text.splitlines():
            s = line.strip()
            if not s or set(s.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            rows.append(cells)
    else:
        dialect = csv.Sniffer().sniff(text[:1024], delimiters=",\t;") if any(d in text for d in (",\t;")) else None
        reader = csv.reader(io.StringIO(text), dialect) if dialect else csv.reader(io.StringIO(text))
        rows = [[c.strip() for c in r] for r in reader if any(c.strip() for c in r)]

    if len(rows) < 2:
        raise ValueError("表格至少需要包含表头与一行数据")

    ncols = max(len(r) for r in rows)
    norm_rows = [r + [""] * (ncols - len(r)) for r in rows]

    # Optional best numeric bolding per column (skip col 0)
    if highlight_best in {"max", "min"}:
        for col in range(1, ncols):
            nums: list[tuple[int, float]] = []
            for r_idx in range(1, len(norm_rows)):
                cleaned = norm_rows[r_idx][col].replace(",", "").replace("%", "").strip()
                try:
                    nums.append((r_idx, float(cleaned)))
                except ValueError:
                    pass
            if nums:
                best_row = max(nums, key=lambda x: x[1])[0] if highlight_best == "max" else min(nums, key=lambda x: x[1])[0]
                norm_rows[best_row][col] = f"\\textbf{{{norm_rows[best_row][col]}}}"

    col_spec = "l" + "c" * max(0, ncols - 1)
    header = " & ".join(norm_rows[0]) + r" \\"
    body_lines = ["    " + " & ".join(r) + r" \\" for r in norm_rows[1:]]
    return "\n".join([
        r"\begin{table}[htbp]",
        r"  \centering",
        f"  \\caption{{{caption}}}",
        f"  \\label{{{label}}}",
        f"  \\begin{{tabular}}{{{col_spec}}}",
        r"    \toprule",
        f"    {header}",
        r"    \midrule",
        *body_lines,
        r"    \bottomrule",
        r"  \end{tabular}",
        r"\end{table}",
    ])


async def rewrite_latex_text(
    text: str,
    *,
    mode: str = "polish",
    instruction: str = "",
    target_words: Optional[int] = None,
    filename: str = "section.tex",
    client: Any = None,
) -> RewriteResult:
    """Rewrite LaTeX prose while protecting citations, labels, math, and commands via placeholders."""
    protected = protect_latex_tokens(text)
    base_inst = _REWRITE_PROMPTS.get(mode, _REWRITE_PROMPTS["polish"])
    extra = []
    if target_words:
        extra.append(f"目标篇幅控制在约 {target_words} 词以内。")
    if instruction:
        extra.append(f"用户附加要求：{instruction}")
    extra.append(
        "【硬性约束】文本中的 [[LTX_0001]] 等占位符代表 LaTeX 引用/公式/标签/结构命令，"
        "必须原封不动保留每个占位符及其编号，不得删除、改写或拆散占位符。只输出改写后的文本正文，不要包裹 Markdown 代码块。"
    )

    llm = get_llm(client)
    res = await llm.acomplete(
        instructions=f"{base_inst}\n" + "\n".join(extra),
        input=[{"type": "text", "text": protected.masked_text}],
        temperature=0.2,
        max_tokens=4096,
        purpose=f"latex.rewrite.{mode}",
    )
    raw_out = (res.text or "").strip()
    if raw_out.startswith("```"):
        lines = raw_out.splitlines()
        if len(lines) >= 2 and lines[-1].strip().startswith("```"):
            raw_out = "\n".join(lines[1:-1]).strip()

    restored, integrity_ok, integrity_errors = restore_latex_tokens(raw_out, protected)
    diff = compute_unified_diff(text, restored, filename=filename)
    return RewriteResult(
        ok=integrity_ok,
        mode=mode,
        original_text=text,
        rewritten_text=restored,
        diff=diff,
        preserved_tokens=len(protected.tokens),
        integrity_ok=integrity_ok,
        integrity_errors=integrity_errors,
    )


async def heal_compile_errors(
    store: LatexStore,
    meta: ProjectMeta,
    compile_result: CompileResult,
    *,
    apply_patches: bool = False,
    client: Any = None,
) -> dict[str, Any]:
    """Use host LLM to diagnose LaTeX compile errors and propose (or apply) minimal patches."""
    if compile_result.ok or not compile_result.errors:
        return {"ok": True, "summary": "当前工程无编译错误，无需修复。", "patches": [], "applied": False}

    ws = Path(meta.workspace_dir).resolve()
    context_blocks: list[str] = []
    seen_files: set[str] = set()
    for err in compile_result.errors[:6]:
        fname = err.file or meta.main_file
        if fname in seen_files:
            continue
        seen_files.add(fname)
        target = (ws / fname).resolve()
        if target.is_file() and target.is_relative_to(ws):
            numbered = "\n".join(
                f"{idx}: {ln}"
                for idx, ln in enumerate(target.read_text(encoding="utf-8", errors="replace").splitlines(), start=1)
            )
            context_blocks.append(f"=== 文件 {fname} ===\n{numbered[:12000]}")

    payload = {
        "engine": compile_result.engine_used,
        "errors": [e.model_dump() for e in compile_result.errors[:8]],
        "log_tail": compile_result.raw_log_tail[-3000:],
        "files": "\n\n".join(context_blocks),
    }

    llm = get_llm(client)
    res = await llm.acomplete_structured(
        instructions=(
            "你是 LaTeX 编译排错专家。根据结构化报错与源码行号，给出最小精准修复补丁。"
            "只修改引发编译失败的最小行区间，严禁删改无关正文内容。"
        ),
        input=[{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        json_schema=HealPlan.model_json_schema(),
        schema_name="hermes_latex_heal",
        temperature=0,
        max_tokens=4000,
        purpose="latex.heal",
    )
    if res.parsed is None:
        return {"ok": False, "summary": "模型未返回有效修复补丁", "patches": [], "applied": False}

    plan = HealPlan.model_validate(res.parsed)
    diffs: list[dict[str, Any]] = []
    applied_files: list[str] = []

    if apply_patches and plan.patches:
        store.create_snapshot(meta.id, label="AI 编译自愈前自动备份")

    # Apply patches per file from bottom line to top line to preserve line numbers
    by_file: dict[str, list[HealPatch]] = {}
    for p in plan.patches:
        by_file.setdefault(p.file, []).append(p)

    for rel, patches in by_file.items():
        original = store.read_file(meta.id, rel)
        lines = original.splitlines()
        for patch in sorted(patches, key=lambda x: x.line_start, reverse=True):
            start = max(0, patch.line_start - 1)
            end = min(len(lines), patch.line_end)
            rep_lines = patch.replacement.splitlines()
            lines[start:end] = rep_lines
        updated = "\n".join(lines) + ("\n" if original.endswith("\n") else "")
        diffs.append({"file": rel, "diff": compute_unified_diff(original, updated, filename=rel)})
        if apply_patches:
            store.write_file(meta.id, rel, updated)
            applied_files.append(rel)

    return {
        "ok": True,
        "summary": plan.summary,
        "patches": [p.model_dump() for p in plan.patches],
        "diffs": diffs,
        "applied": apply_patches,
        "applied_files": applied_files,
    }


async def generate_latex_snippet(
    kind: str,
    prompt_or_data: str,
    *,
    caption: str = "Generated Result",
    label: str = "fig:generated",
    image_bytes: Optional[bytes] = None,
    image_mime: str = "image/png",
    client: Any = None,
) -> dict[str, Any]:
    """Generate formula, booktabs table, algorithm pseudocode, or TikZ/PGFPlots code."""
    if kind == "table" and ("," in prompt_or_data or "\t" in prompt_or_data or "|" in prompt_or_data):
        try:
            code = csv_to_booktabs(prompt_or_data, caption=caption, label=label if label.startswith("tab:") else "tab:results")
            return {"ok": True, "kind": "table", "code": code, "offline": True}
        except ValueError:
            pass

    kind_guides = {
        "formula": "输出标准 LaTeX equation/align 公式代码（如需要可附简短符号说明，但代码用 ```latex 包裹或纯代码）。",
        "table": "输出使用 booktabs (\\toprule, \\midrule, \\bottomrule) 的规范学术三线表。",
        "tikz": "输出可独立编译的学术矢量架构图/流程图 TikZ 代码（仅使用标准 tikz 库 shapes.geometric, arrows.meta, positioning, calc）。",
        "algorithm": "输出使用 algorithm2e 风格的规范伪代码环境。",
        "section": "根据研究要点起草学术论文章节 LaTeX 代码，规范使用 \\label 与 \\cite 占位。",
    }
    guide = kind_guides.get(kind, kind_guides["formula"])
    inputs: list[dict[str, Any]] = [{"type": "text", "text": f"任务类型: {kind}\n要求/数据:\n{prompt_or_data}"}]
    if image_bytes:
        import base64
        inputs.append({
            "type": "image",
            "data": base64.b64encode(image_bytes).decode("ascii"),
            "mime_type": image_mime,
        })

    llm = get_llm(client)
    res = await llm.acomplete(
        instructions=f"你是顶会 LaTeX 代码生成专家。{guide} 只返回可直接嵌入论文的干净 LaTeX 代码。",
        input=inputs,
        temperature=0.2,
        max_tokens=3000,
        purpose=f"latex.generate.{kind}",
    )
    code = (res.text or "").strip()
    if code.startswith("```"):
        lines = code.splitlines()
        if len(lines) >= 2 and lines[-1].strip().startswith("```"):
            code = "\n".join(lines[1:-1]).strip()
    return {"ok": True, "kind": kind, "code": code, "offline": False}


async def converse_paper_project(
    store: LatexStore,
    project_id: str,
    prompt: str,
    *,
    active_file: Optional[str] = None,
    cursor_line: Optional[int] = None,
    selection_text: Optional[str] = None,
    referenced_materials: Optional[list[str]] = None,
    auto_apply: bool = False,
    client: Any = None,
) -> dict[str, Any]:
    """Conversational AI academic co-author: scoped strictly to the current paper project."""
    meta = store.get_project(project_id)
    ws = Path(meta.workspace_dir).resolve()

    # 1. Outline and citation context
    from .project_parser import parse_project
    structure = parse_project(ws, meta.main_file)

    outline_summary = [
        f"L{node.line} [{node.kind.upper()}] {node.title} (file: {node.file})"
        for node in structure.outline[:30]
    ]
    known_cites = sorted(set(structure.cites and [k for c in structure.cites for k in c.keys] or []))[:40]
    known_labels = [lbl.key for lbl in structure.labels[:40]]

    # 2. Material content (evidence grounding)
    materials_context: list[str] = []
    mat_list = referenced_materials or []
    if not mat_list:
        # Auto-detect mentioned files or top files in materials/
        for mat in store.list_materials(project_id)[:4]:
            mat_list.append(mat.path)

    for rel in mat_list[:5]:
        try:
            target = ws / rel
            if target.is_file() and target.is_relative_to(ws):
                snippet = target.read_text(encoding="utf-8", errors="replace")[:6000]
                materials_context.append(f"=== 参考资料: {rel} ===\n{snippet}")
        except Exception:
            pass

    # 3. Active file and selection context
    target_rel = active_file or meta.main_file
    active_content = ""
    numbered_lines = ""
    try:
        active_target = ws / target_rel
        if active_target.is_file() and active_target.is_relative_to(ws):
            active_content = active_target.read_text(encoding="utf-8", errors="replace")
            all_lines = active_content.splitlines()
            # If cursor line is provided, window around cursor (or whole file if small)
            if len(all_lines) <= 250:
                numbered_lines = "\n".join(f"{idx}: {ln}" for idx, ln in enumerate(all_lines, start=1))
            else:
                cur = cursor_line or 1
                start = max(1, cur - 60)
                end = min(len(all_lines), cur + 60)
                numbered_lines = f"[总行数: {len(all_lines)}，截取第 {start} 至 {end} 行]\n" + "\n".join(
                    f"{idx}: {ln}" for idx, ln in enumerate(all_lines[start - 1:end], start=start)
                )
    except Exception:
        pass

    # 4. Recent project chat history
    recent_msgs = store.list_chat_messages(project_id, limit=6)
    history_blocks = [
        f"[{m.role.upper()}]: {m.text}" + (f"\n(附带修改补丁: {len(m.patches)} 项)" if m.patches else "")
        for m in recent_msgs
    ]

    # Save user message to store
    store.add_chat_message(
        project_id,
        role="user",
        text=prompt,
        attachments=mat_list,
        active_file=target_rel,
    )

    payload = {
        "project": {
            "name": meta.name,
            "template": meta.template_id,
            "engine": meta.engine,
            "main_file": meta.main_file,
        },
        "outline": outline_summary,
        "available_cites": known_cites,
        "available_labels": known_labels,
        "referenced_materials": "\n\n".join(materials_context) if materials_context else "(无外部参考资料)",
        "active_file": {
            "path": target_rel,
            "cursor_line": cursor_line,
            "selection_text": selection_text or "",
            "numbered_code": numbered_lines,
        },
        "recent_conversation": history_blocks,
        "user_instruction": prompt,
    }

    instructions = (
        "你是顶级计算机与区块链学术同行评审兼 LaTeX 合作创作者 (Academic LaTeX Co-Author)。\n"
        "你的任务：针对当前论文工程，与作者进行深入学术交流，并根据作者指令、参考资料（实验数据/提纲/设计笔记）、"
        "当前正在编辑的文件，提出严谨、地道的学术修改方案或补丁。\n\n"
        "【学术写作规范】\n"
        "1. 严格以提供的参考资料（实验数据、架构提纲）为客观事实依据，严禁凭空捏造实验指标与虚假数值。\n"
        "2. 语言遵循 IEEE Transactions / ACM / CCF-A 规范：行文肯定自信（Assertive）、逻辑环环相扣，去除套话 AI 腔。\n"
        "3. 遇到已有引用或标签时，尽量复用已知列表中的 \\cite{...} 与 \\ref{...}。\n"
        "4. 若用户需要修改或增加论文正文：请在 patches 列表中给出精准的修改补丁（明确标注 file, line_start, line_end 或 action='replace_range' / 'insert_cursor' / 'replace_file'）。\n"
        "5. 若用户仅进行学术咨询、提问或讨论大纲，patches 可为空列表。\n"
        "6. 输出 JSON 结构必须符合 ProjectChatPlan 模式。"
    )

    llm = get_llm(client)
    try:
        res = await llm.acomplete_structured(
            instructions=instructions,
            input=[{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            json_schema=ProjectChatPlan.model_json_schema(),
            schema_name="hermes_latex_project_chat",
            temperature=0.1,
            max_tokens=5000,
            purpose="latex.project.chat",
        )
        if res.parsed is not None:
            plan = ProjectChatPlan.model_validate(res.parsed)
        else:
            plan = ProjectChatPlan(message=res.text or "已收到您的需求，未产生具体的代码修改。")
    except Exception as err:
        plan = ProjectChatPlan(
            message=f"⚠️ 模型调用异常 ({err})。请检查网络或在左下角设置中检查大模型连接状态。"
        )

    # Compute diff for patches
    diff_blocks: list[str] = []
    patches_to_apply = plan.patches

    # Group patches by file
    by_file: dict[str, list[ProjectFilePatch]] = {}
    for p in patches_to_apply:
        by_file.setdefault(p.file or target_rel, []).append(p)

    modified_files: dict[str, str] = {}
    for f_rel, f_patches in by_file.items():
        try:
            original = store.read_file(project_id, f_rel)
        except Exception:
            original = ""
        lines = original.splitlines()

        for patch in sorted(f_patches, key=lambda x: x.line_start or 1, reverse=True):
            rep_lines = patch.replacement.splitlines()
            if patch.action == "replace_file" or not original:
                lines = rep_lines
            elif patch.action == "insert_cursor" and patch.line_start:
                pos = min(len(lines), max(0, patch.line_start))
                lines[pos:pos] = rep_lines
            elif patch.line_start and patch.line_end:
                s = max(0, patch.line_start - 1)
                e = min(len(lines), patch.line_end)
                lines[s:e] = rep_lines
            else:
                lines.extend(rep_lines)

        updated = "\n".join(lines) + ("\n" if original.endswith("\n") or not original else "")
        diff = compute_unified_diff(original, updated, filename=f_rel)
        if diff.strip():
            diff_blocks.append(diff)
            modified_files[f_rel] = updated

    combined_diff = "\n\n".join(diff_blocks) if diff_blocks else None

    # Auto apply if requested and patches exist
    applied = False
    if auto_apply and modified_files:
        store.create_snapshot(project_id, label=f"AI 对话修改: {prompt[:25]}")
        for f_rel, content in modified_files.items():
            store.write_file(project_id, f_rel, content)
        store.bump_revision(project_id)
        applied = True

    # Record assistant message
    asst_msg = store.add_chat_message(
        project_id,
        role="assistant",
        text=plan.message or plan.clarification or "修改建议已就绪。",
        active_file=target_rel,
        patches=[p.model_dump() for p in plan.patches],
        diff=combined_diff,
        applied=applied,
    )

    return {
        "ok": True,
        "message": asst_msg.text,
        "clarification": plan.clarification,
        "patches": [p.model_dump() for p in plan.patches],
        "diff": combined_diff,
        "applied": applied,
        "message_id": asst_msg.id,
    }


def apply_chat_patches(store: LatexStore, project_id: str, message_id: str) -> dict[str, Any]:
    """Apply previously proposed patches from a specific assistant chat message."""
    msg = store.get_chat_message(message_id)
    if not msg:
        raise KeyError(f"未找到对话消息: {message_id}")
    if msg.applied:
        return {"ok": True, "applied": True, "already_applied": True}
    if not msg.patches:
        return {"ok": True, "applied": False, "message": "该消息无代码修改补丁"}

    by_file: dict[str, list[ProjectFilePatch]] = {}
    for p in msg.patches:
        by_file.setdefault(p.file, []).append(p)

    store.create_snapshot(project_id, label=f"采纳对话修改 ({msg.text[:20]})")
    for f_rel, f_patches in by_file.items():
        try:
            original = store.read_file(project_id, f_rel)
        except Exception:
            original = ""
        lines = original.splitlines()
        for patch in sorted(f_patches, key=lambda x: x.line_start or 1, reverse=True):
            rep_lines = patch.replacement.splitlines()
            if patch.action == "replace_file" or not original:
                lines = rep_lines
            elif patch.action == "insert_cursor" and patch.line_start:
                pos = min(len(lines), max(0, patch.line_start))
                lines[pos:pos] = rep_lines
            elif patch.line_start and patch.line_end:
                s = max(0, patch.line_start - 1)
                e = min(len(lines), patch.line_end)
                lines[s:e] = rep_lines
            else:
                lines.extend(rep_lines)
        updated = "\n".join(lines) + ("\n" if original.endswith("\n") or not original else "")
        store.write_file(project_id, f_rel, updated)

    store.mark_chat_message_applied(message_id, True)
    store.bump_revision(project_id)
    return {"ok": True, "applied": True, "updated_files": list(by_file.keys())}

