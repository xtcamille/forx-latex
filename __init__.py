"""forx-latex: Standalone AI-native LaTeX academic writing plugin for Hermes."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .ai_engine import converse_paper_project, generate_latex_snippet, heal_compile_errors, rewrite_latex_text
from .bibtex import (
    deduplicate_bib,
    fetch_bibtex_by_arxiv,
    fetch_bibtex_by_doi,
    format_bib_entry,
    format_bib_file,
    parse_bib,
    search_crossref,
    sync_from_bib_file,
)
from .checker import run_preflight_check
from .cli import run as cli_run, setup as cli_setup
from .compiler import (
    clean_auxiliary_files,
    compile_project,
    detect_compilers,
    export_submission_zip,
    install_tectonic,
)
from .project_parser import parse_project
from .storage import LatexStore, safe_resolve_in_workspace
from .templates import get_template_files, list_templates

PROJECT_MANAGE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "latex_project_manage",
        "description": "Manage LaTeX paper projects: list templates, create from IEEE/top-CS/CCF-blockchain templates, inspect structure/outline, read/write files, or manage snapshots.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_templates", "list_projects", "create", "link_dir", "structure", "read_file", "write_file", "snapshot", "list_snapshots", "restore_snapshot"],
                },
                "project_id": {"type": "string"},
                "name": {"type": "string"},
                "template_id": {"type": "string"},
                "title": {"type": "string"},
                "author": {"type": "string"},
                "workspace_dir": {"type": "string"},
                "rel_path": {"type": "string"},
                "content": {"type": "string"},
                "snapshot_id": {"type": "string"},
                "label": {"type": "string"},
            },
            "required": ["action"],
        },
    },
}

COMPILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "latex_compile",
        "description": "Compile a LaTeX project (supports Tectonic, latexmk, xelatex, pdflatex) and return structured diagnostics, page count, and SyncTeX status. Can also run AI auto-heal on errors.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "engine": {"type": "string", "enum": ["auto", "tectonic", "pdflatex", "xelatex", "lualatex"]},
                "auto_heal": {"type": "boolean", "description": "If compilation fails, automatically diagnose and propose/apply fixes."},
                "apply_heal": {"type": "boolean", "description": "Apply AI heal patches to disk and recompile once."},
            },
            "required": ["project_id"],
        },
    },
}

REWRITE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "latex_syntax_rewrite",
        "description": "Rewrite LaTeX prose (polish, zh2en, en2zh, compress, expand, deai) while strictly protecting citations, refs, labels, and math commands.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Raw LaTeX snippet to rewrite (or omit if project_id + rel_path are given)."},
                "project_id": {"type": "string"},
                "rel_path": {"type": "string"},
                "mode": {"type": "string", "enum": ["polish", "zh2en", "en2zh", "compress", "expand", "deai"]},
                "instruction": {"type": "string"},
                "target_words": {"type": "integer"},
                "apply": {"type": "boolean", "description": "When rewriting a project file, write back after integrity verification (creates automatic snapshot first)."},
            },
            "required": ["mode"],
        },
    },
}

BIB_SCHEMA = {
    "type": "function",
    "function": {
        "name": "latex_bib_manage",
        "description": "Manage BibTeX references: parse/list entries, fetch by DOI or arXiv ID, search Crossref literature, deduplicate/format, or sync from a Zotero .bib export.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "fetch_doi", "fetch_arxiv", "search", "dedup", "sync_file"]},
                "project_id": {"type": "string"},
                "bib_file": {"type": "string", "description": "Relative .bib path (default refs.bib)."},
                "query": {"type": "string", "description": "DOI, arXiv ID, or search keywords."},
                "source_path": {"type": "string", "description": "External .bib path for Zotero sync."},
                "append": {"type": "boolean", "description": "Append fetched BibTeX entry directly to project .bib."},
            },
            "required": ["action"],
        },
    },
}

CHECK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "latex_preflight_check",
        "description": "Run consistency, citation, math balance, acronym, double-blind anonymity, and layout/page-limit pre-flight audit on a LaTeX project, or export a clean arXiv/submission ZIP.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "double_blind": {"type": "boolean"},
                "clean_aux": {"type": "boolean"},
                "export_zip_path": {"type": "string"},
            },
            "required": ["project_id"],
        },
    },
}

GENERATE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "latex_generate_snippet",
        "description": "Generate LaTeX formulas, booktabs tables (from CSV/Markdown or prompt), algorithm2e pseudocode, or TikZ diagrams.",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["formula", "table", "tikz", "algorithm", "section"]},
                "input": {"type": "string", "description": "CSV/Markdown data or natural language specification."},
                "caption": {"type": "string"},
                "label": {"type": "string"},
            },
            "required": ["kind", "input"],
        },
    },
}

SETUP_COMPILER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "latex_setup_compiler",
        "description": "Inspect available TeX compilers or install standalone Tectonic compiler locally (requires no TeX Live / MiKTeX).",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["status", "install_tectonic"]},
            },
            "required": ["action"],
        },
    },
}

PROJECT_CHAT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "latex_project_chat",
        "description": "Have an interactive AI co-author conversation about a specific LaTeX paper project. Grounds responses in research materials (experimental data, notes) and generates concrete code patches/sections.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "prompt": {"type": "string", "description": "Instruction or question about the paper."},
                "active_file": {"type": "string", "description": "Relative path of the target file being edited."},
                "cursor_line": {"type": "integer", "description": "Target line number in the active file."},
                "referenced_materials": {"type": "array", "items": {"type": "string"}, "description": "Relative paths of data/notes in materials/ or project."},
                "auto_apply": {"type": "boolean", "description": "Immediately apply proposed patches to project files (with snapshot backup)."},
            },
            "required": ["project_id", "prompt"],
        },
    },
}



def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=lambda x: x.model_dump() if hasattr(x, "model_dump") else str(x))


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _handle_project_manage(args: dict[str, Any]) -> str:
    store = LatexStore()
    action = args["action"]
    if action == "list_templates":
        return _dump([t.model_dump() for t in list_templates()])
    if action == "list_projects":
        return _dump([p.model_dump() for p in store.list_projects()])
    if action == "create":
        tid = args.get("template_id") or "ieee-conf"
        meta, files = get_template_files(
            tid,
            title=args.get("title") or args.get("name") or "Untitled Paper",
            author=args.get("author") or "Anonymous Author(s)",
        )
        proj = store.create_project(
            name=args.get("name") or meta.name,
            template_id=tid,
            files=files,
            main_file=meta.main_file,
            engine=meta.recommended_engine,
            venue_preset=meta.category,
            page_limit=meta.page_limit,
            double_blind=meta.double_blind,
        )
        return _dump({"project": proj.model_dump(), "files": sorted(files.keys())})
    if action == "link_dir":
        ws = Path(args["workspace_dir"]).expanduser().resolve()
        proj = store.create_project(name=args.get("name") or ws.name, workspace_dir=ws, template_id="linked")
        return _dump(proj.model_dump())

    pid = args["project_id"]
    if action == "structure":
        proj = store.get_project(pid)
        return _dump(parse_project(Path(proj.workspace_dir), proj.main_file).model_dump())
    if action == "read_file":
        return _dump({"path": args["rel_path"], "content": store.read_file(pid, args["rel_path"])})
    if action == "write_file":
        proj = store.write_file(pid, args["rel_path"], args["content"], snapshot_label=args.get("label") or "Agent 编辑")
        return _dump({"ok": True, "project": proj.model_dump()})
    if action == "snapshot":
        return _dump(store.create_snapshot(pid, label=args.get("label") or "Agent 快照").model_dump())
    if action == "list_snapshots":
        return _dump([s.model_dump() for s in store.list_snapshots(pid)])
    if action == "restore_snapshot":
        return _dump(store.restore_snapshot(pid, args["snapshot_id"]).model_dump())
    raise ValueError(f"不支持的 action: {action}")


def _make_compile_handler(ctx: Any):
    def _handle(args: dict[str, Any]) -> str:
        store = LatexStore()
        meta = store.get_project(args["project_id"])
        res = compile_project(meta, engine=args.get("engine", "auto"))
        out: dict[str, Any] = {"compile": res.model_dump()}
        if not res.ok and args.get("auto_heal"):
            heal = _run_async(heal_compile_errors(store, meta, res, apply_patches=bool(args.get("apply_heal")), client=ctx.llm))
            out["heal"] = heal
            if args.get("apply_heal") and heal.get("applied_files"):
                out["recompile"] = compile_project(meta, engine=args.get("engine", "auto")).model_dump()
        return _dump(out)
    return _handle


def _make_rewrite_handler(ctx: Any):
    def _handle(args: dict[str, Any]) -> str:
        store = LatexStore()
        pid = args.get("project_id")
        rel_path = args.get("rel_path")
        text = args.get("text")
        if text is None and pid and rel_path:
            text = store.read_file(pid, rel_path)
        if not text:
            raise ValueError("需要提供 text 或 (project_id + rel_path)")
        res = _run_async(rewrite_latex_text(
            text,
            mode=args.get("mode", "polish"),
            instruction=args.get("instruction", ""),
            target_words=args.get("target_words"),
            filename=rel_path or "snippet.tex",
            client=ctx.llm,
        ))
        data = res.model_dump()
        if args.get("apply") and res.integrity_ok and pid and rel_path:
            proj = store.write_file(pid, rel_path, res.rewritten_text, snapshot_label=f"AI {args.get('mode', 'polish')} 改写前备份")
            data["applied"] = True
            data["revision"] = proj.revision
        return _dump(data)
    return _handle


def _handle_bib_manage(args: dict[str, Any]) -> str:
    store = LatexStore()
    action = args["action"]
    pid = args.get("project_id")
    bib_rel = args.get("bib_file") or "refs.bib"

    if action == "search":
        return _dump({"results": search_crossref(args["query"])})
    if action in {"fetch_doi", "fetch_arxiv"}:
        entry = fetch_bibtex_by_doi(args["query"]) if action == "fetch_doi" else fetch_bibtex_by_arxiv(args["query"])
        formatted = format_bib_entry(entry)
        appended = False
        if pid and args.get("append"):
            meta = store.get_project(pid)
            bib_path = safe_resolve_in_workspace(Path(meta.workspace_dir), bib_rel)
            existing = bib_path.read_text(encoding="utf-8", errors="replace") if bib_path.is_file() else ""
            entries = parse_bib(existing)
            entries.append(entry)
            kept, _ = deduplicate_bib(entries)
            store.write_file(pid, bib_rel, format_bib_file(kept), snapshot_label=f"添加文献 {entry.key}")
            appended = True
        return _dump({"entry": entry.model_dump(), "bibtex": formatted, "appended": appended})

    if not pid:
        raise ValueError("此操作需要 project_id")
    meta = store.get_project(pid)
    bib_path = safe_resolve_in_workspace(Path(meta.workspace_dir), bib_rel)
    if action == "list":
        if not bib_path.is_file():
            return _dump({"entries": []})
        return _dump({"entries": [e.model_dump() for e in parse_bib(bib_path.read_text(encoding="utf-8", errors="replace"))]})
    if action == "dedup":
        if not bib_path.is_file():
            return _dump({"removed": [], "total": 0})
        entries = parse_bib(bib_path.read_text(encoding="utf-8", errors="replace"))
        kept, removed = deduplicate_bib(entries)
        store.write_file(pid, bib_rel, format_bib_file(kept), snapshot_label="BibTeX 去重格式化")
        return _dump({"removed": removed, "total": len(kept)})
    if action == "sync_file":
        res = sync_from_bib_file(Path(args["source_path"]).expanduser(), bib_path)
        store.bump_revision(pid)
        return _dump(res)
    raise ValueError(f"未知 action: {action}")


def _handle_preflight_check(args: dict[str, Any]) -> str:
    store = LatexStore()
    meta = store.get_project(args["project_id"])
    ws = Path(meta.workspace_dir)
    if args.get("clean_aux"):
        return _dump({"cleaned": clean_auxiliary_files(ws)})
    if args.get("export_zip_path"):
        return _dump(export_submission_zip(ws, Path(args["export_zip_path"]).expanduser().resolve(), main_file=meta.main_file))
    report = run_preflight_check(meta, check_double_blind=args.get("double_blind"))
    return _dump(report.model_dump())


def _make_generate_handler(ctx: Any):
    def _handle(args: dict[str, Any]) -> str:
        res = _run_async(generate_latex_snippet(
            args["kind"],
            args["input"],
            caption=args.get("caption") or "Experimental Results",
            label=args.get("label") or "tab:results",
            client=ctx.llm,
        ))
        return _dump(res)
    return _handle


def _make_project_chat_handler(ctx: Any):
    def _handle(args: dict[str, Any]) -> str:
        store = LatexStore()
        res = _run_async(converse_paper_project(
            store,
            args["project_id"],
            args["prompt"],
            active_file=args.get("active_file"),
            cursor_line=args.get("cursor_line"),
            referenced_materials=args.get("referenced_materials"),
            auto_apply=bool(args.get("auto_apply")),
            client=ctx.llm,
        ))
        return _dump(res)
    return _handle



def _handle_setup_compiler(args: dict[str, Any]) -> str:
    if args["action"] == "install_tectonic":
        return _dump(install_tectonic())
    return _dump(detect_compilers())


def _slash_handler(raw_args: str) -> str:
    parts = (raw_args or "").strip().split()
    store = LatexStore()
    if not parts:
        comp = detect_compilers()
        projects = store.list_projects()
        eng = comp["active_engine"] or "未安装（可运行 `hermes latex setup` 一键安装 Tectonic）"
        return (
            f"**LaTeX 论文工坊 (`forx-latex`)**\n\n"
            f"- 编译引擎状态: `{eng}`\n"
            f"- 已有项目数: `{len(projects)}` | 内置模板: `{len(list_templates())}` 个（IEEE / 顶会 / CCF区块链专委会期刊）\n"
            f"- 快捷命令: `/latex templates`, `/latex list`, `/latex setup`, `/latex check <project_id>`"
        )
    sub = parts[0].lower()
    if sub == "templates":
        lines = [f"- `{t.id}`: {t.name}" for t in list_templates()]
        return "**内置学术模板：**\n" + "\n".join(lines)
    if sub == "list":
        projs = store.list_projects()
        if not projs:
            return "暂无 LaTeX 项目。可用 `hermes latex init --template ieee-conf --name MyPaper` 创建。"
        return "\n".join(f"- `{p.id}` | {p.name} (r{p.revision}, `{p.template_id}`)" for p in projs)
    if sub == "setup":
        return _dump(install_tectonic())
    if sub == "check" and len(parts) >= 2:
        meta = store.get_project(parts[1])
        rep = run_preflight_check(meta)
        return f"体检结果: errors={rep.summary['errors']}, warnings={rep.summary['warnings']}, words={rep.word_count['total_units']}"
    return "未知子命令。支持 `templates`, `list`, `setup`, `check <project_id>`。"


def register(ctx: Any) -> None:
    ctx.register_cli_command(
        name="latex",
        help="Manage, compile, rewrite, and audit academic LaTeX papers",
        setup_fn=cli_setup,
        handler_fn=lambda args: cli_run(args, ctx.llm),
    )
    ctx.register_command(
        name="latex",
        handler=_slash_handler,
        description="Inspect LaTeX templates, projects, compiler status, and pre-flight checks",
        args_hint="[templates|list|setup|check <project_id>]",
    )

    tools = [
        ("latex_project_manage", PROJECT_MANAGE_SCHEMA, _handle_project_manage, "Manage LaTeX paper projects, templates, files, and snapshots."),
        ("latex_compile", COMPILE_SCHEMA, _make_compile_handler(ctx), "Compile LaTeX projects and run AI auto-heal on errors."),
        ("latex_syntax_rewrite", REWRITE_SCHEMA, _make_rewrite_handler(ctx), "Syntax-protected academic LaTeX rewriting and page compression."),
        ("latex_bib_manage", BIB_SCHEMA, _handle_bib_manage, "Parse, fetch (DOI/arXiv), search, deduplicate, and sync BibTeX libraries."),
        ("latex_preflight_check", CHECK_SCHEMA, _handle_preflight_check, "Audit consistency, citations, double-blind anonymity, and export submission archives."),
        ("latex_generate_snippet", GENERATE_SCHEMA, _make_generate_handler(ctx), "Generate booktabs tables, equations, pseudocode, and TikZ diagrams."),
        ("latex_setup_compiler", SETUP_COMPILER_SCHEMA, _handle_setup_compiler, "Detect TeX compilers or install standalone Tectonic engine."),
        ("latex_project_chat", PROJECT_CHAT_SCHEMA, _make_project_chat_handler(ctx), "Interactive AI co-author conversation scoped to a LaTeX paper project."),
    ]
    for name, schema, handler, desc in tools:
        ctx.register_tool(name=name, toolset="latex", schema=schema, handler=handler, description=desc)

    skill_path = Path(__file__).parent / "skills" / "forx-latex" / "SKILL.md"
    if skill_path.exists():
        ctx.register_skill(
            name="forx-latex",
            path=skill_path,
            description="End-to-end academic LaTeX workflow: templates, compilation, syntax-protected rewriting, BibTeX, and pre-flight audit.",
        )
