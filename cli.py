"""CLI subcommand `hermes latex <action>` for academic LaTeX workflows."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .ai_engine import converse_paper_project, generate_latex_snippet, rewrite_latex_text
from .bibtex import deduplicate_bib, fetch_bibtex_by_arxiv, fetch_bibtex_by_doi, format_bib_file, parse_bib, search_crossref, sync_from_bib_file
from .checker import run_preflight_check
from .compiler import clean_auxiliary_files, compile_project, detect_compilers, export_submission_zip, install_tectonic
from .project_parser import parse_project
from .storage import LatexStore, safe_resolve_in_workspace
from .templates import get_template_files, list_templates


def setup(parser) -> None:
    parser.add_argument(
        "action",
        choices=["templates", "init", "link", "list", "structure", "build", "clean", "check", "bib", "rewrite", "generate", "chat", "materials", "snapshot", "export", "setup", "doctor"],
        help="LaTeX subcommand action",
    )
    parser.add_argument("--project", help="Project ID")
    parser.add_argument("--template", default="ieee-conf", help="Template ID for init")
    parser.add_argument("--name", help="Project name or paper title")
    parser.add_argument("--author", default="Anonymous Author(s)", help="Author string")
    parser.add_argument("--dir", help="Local workspace path for link")
    parser.add_argument("--file", help="Relative .tex / .bib file path")
    parser.add_argument("--engine", default="auto", choices=["auto", "tectonic", "pdflatex", "xelatex", "lualatex"])
    parser.add_argument("--doi", help="DOI to fetch BibTeX")
    parser.add_argument("--arxiv", help="arXiv ID to fetch BibTeX")
    parser.add_argument("--query", help="Literature search query")
    parser.add_argument("--source-bib", help="Source .bib path (e.g. Zotero export)")
    parser.add_argument("--dedup", action="store_true", help="Deduplicate project refs.bib")
    parser.add_argument("--mode", default="polish", choices=["polish", "zh2en", "en2zh", "compress", "expand", "deai"])
    parser.add_argument("--kind", default="table", choices=["formula", "table", "tikz", "algorithm", "section"])
    parser.add_argument("--input", help="Input file path or inline text")
    parser.add_argument("--apply", action="store_true", help="Write rewrite output back to file")
    parser.add_argument("--double-blind", action="store_true", help="Force double-blind anonymity check")
    parser.add_argument("--output", help="Output ZIP path for export")
    parser.add_argument("--label", default="CLI 快照", help="Snapshot label")


def run(args, client: Any = None) -> int:
    store = LatexStore()

    def need_project():
        if not args.project:
            raise ValueError("需要指定 --project <project_id>")
        return store.get_project(args.project)

    def act_templates():
        return [t.model_dump() for t in list_templates()]

    def act_init():
        meta, files = get_template_files(
            args.template,
            title=args.name or "Scalable Byzantine Consensus for Decentralized Applications",
            author=args.author,
        )
        proj = store.create_project(
            name=args.name or meta.name,
            template_id=args.template,
            files=files,
            main_file=meta.main_file,
            engine=meta.recommended_engine,
            venue_preset=meta.category,
            page_limit=meta.page_limit,
            double_blind=meta.double_blind,
        )
        return {"project": proj.model_dump(), "files": sorted(files.keys())}

    def act_link():
        if not args.dir:
            raise ValueError("需要 --dir <本地LaTeX目录>")
        ws = Path(args.dir).expanduser().resolve()
        return store.create_project(name=args.name or ws.name, workspace_dir=ws, template_id="linked").model_dump()

    def act_build():
        meta = need_project()
        return compile_project(meta, engine=args.engine).model_dump()

    def act_clean():
        meta = need_project()
        return {"removed": clean_auxiliary_files(Path(meta.workspace_dir))}

    def act_check():
        meta = need_project()
        return run_preflight_check(meta, check_double_blind=True if args.double_blind else None).model_dump()

    def act_bib():
        if args.doi:
            entry = fetch_bibtex_by_doi(args.doi)
            return entry.model_dump()
        if args.arxiv:
            entry = fetch_bibtex_by_arxiv(args.arxiv)
            return entry.model_dump()
        if args.query:
            return {"results": search_crossref(args.query)}
        meta = need_project()
        bib_rel = args.file or "refs.bib"
        bib_path = safe_resolve_in_workspace(Path(meta.workspace_dir), bib_rel)
        if args.source_bib:
            return sync_from_bib_file(Path(args.source_bib).expanduser(), bib_path)
        if args.dedup and bib_path.is_file():
            kept, removed = deduplicate_bib(parse_bib(bib_path.read_text(encoding="utf-8", errors="replace")))
            store.write_file(meta.id, bib_rel, format_bib_file(kept), snapshot_label="BibTeX 去重")
            return {"removed": removed, "total": len(kept)}
        if not bib_path.is_file():
            return {"entries": []}
        return {"entries": [e.model_dump() for e in parse_bib(bib_path.read_text(encoding="utf-8", errors="replace"))]}

    def act_rewrite():
        if args.file and args.project:
            text = store.read_file(args.project, args.file)
        elif args.input:
            p = Path(args.input)
            text = p.read_text(encoding="utf-8") if p.is_file() else args.input
        else:
            raise ValueError("需要 --input 或 (--project + --file)")
        res = asyncio.run(rewrite_latex_text(text, mode=args.mode, filename=args.file or "snippet.tex", client=client))
        out = res.model_dump()
        if args.apply and args.project and args.file and res.integrity_ok:
            store.write_file(args.project, args.file, res.rewritten_text, snapshot_label=f"CLI {args.mode} 改写")
            out["applied"] = True
        return out

    def act_generate():
        if not args.input:
            raise ValueError("需要 --input")
        p = Path(args.input)
        raw = p.read_text(encoding="utf-8") if p.is_file() else args.input
        return asyncio.run(generate_latex_snippet(args.kind, raw, client=client))

    def act_chat():
        meta = need_project()
        prompt = args.input
        if not prompt:
            raise ValueError("需要 --input 提供修改需求或对话内容")
        return asyncio.run(converse_paper_project(
            store,
            meta.id,
            prompt,
            active_file=args.file,
            auto_apply=args.apply,
            client=client,
        ))

    def act_materials():
        meta = need_project()
        return [m.model_dump() for m in store.list_materials(meta.id)]

    def act_export():
        meta = need_project()
        out = Path(args.output or f"{meta.id}_arxiv.zip").expanduser().resolve()
        return export_submission_zip(Path(meta.workspace_dir), out, main_file=meta.main_file)

    handlers = {
        "templates": act_templates,
        "init": act_init,
        "link": act_link,
        "list": lambda: [p.model_dump() for p in store.list_projects()],
        "structure": lambda: parse_project(Path(need_project().workspace_dir), need_project().main_file).model_dump(),
        "build": act_build,
        "clean": act_clean,
        "check": act_check,
        "bib": act_bib,
        "rewrite": act_rewrite,
        "generate": act_generate,
        "chat": act_chat,
        "materials": act_materials,
        "snapshot": lambda: store.create_snapshot(need_project().id, label=args.label).model_dump(),
        "export": act_export,
        "setup": install_tectonic,
        "doctor": detect_compilers,
    }
    try:
        result = handlers[args.action]()
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
