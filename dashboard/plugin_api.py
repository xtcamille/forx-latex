"""Authenticated FastAPI routes for hermes-latex; host middleware validates auth & profile scope."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_root = Path(__file__).resolve().parents[1]
_pkg_name = "hermes_latex_" + hashlib.sha256(str(_root).encode()).hexdigest()[:16]
if _pkg_name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        _pkg_name,
        _root / "__init__.py",
        submodule_search_locations=[str(_root)],
    )
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_pkg_name] = _mod
    _spec.loader.exec_module(_mod)

ai_engine = __import__(_pkg_name + ".ai_engine", fromlist=["rewrite_latex_text"])
bibtex = __import__(_pkg_name + ".bibtex", fromlist=["parse_bib"])
checker = __import__(_pkg_name + ".checker", fromlist=["run_preflight_check"])
compiler = __import__(_pkg_name + ".compiler", fromlist=["compile_project"])
project_parser = __import__(_pkg_name + ".project_parser", fromlist=["parse_project"])
storage = __import__(_pkg_name + ".storage", fromlist=["LatexStore"])
synctex = __import__(_pkg_name + ".synctex", fromlist=["forward_search"])
templates = __import__(_pkg_name + ".templates", fromlist=["list_templates"])


class ScopedRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def scoped(request: Request):
            try:
                from hermes_cli.web_server_profiles import _config_profile_scope
                profile_ctx = _config_profile_scope(request.query_params.get("profile"))
            except Exception:
                from contextlib import nullcontext
                profile_ctx = nullcontext()

            try:
                with profile_ctx:
                    try:
                        from hermes_cli.config import load_config
                        cfg = load_config().get("plugins", {})
                        enabled = cfg.get("enabled", [])
                        disabled = cfg.get("disabled", [])
                        if "hermes-latex" not in enabled or "hermes-latex" in disabled:
                            raise HTTPException(403, "请在当前配置中启用 hermes-latex 插件")
                    except ImportError:
                        pass
                    return await handler(request)
            except HTTPException:
                raise
            except storage.ConflictError as exc:
                raise HTTPException(409, str(exc)) from exc
            except KeyError as exc:
                raise HTTPException(404, str(exc)) from exc
            except FileNotFoundError as exc:
                raise HTTPException(404, str(exc)) from exc
            except (ValueError, ValidationError) as exc:
                raise HTTPException(422, str(exc)) from exc

        return scoped


router = APIRouter(route_class=ScopedRoute)


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateProjectBody(Body):
    name: str = Field(min_length=1, max_length=160)
    template_id: str = "ieee-conf"
    title: str = Field("", max_length=300)
    author: str = Field("Anonymous Author(s)", max_length=300)
    request_id: str | None = None


class ImportZipBody(Body):
    name: str = Field(min_length=1, max_length=160)
    data_base64: str = Field(min_length=1)


class LinkDirBody(Body):
    name: str = Field("", max_length=160)
    workspace_dir: str = Field(min_length=1, max_length=1000)


class UpdateProjectBody(Body):
    name: str | None = None
    main_file: str | None = None
    engine: str | None = None
    page_limit: int | None = Field(None, ge=1, le=500)
    double_blind: bool | None = None


class WriteFileBody(Body):
    path: str = Field(min_length=1, max_length=400)
    content: str
    expected_revision: int | None = None
    snapshot_label: str | None = None


class UploadAssetBody(Body):
    path: str = Field(min_length=1, max_length=400)
    data_base64: str = Field(min_length=1)


class CompileBody(Body):
    engine: str = "auto"


class SnapshotBody(Body):
    label: str = Field("手动快照", max_length=200)


class BibFetchBody(Body):
    kind: str = Field("doi", pattern="^(doi|arxiv|search|raw)$")
    query: str = Field(min_length=1, max_length=2000)
    bib_file: str = "refs.bib"
    append: bool = True


class BibSyncBody(Body):
    source_path: str = Field(min_length=1, max_length=1000)
    bib_file: str = "refs.bib"


class CheckBody(Body):
    double_blind: bool | None = None


class RewriteBody(Body):
    text: str = Field(min_length=1, max_length=50000)
    mode: str = "polish"
    instruction: str = ""
    target_words: int | None = Field(None, ge=10, le=10000)
    filename: str = "section.tex"


class HealBody(Body):
    apply_patches: bool = False
    engine: str = "auto"


class GenerateBody(Body):
    kind: str = "table"
    input: str = Field(min_length=1, max_length=50000)
    caption: str = "Experimental Results"
    label: str = "tab:results"
    image_base64: str | None = None


class ProjectChatBody(Body):
    prompt: str = Field(min_length=1, max_length=25000)
    active_file: str | None = None
    cursor_line: int | None = None
    selection_text: str | None = None
    referenced_materials: list[str] = Field(default_factory=list)
    auto_apply: bool = False


class ApplyChatPatchBody(Body):
    message_id: str = Field(min_length=1)


class MaterialUploadBody(Body):
    path: str | None = None
    rel_path: str | None = None
    text_content: str | None = None
    content: str | None = None
    data_base64: str | None = None


@router.get("/status")
async def status():
    comp = compiler.detect_compilers()
    return {
        "ready": True,
        "compiler": comp,
        "template_count": len(templates.list_templates()),
    }


@router.get("/templates")
async def list_all_templates():
    return {"templates": [t.model_dump() for t in templates.list_templates()]}


@router.post("/compiler/install-tectonic")
async def setup_tectonic():
    return compiler.install_tectonic()


@router.get("/projects")
async def list_projects():
    return {"projects": [p.model_dump() for p in storage.LatexStore().list_projects()]}


@router.post("/projects")
async def create_project(body: CreateProjectBody):
    store = storage.LatexStore()
    fp = storage.stable_json(body.model_dump(exclude={"request_id"}))
    replay = store.replay(body.request_id, fp)
    if replay:
        return replay
    meta, files = templates.get_template_files(
        body.template_id,
        title=body.title or body.name,
        author=body.author,
    )
    proj = store.create_project(
        name=body.name,
        template_id=body.template_id,
        files=files,
        main_file=meta.main_file,
        engine=meta.recommended_engine,
        venue_preset=meta.category,
        page_limit=meta.page_limit,
        double_blind=meta.double_blind,
    )
    res = {"project": proj.model_dump(), "files": store.list_files(proj.id)}
    store.record_request(body.request_id, fp, res)
    return res


@router.post("/projects/import-zip")
async def import_zip_project(body: ImportZipBody):
    raw = base64.b64decode(body.data_base64, validate=True)
    files = templates.extract_zip_template(raw)
    store = storage.LatexStore()
    proj = store.create_project(name=body.name, template_id="zip-import", files=files)
    return {"project": proj.model_dump(), "files": store.list_files(proj.id)}


@router.post("/projects/link-dir")
async def link_dir_project(body: LinkDirBody):
    ws = Path(body.workspace_dir).expanduser().resolve()
    if not ws.is_dir():
        raise ValueError(f"目录不存在: {ws}")
    store = storage.LatexStore()
    proj = store.create_project(name=body.name or ws.name, template_id="linked", workspace_dir=ws)
    return {"project": proj.model_dump(), "files": store.list_files(proj.id)}


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    store = storage.LatexStore()
    proj = store.get_project(project_id)
    structure = project_parser.parse_project(Path(proj.workspace_dir), proj.main_file)
    return {
        "project": proj.model_dump(),
        "files": store.list_files(project_id),
        "structure": structure.model_dump(),
    }


@router.patch("/projects/{project_id}")
async def update_project(project_id: str, body: UpdateProjectBody):
    proj = storage.LatexStore().update_project_meta(project_id, **body.model_dump(exclude_none=True))
    return {"project": proj.model_dump()}


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, delete_files: bool = False):
    return storage.LatexStore().delete_project(project_id, delete_files=delete_files)


@router.get("/projects/{project_id}/file")
async def read_file(project_id: str, path: str):
    content = storage.LatexStore().read_file(project_id, path)
    return {"path": path, "content": content}


@router.put("/projects/{project_id}/file")
async def write_file(project_id: str, body: WriteFileBody):
    store = storage.LatexStore()
    proj = store.write_file(
        project_id,
        body.path,
        body.content,
        expected_revision=body.expected_revision,
        snapshot_label=body.snapshot_label,
    )
    structure = project_parser.parse_project(Path(proj.workspace_dir), proj.main_file)
    return {"project": proj.model_dump(), "files": store.list_files(project_id), "structure": structure.model_dump()}


@router.delete("/projects/{project_id}/file")
async def delete_file(project_id: str, path: str):
    store = storage.LatexStore()
    proj = store.delete_file(project_id, path)
    return {"project": proj.model_dump(), "files": store.list_files(project_id)}


@router.post("/projects/{project_id}/upload-asset")
async def upload_asset(project_id: str, body: UploadAssetBody):
    store = storage.LatexStore()
    proj = store.get_project(project_id)
    raw = base64.b64decode(body.data_base64, validate=True)
    target = storage.safe_resolve_in_workspace(Path(proj.workspace_dir), body.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    proj = store.bump_revision(project_id)
    return {"project": proj.model_dump(), "files": store.list_files(project_id)}


@router.post("/projects/{project_id}/compile")
async def compile_proj(project_id: str, body: CompileBody):
    proj = storage.LatexStore().get_project(project_id)
    res = compiler.compile_project(proj, engine=body.engine)
    return res.model_dump()


@router.get("/projects/{project_id}/pdf")
async def get_pdf(project_id: str):
    proj = storage.LatexStore().get_project(project_id)
    ws = Path(proj.workspace_dir)
    main_rel = project_parser.detect_main_file(ws, proj.main_file)
    stem = (ws / main_rel).stem
    pdf_path = (ws / main_rel).with_suffix(".pdf")
    if not pdf_path.is_file():
        return {"available": False}
    sync_path = (ws / main_rel).parent / f"{stem}.synctex.gz"
    return {
        "available": True,
        "filename": pdf_path.name,
        "content_type": "application/pdf",
        "data": base64.b64encode(pdf_path.read_bytes()).decode("ascii"),
        "page_count": compiler.count_pdf_pages(pdf_path),
        "synctex_available": sync_path.is_file(),
    }


@router.get("/projects/{project_id}/synctex/forward")
async def synctex_forward(project_id: str, file: str, line: int):
    proj = storage.LatexStore().get_project(project_id)
    ws = Path(proj.workspace_dir)
    main_rel = project_parser.detect_main_file(ws, proj.main_file)
    sync_path = (ws / main_rel).parent / f"{(ws / main_rel).stem}.synctex.gz"
    pts = synctex.forward_search(sync_path, ws, file, line)
    return {"points": [p.model_dump() for p in pts]}


@router.get("/projects/{project_id}/synctex/inverse")
async def synctex_inverse(project_id: str, page: int, x: float, y: float):
    proj = storage.LatexStore().get_project(project_id)
    ws = Path(proj.workspace_dir)
    main_rel = project_parser.detect_main_file(ws, proj.main_file)
    sync_path = (ws / main_rel).parent / f"{(ws / main_rel).stem}.synctex.gz"
    pt = synctex.inverse_search(sync_path, ws, page, x, y)
    return {"point": pt.model_dump() if pt else None}


@router.get("/projects/{project_id}/synctex/page")
async def synctex_page(project_id: str, page: int):
    proj = storage.LatexStore().get_project(project_id)
    ws = Path(proj.workspace_dir)
    main_rel = project_parser.detect_main_file(ws, proj.main_file)
    sync_path = (ws / main_rel).parent / f"{(ws / main_rel).stem}.synctex.gz"
    pts = synctex.page_nodes(sync_path, ws, page)
    return {"points": [p.model_dump() for p in pts]}


@router.get("/projects/{project_id}/bib")
async def get_bib(project_id: str, bib_file: str = "refs.bib"):
    proj = storage.LatexStore().get_project(project_id)
    bib_path = storage.safe_resolve_in_workspace(Path(proj.workspace_dir), bib_file)
    if not bib_path.is_file():
        return {"entries": [], "issues": []}
    entries = bibtex.parse_bib(bib_path.read_text(encoding="utf-8", errors="replace"))
    return {"entries": [e.model_dump() for e in entries], "issues": bibtex.validate_bib(entries)}


@router.post("/projects/{project_id}/bib/fetch")
async def fetch_bib(project_id: str, body: BibFetchBody):
    store = storage.LatexStore()
    proj = store.get_project(project_id)
    if body.kind == "search":
        return {"results": bibtex.search_crossref(body.query)}
    if body.kind == "doi":
        entries = [bibtex.fetch_bibtex_by_doi(body.query)]
    elif body.kind == "arxiv":
        entries = [bibtex.fetch_bibtex_by_arxiv(body.query)]
    else:
        entries = bibtex.parse_bib(body.query)
        if not entries:
            raise ValueError("未解析到有效的 BibTeX 条目")

    appended = False
    if body.append:
        bib_path = storage.safe_resolve_in_workspace(Path(proj.workspace_dir), body.bib_file)
        existing = bib_path.read_text(encoding="utf-8", errors="replace") if bib_path.is_file() else ""
        merged = bibtex.parse_bib(existing) + entries
        kept, _ = bibtex.deduplicate_bib(merged)
        store.write_file(project_id, body.bib_file, bibtex.format_bib_file(kept), snapshot_label=f"新增文献 {entries[0].key}")
        appended = True
    return {"entries": [e.model_dump() for e in entries], "appended": appended}


@router.post("/projects/{project_id}/bib/dedup")
async def dedup_bib(project_id: str, bib_file: str = "refs.bib"):
    store = storage.LatexStore()
    proj = store.get_project(project_id)
    bib_path = storage.safe_resolve_in_workspace(Path(proj.workspace_dir), bib_file)
    if not bib_path.is_file():
        return {"removed": [], "total": 0}
    entries = bibtex.parse_bib(bib_path.read_text(encoding="utf-8", errors="replace"))
    kept, removed = bibtex.deduplicate_bib(entries)
    store.write_file(project_id, bib_file, bibtex.format_bib_file(kept), snapshot_label="BibTeX 去重格式化")
    return {"removed": removed, "total": len(kept)}


@router.post("/projects/{project_id}/bib/sync-zotero")
async def sync_zotero(project_id: str, body: BibSyncBody):
    store = storage.LatexStore()
    proj = store.get_project(project_id)
    target = storage.safe_resolve_in_workspace(Path(proj.workspace_dir), body.bib_file)
    res = bibtex.sync_from_bib_file(Path(body.source_path).expanduser(), target)
    store.bump_revision(project_id)
    return res


@router.get("/projects/{project_id}/snapshots")
async def list_snapshots(project_id: str):
    return {"snapshots": [s.model_dump() for s in storage.LatexStore().list_snapshots(project_id)]}


@router.post("/projects/{project_id}/snapshots")
async def create_snapshot(project_id: str, body: SnapshotBody):
    return storage.LatexStore().create_snapshot(project_id, label=body.label).model_dump()


@router.get("/projects/{project_id}/snapshots/diff")
async def diff_snapshots(project_id: str, from_id: str, to_id: str | None = None):
    return storage.LatexStore().diff_snapshots(project_id, from_id, to_id)


@router.post("/projects/{project_id}/snapshots/{snapshot_id}/restore")
async def restore_snapshot(project_id: str, snapshot_id: str):
    store = storage.LatexStore()
    proj = store.restore_snapshot(project_id, snapshot_id)
    return {"project": proj.model_dump(), "files": store.list_files(project_id)}


@router.post("/projects/{project_id}/check")
async def check_project(project_id: str, body: CheckBody):
    proj = storage.LatexStore().get_project(project_id)
    return checker.run_preflight_check(proj, check_double_blind=body.double_blind).model_dump()


@router.post("/projects/{project_id}/clean")
async def clean_project(project_id: str):
    proj = storage.LatexStore().get_project(project_id)
    return {"removed": compiler.clean_auxiliary_files(Path(proj.workspace_dir))}


@router.post("/projects/{project_id}/export-zip")
async def export_zip(project_id: str):
    proj = storage.LatexStore().get_project(project_id)
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
        tmp_zip = Path(tf.name)
    try:
        info = compiler.export_submission_zip(Path(proj.workspace_dir), tmp_zip, main_file=proj.main_file)
        data = base64.b64encode(tmp_zip.read_bytes()).decode("ascii")
        return {"filename": f"{proj.id}_arxiv.zip", "content_type": "application/zip", "data": data, "files": info["files"]}
    finally:
        tmp_zip.unlink(missing_ok=True)


@router.post("/projects/{project_id}/ai/rewrite")
async def ai_rewrite(project_id: str, body: RewriteBody):
    storage.LatexStore().get_project(project_id)
    res = await ai_engine.rewrite_latex_text(
        body.text,
        mode=body.mode,
        instruction=body.instruction,
        target_words=body.target_words,
        filename=body.filename,
    )
    return res.model_dump()


@router.post("/projects/{project_id}/ai/heal")
async def ai_heal(project_id: str, body: HealBody):
    store = storage.LatexStore()
    proj = store.get_project(project_id)
    comp = compiler.compile_project(proj, engine=body.engine)
    heal = await ai_engine.heal_compile_errors(store, proj, comp, apply_patches=body.apply_patches)
    return {"compile": comp.model_dump(), "heal": heal}


@router.post("/projects/{project_id}/ai/generate")
async def ai_generate(project_id: str, body: GenerateBody):
    storage.LatexStore().get_project(project_id)
    img_bytes = base64.b64decode(body.image_base64, validate=True) if body.image_base64 else None
    return await ai_engine.generate_latex_snippet(
        body.kind,
        body.input,
        caption=body.caption,
        label=body.label,
        image_bytes=img_bytes,
    )


@router.post("/projects/{project_id}/chat")
async def project_chat(project_id: str, body: ProjectChatBody):
    store = storage.LatexStore()
    return await ai_engine.converse_paper_project(
        store,
        project_id,
        body.prompt,
        active_file=body.active_file,
        cursor_line=body.cursor_line,
        selection_text=body.selection_text,
        referenced_materials=body.referenced_materials,
        auto_apply=body.auto_apply,
    )


@router.get("/projects/{project_id}/chat/history")
async def get_project_chat_history(project_id: str, limit: int = 50):
    store = storage.LatexStore()
    store.get_project(project_id)
    return {"messages": [m.model_dump() for m in store.list_chat_messages(project_id, limit=limit)]}


@router.post("/projects/{project_id}/chat/apply")
async def apply_project_chat_patch(project_id: str, body: ApplyChatPatchBody):
    store = storage.LatexStore()
    return ai_engine.apply_chat_patches(store, project_id, body.message_id)


@router.delete("/projects/{project_id}/chat/history")
async def clear_project_chat_history(project_id: str):
    store = storage.LatexStore()
    store.get_project(project_id)
    return {"cleared": store.clear_chat_messages(project_id)}


@router.get("/projects/{project_id}/materials")
async def list_project_materials(project_id: str):
    store = storage.LatexStore()
    store.get_project(project_id)
    return {"materials": [m.model_dump() for m in store.list_materials(project_id)]}


@router.post("/projects/{project_id}/materials")
async def upload_project_material(project_id: str, body: MaterialUploadBody):
    store = storage.LatexStore()
    store.get_project(project_id)
    target_path = body.path or body.rel_path
    if not target_path:
        raise ValueError("请提供 path 或 rel_path")
    text_data = body.text_content if body.text_content is not None else body.content
    if body.data_base64:
        raw = base64.b64decode(body.data_base64, validate=True)
        saved = store.save_material(project_id, target_path, raw, is_binary=True)
    elif text_data is not None:
        saved = store.save_material(project_id, target_path, text_data, is_binary=False)
    else:
        raise ValueError("请提供 text_content 或 data_base64")
    return {"ok": True, "material": saved.model_dump()}

