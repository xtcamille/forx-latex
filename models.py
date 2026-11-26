"""Typed Pydantic schemas for forx-latex projects, diagnostics, SyncTeX, BibTeX, and checks."""
from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class TemplateMeta(StrictModel):
    id: str
    name: str
    category: Literal["ieee", "cs_top", "ccf_blockchain", "thesis", "general"]
    language: Literal["en", "zh", "bilingual"] = "en"
    recommended_engine: Literal["tectonic", "pdflatex", "xelatex", "lualatex"] = "tectonic"
    venue_tags: list[str] = Field(default_factory=list)
    page_limit: Optional[int] = None
    double_blind: bool = False
    description: str = ""
    main_file: str = "main.tex"


class ProjectMeta(StrictModel):
    id: str
    name: str
    template_id: str = "custom"
    workspace_dir: str
    main_file: str = "main.tex"
    engine: Literal["auto", "tectonic", "pdflatex", "xelatex", "lualatex"] = "auto"
    venue_preset: str = "general"
    page_limit: Optional[int] = None
    double_blind: bool = False
    revision: int = 1
    created_at: str
    updated_at: str


class FileEntry(StrictModel):
    path: str
    size: int = 0
    is_binary: bool = False
    kind: Literal["tex", "bib", "sty", "cls", "image", "pdf", "other"] = "other"


class OutlineNode(StrictModel):
    id: str
    level: int
    kind: Literal["part", "chapter", "section", "subsection", "subsubsection", "figure", "table", "algorithm"]
    title: str
    file: str
    line: int
    label: Optional[str] = None


class LabelEntry(StrictModel):
    key: str
    kind: str = "unknown"
    file: str
    line: int
    context: str = ""


class RefUsage(StrictModel):
    key: str
    command: str
    file: str
    line: int


class CiteUsage(StrictModel):
    keys: list[str]
    command: str
    file: str
    line: int


class ProjectStructure(StrictModel):
    main_file: str
    included_files: list[str] = Field(default_factory=list)
    packages: list[str] = Field(default_factory=list)
    bib_files: list[str] = Field(default_factory=list)
    graphics_files: list[str] = Field(default_factory=list)
    recommended_engine: Literal["tectonic", "pdflatex", "xelatex", "lualatex"] = "tectonic"
    uses_biber: bool = False
    outline: list[OutlineNode] = Field(default_factory=list)
    labels: list[LabelEntry] = Field(default_factory=list)
    refs: list[RefUsage] = Field(default_factory=list)
    cites: list[CiteUsage] = Field(default_factory=list)
    macros: list[str] = Field(default_factory=list)


class DiagnosticItem(StrictModel):
    severity: Literal["error", "warning", "overfull", "info"]
    file: str
    line: Optional[int] = None
    message: str
    code: str = ""
    snippet: str = ""


class SyncTeXPoint(StrictModel):
    page: int
    x: float
    y: float
    width: float = 0.0
    height: float = 0.0
    file: str = ""
    line: int = 1


class CompileResult(StrictModel):
    ok: bool
    engine_used: str
    compiler_path: str = ""
    pdf_path: Optional[str] = None
    synctex_path: Optional[str] = None
    log_path: Optional[str] = None
    page_count: Optional[int] = None
    duration_ms: int = 0
    errors: list[DiagnosticItem] = Field(default_factory=list)
    warnings: list[DiagnosticItem] = Field(default_factory=list)
    overfulls: list[DiagnosticItem] = Field(default_factory=list)
    raw_log_tail: str = ""
    hint: str = ""


class SnapshotSummary(StrictModel):
    id: str
    project_id: str
    revision: int
    label: str
    created_at: str
    file_count: int = 0


class BibEntry(StrictModel):
    key: str
    entry_type: str
    fields: dict[str, str] = Field(default_factory=dict)
    raw: str = ""
    line: int = 1


class CheckIssue(StrictModel):
    category: Literal["consistency", "citation", "double_blind", "layout", "math", "acronym"]
    severity: Literal["error", "warning", "info"]
    file: str
    line: Optional[int] = None
    title: str
    detail: str
    suggestion: str = ""


class CheckReport(StrictModel):
    ok: bool
    summary: dict[str, int] = Field(default_factory=dict)
    word_count: dict[str, Any] = Field(default_factory=dict)
    issues: list[CheckIssue] = Field(default_factory=list)


class RewriteResult(StrictModel):
    ok: bool
    mode: str
    original_text: str
    rewritten_text: str
    diff: str
    preserved_tokens: int
    integrity_ok: bool
    integrity_errors: list[str] = Field(default_factory=list)


class ProjectFilePatch(StrictModel):
    file: str
    action: Literal["replace_range", "insert_cursor", "replace_file", "create_file"] = "replace_range"
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    replacement: str
    explanation: str = ""


class ProjectChatMessage(StrictModel):
    id: str
    project_id: str
    role: Literal["user", "assistant", "system"]
    text: str
    timestamp: str
    attachments: list[str] = Field(default_factory=list)
    active_file: Optional[str] = None
    patches: list[ProjectFilePatch] = Field(default_factory=list)
    diff: Optional[str] = None
    applied: bool = False


class ProjectChatRequest(StrictModel):
    prompt: str
    active_file: Optional[str] = None
    cursor_line: Optional[int] = None
    selection_text: Optional[str] = None
    referenced_materials: list[str] = Field(default_factory=list)
    auto_apply: bool = False


class ProjectChatPlan(StrictModel):
    message: str = ""
    clarification: Optional[str] = None
    patches: list[ProjectFilePatch] = Field(default_factory=list)

