"""Profile-scoped SQLite metadata, local snapshots, and safe workspace file I/O."""
from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from .models import FileEntry, ProjectChatMessage, ProjectFilePatch, ProjectMeta, SnapshotSummary

TEXT_EXTENSIONS = {
    ".tex", ".bib", ".sty", ".cls", ".bst", ".txt", ".md", ".csv",
    ".json", ".yaml", ".yml", ".latexmkrc", ".cfg", ".def", ".clo",
}
BINARY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".eps", ".svg"}
IGNORED_DIRS = {".git", "__pycache__", ".hermes_latex_build", "build", "node_modules"}
AUX_EXTENSIONS = {
    ".aux", ".log", ".bbl", ".blg", ".out", ".toc", ".lof", ".lot",
    ".fls", ".fdb_latexmk", ".synctex.gz", ".synctex", ".nav", ".snm",
    ".vrb", ".xdv", ".bcf", ".run.xml", ".idx", ".ilg", ".ind",
}


class ConflictError(ValueError):
    """Raised on optimistic concurrency or request-id fingerprint mismatch."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def data_root() -> Path:
    """Resolve plugin data dir dynamically so profile switches take effect immediately."""
    try:
        from plugins.plugin_storage import plugin_data_dir
        return plugin_data_dir("hermes-latex")
    except Exception:
        import os
        home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        root = home / "plugin-data" / "hermes-latex"
        root.mkdir(parents=True, exist_ok=True)
        return root


def workspaces_root() -> Path:
    root = data_root() / "workspaces"
    root.mkdir(parents=True, exist_ok=True)
    return root


def bin_root() -> Path:
    root = data_root() / "bin"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _classify_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".tex":
        return "tex"
    if ext == ".bib":
        return "bib"
    if ext == ".sty":
        return "sty"
    if ext == ".cls":
        return "cls"
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".eps", ".svg"}:
        return "image"
    if ext == ".pdf":
        return "pdf"
    return "other"


def _is_text_file(path: Path) -> bool:
    if path.name in {"latexmkrc", ".latexmkrc", "Makefile"}:
        return True
    return path.suffix.lower() in TEXT_EXTENSIONS


def safe_resolve_in_workspace(workspace: Path, rel_path: str) -> Path:
    """Resolve *rel_path* inside *workspace*, blocking path traversal."""
    clean = (rel_path or "").strip().lstrip("/\\")
    if not clean or ".." in Path(clean).parts:
        raise ValueError(f"非法相对路径: {rel_path!r}")
    base = workspace.resolve()
    target = (base / clean).resolve()
    if target != base and not target.is_relative_to(base):
        raise ValueError(f"路径越界被拒绝: {rel_path!r}")
    return target


class LatexStore:
    """Profile-scoped project registry, snapshots, and safe workspace accessor."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (data_root() / "latex_projects.db")

    @contextmanager
    def connection(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from hermes_cli.sqlite_util import open_db
            conn = open_db(
                self.db_path,
                db_label="hermes-latex",
                foreign_keys=True,
                check_same_thread=False,
            )
        except Exception:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.execute("PRAGMA foreign_keys = ON")

        with closing(conn) as db:
            db.row_factory = sqlite3.Row
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    workspace_dir TEXT NOT NULL,
                    main_file TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    venue_preset TEXT NOT NULL,
                    page_limit INTEGER,
                    double_blind INTEGER NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    files_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_chat_messages (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    attachments_json TEXT NOT NULL DEFAULT '[]',
                    active_file TEXT,
                    patches_json TEXT NOT NULL DEFAULT '[]',
                    diff TEXT,
                    applied INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            yield db

    def replay(self, request_id: Optional[str], fingerprint: str) -> Optional[Any]:
        if not request_id:
            return None
        with self.connection() as db:
            row = db.execute("SELECT fingerprint, result_json FROM requests WHERE request_id = ?", (request_id,)).fetchone()
            if not row:
                return None
            if row["fingerprint"] != fingerprint:
                raise ConflictError("同一 request_id 不能用于不同的请求参数")
            return json.loads(row["result_json"])

    def record_request(self, request_id: Optional[str], fingerprint: str, result: Any) -> None:
        if not request_id:
            return
        with self.connection() as db, db:
            db.execute(
                "INSERT OR REPLACE INTO requests (request_id, fingerprint, result_json, created_at) VALUES (?, ?, ?, ?)",
                (request_id, fingerprint, json.dumps(result, ensure_ascii=False), utc_now()),
            )

    def list_projects(self) -> list[ProjectMeta]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
            return [self._row_to_meta(r) for r in rows]

    def get_project(self, project_id: str) -> ProjectMeta:
        with self.connection() as db:
            row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if row is None:
                raise KeyError(f"未找到 LaTeX 项目: {project_id}")
            return self._row_to_meta(row)

    def _row_to_meta(self, row: sqlite3.Row) -> ProjectMeta:
        return ProjectMeta(
            id=row["id"],
            name=row["name"],
            template_id=row["template_id"],
            workspace_dir=row["workspace_dir"],
            main_file=row["main_file"],
            engine=row["engine"],
            venue_preset=row["venue_preset"],
            page_limit=row["page_limit"],
            double_blind=bool(row["double_blind"]),
            revision=row["revision"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_project(
        self,
        *,
        name: str,
        template_id: str = "custom",
        files: Optional[dict[str, str]] = None,
        workspace_dir: Optional[Path] = None,
        main_file: str = "main.tex",
        engine: str = "auto",
        venue_preset: str = "general",
        page_limit: Optional[int] = None,
        double_blind: bool = False,
    ) -> ProjectMeta:
        pid = f"lx_{uuid.uuid4().hex[:10]}"
        now = utc_now()
        if workspace_dir is None:
            ws = workspaces_root() / pid
            ws.mkdir(parents=True, exist_ok=True)
        else:
            ws = Path(workspace_dir).expanduser().resolve()
            ws.mkdir(parents=True, exist_ok=True)

        if files:
            for rel, content in files.items():
                dest = safe_resolve_in_workspace(ws, rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")

        meta = ProjectMeta(
            id=pid,
            name=name.strip() or "Untitled Paper",
            template_id=template_id,
            workspace_dir=str(ws),
            main_file=main_file,
            engine=engine,  # type: ignore[arg-type]
            venue_preset=venue_preset,
            page_limit=page_limit,
            double_blind=double_blind,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        with self.connection() as db, db:
            db.execute(
                """
                INSERT INTO projects (
                    id, name, template_id, workspace_dir, main_file, engine,
                    venue_preset, page_limit, double_blind, revision, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meta.id, meta.name, meta.template_id, meta.workspace_dir, meta.main_file,
                    meta.engine, meta.venue_preset, meta.page_limit, int(meta.double_blind),
                    meta.revision, meta.created_at, meta.updated_at,
                ),
            )
        self.create_snapshot(pid, label="初始化工程")
        return meta

    def update_project_meta(self, project_id: str, **updates: Any) -> ProjectMeta:
        allowed = {"name", "main_file", "engine", "venue_preset", "page_limit", "double_blind"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return self.get_project(project_id)
        if "double_blind" in fields:
            fields["double_blind"] = int(bool(fields["double_blind"]))
        fields["updated_at"] = utc_now()
        sets = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [project_id]
        with self.connection() as db, db:
            cur = db.execute(f"UPDATE projects SET {sets} WHERE id = ?", vals)
            if cur.rowcount == 0:
                raise KeyError(f"未找到 LaTeX 项目: {project_id}")
        return self.get_project(project_id)

    def delete_project(self, project_id: str, *, delete_files: bool = False) -> dict[str, Any]:
        meta = self.get_project(project_id)
        with self.connection() as db, db:
            db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        ws = Path(meta.workspace_dir)
        if delete_files and ws.is_dir() and ws.resolve().is_relative_to(workspaces_root().resolve()):
            shutil.rmtree(ws, ignore_errors=True)
        return {"deleted": True, "project_id": project_id}

    def bump_revision(self, project_id: str) -> ProjectMeta:
        now = utc_now()
        with self.connection() as db, db:
            db.execute("UPDATE projects SET revision = revision + 1, updated_at = ? WHERE id = ?", (now, project_id))
        return self.get_project(project_id)

    def list_files(self, project_id: str) -> list[dict[str, Any]]:
        meta = self.get_project(project_id)
        ws = Path(meta.workspace_dir)
        if not ws.is_dir():
            return []
        entries = []
        for p in sorted(ws.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(ws).as_posix()
            parts = rel.split("/")
            if any(part in IGNORED_DIRS for part in parts):
                continue
            if p.suffix.lower() in AUX_EXTENSIONS or rel.endswith(".synctex.gz"):
                continue
            entries.append({
                "path": rel,
                "size": p.stat().st_size,
                "is_binary": not _is_text_file(p),
                "kind": _classify_kind(p),
            })
        return entries

    def read_file(self, project_id: str, rel_path: str) -> str:
        meta = self.get_project(project_id)
        target = safe_resolve_in_workspace(Path(meta.workspace_dir), rel_path)
        if not target.is_file():
            raise FileNotFoundError(f"文件不存在: {rel_path}")
        return target.read_text(encoding="utf-8", errors="replace")

    def write_file(
        self,
        project_id: str,
        rel_path: str,
        content: str,
        *,
        expected_revision: Optional[int] = None,
        snapshot_label: Optional[str] = None,
    ) -> ProjectMeta:
        meta = self.get_project(project_id)
        if expected_revision is not None and meta.revision != expected_revision:
            raise ConflictError(f"项目版本冲突: 期望 r{expected_revision}，当前为 r{meta.revision}")
        if snapshot_label:
            self.create_snapshot(project_id, label=snapshot_label)
        target = safe_resolve_in_workspace(Path(meta.workspace_dir), rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return self.bump_revision(project_id)

    def delete_file(self, project_id: str, rel_path: str) -> ProjectMeta:
        meta = self.get_project(project_id)
        if rel_path == meta.main_file:
            raise ValueError("不能删除主文档文件")
        target = safe_resolve_in_workspace(Path(meta.workspace_dir), rel_path)
        if not target.is_file():
            raise FileNotFoundError(f"文件不存在: {rel_path}")
        target.unlink()
        return self.bump_revision(project_id)

    def _collect_text_snapshot(self, ws: Path) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        if not ws.is_dir():
            return snapshot
        for p in sorted(ws.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(ws).as_posix()
            if any(part in IGNORED_DIRS for part in rel.split("/")):
                continue
            if p.suffix.lower() in AUX_EXTENSIONS or rel.endswith(".synctex.gz"):
                continue
            if _is_text_file(p) and p.stat().st_size <= 2 * 1024 * 1024:
                snapshot[rel] = p.read_text(encoding="utf-8", errors="replace")
        return snapshot

    def create_snapshot(self, project_id: str, label: str = "手动快照") -> SnapshotSummary:
        meta = self.get_project(project_id)
        files = self._collect_text_snapshot(Path(meta.workspace_dir))
        sid = f"snap_{uuid.uuid4().hex[:10]}"
        now = utc_now()
        with self.connection() as db, db:
            db.execute(
                "INSERT INTO snapshots (id, project_id, revision, label, created_at, files_json) VALUES (?, ?, ?, ?, ?, ?)",
                (sid, project_id, meta.revision, label[:200], now, json.dumps(files, ensure_ascii=False)),
            )
        return SnapshotSummary(
            id=sid,
            project_id=project_id,
            revision=meta.revision,
            label=label[:200],
            created_at=now,
            file_count=len(files),
        )

    def list_snapshots(self, project_id: str) -> list[SnapshotSummary]:
        self.get_project(project_id)
        with self.connection() as db:
            rows = db.execute(
                "SELECT id, project_id, revision, label, created_at, files_json FROM snapshots WHERE project_id = ? ORDER BY created_at DESC LIMIT 80",
                (project_id,),
            ).fetchall()
        out = []
        for r in rows:
            files = json.loads(r["files_json"])
            out.append(
                SnapshotSummary(
                    id=r["id"],
                    project_id=r["project_id"],
                    revision=r["revision"],
                    label=r["label"],
                    created_at=r["created_at"],
                    file_count=len(files),
                )
            )
        return out

    def get_snapshot_files(self, project_id: str, snapshot_id: str) -> dict[str, str]:
        with self.connection() as db:
            row = db.execute(
                "SELECT files_json FROM snapshots WHERE project_id = ? AND id = ?",
                (project_id, snapshot_id),
            ).fetchone()
            if row is None:
                raise KeyError(f"未找到快照: {snapshot_id}")
            return json.loads(row["files_json"])

    def diff_snapshots(
        self,
        project_id: str,
        from_snapshot_id: str,
        to_snapshot_id: Optional[str] = None,
    ) -> dict[str, Any]:
        meta = self.get_project(project_id)
        left = self.get_snapshot_files(project_id, from_snapshot_id)
        right = (
            self.get_snapshot_files(project_id, to_snapshot_id)
            if to_snapshot_id
            else self._collect_text_snapshot(Path(meta.workspace_dir))
        )
        all_paths = sorted(set(left.keys()) | set(right.keys()))
        diffs = []
        for rel in all_paths:
            a = left.get(rel, "")
            b = right.get(rel, "")
            if a == b:
                continue
            udiff = "".join(
                difflib.unified_diff(
                    a.splitlines(keepends=True),
                    b.splitlines(keepends=True),
                    fromfile=f"a/{rel}",
                    tofile=f"b/{rel}",
                )
            )
            diffs.append({"path": rel, "diff": udiff, "added": rel not in left, "deleted": rel not in right})
        return {"from": from_snapshot_id, "to": to_snapshot_id or "current", "changes": diffs}

    def restore_snapshot(self, project_id: str, snapshot_id: str) -> ProjectMeta:
        meta = self.get_project(project_id)
        self.create_snapshot(project_id, label=f"恢复前自动备份 ({snapshot_id})")
        target_files = self.get_snapshot_files(project_id, snapshot_id)
        ws = Path(meta.workspace_dir)
        for rel, content in target_files.items():
            dest = safe_resolve_in_workspace(ws, rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        return self.bump_revision(project_id)

    # ── Project Chat Message & Material Accessors ──────────────────────────

    def add_chat_message(
        self,
        project_id: str,
        role: str,
        text: str,
        *,
        attachments: Optional[list[str]] = None,
        active_file: Optional[str] = None,
        patches: Optional[list[dict[str, Any]]] = None,
        diff: Optional[str] = None,
        applied: bool = False,
        message_id: Optional[str] = None,
    ) -> ProjectChatMessage:
        msg_id = message_id or str(uuid.uuid4())
        ts = utc_now()
        att_json = json.dumps(attachments or [], ensure_ascii=False)
        pat_json = json.dumps(patches or [], ensure_ascii=False)
        with self.connection() as db, db:
            db.execute(
                """
                INSERT INTO project_chat_messages
                (id, project_id, role, text, timestamp, attachments_json, active_file, patches_json, diff, applied)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (msg_id, project_id, role, text, ts, att_json, active_file, pat_json, diff, 1 if applied else 0),
            )
        parsed_patches = [ProjectFilePatch.model_validate(p) for p in (patches or [])]
        return ProjectChatMessage(
            id=msg_id,
            project_id=project_id,
            role=role,  # type: ignore[arg-type]
            text=text,
            timestamp=ts,
            attachments=attachments or [],
            active_file=active_file,
            patches=parsed_patches,
            diff=diff,
            applied=applied,
        )

    def list_chat_messages(self, project_id: str, limit: int = 50) -> list[ProjectChatMessage]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT id, project_id, role, text, timestamp, attachments_json, active_file, patches_json, diff, applied
                FROM project_chat_messages
                WHERE project_id = ?
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
            out: list[ProjectChatMessage] = []
            for r in rows:
                raw_patches = json.loads(r["patches_json"] or "[]")
                out.append(
                    ProjectChatMessage(
                        id=r["id"],
                        project_id=r["project_id"],
                        role=r["role"],
                        text=r["text"],
                        timestamp=r["timestamp"],
                        attachments=json.loads(r["attachments_json"] or "[]"),
                        active_file=r["active_file"],
                        patches=[ProjectFilePatch.model_validate(p) for p in raw_patches],
                        diff=r["diff"],
                        applied=bool(r["applied"]),
                    )
                )
            return out

    def get_chat_message(self, message_id: str) -> Optional[ProjectChatMessage]:
        with self.connection() as db:
            r = db.execute(
                """
                SELECT id, project_id, role, text, timestamp, attachments_json, active_file, patches_json, diff, applied
                FROM project_chat_messages
                WHERE id = ?
                """,
                (message_id,),
            ).fetchone()
            if not r:
                return None
            raw_patches = json.loads(r["patches_json"] or "[]")
            return ProjectChatMessage(
                id=r["id"],
                project_id=r["project_id"],
                role=r["role"],
                text=r["text"],
                timestamp=r["timestamp"],
                attachments=json.loads(r["attachments_json"] or "[]"),
                active_file=r["active_file"],
                patches=[ProjectFilePatch.model_validate(p) for p in raw_patches],
                diff=r["diff"],
                applied=bool(r["applied"]),
            )

    def mark_chat_message_applied(self, message_id: str, applied: bool = True) -> bool:
        with self.connection() as db, db:
            cursor = db.execute(
                "UPDATE project_chat_messages SET applied = ? WHERE id = ?",
                (1 if applied else 0, message_id),
            )
            return cursor.rowcount > 0

    def clear_chat_messages(self, project_id: str) -> int:
        with self.connection() as db, db:
            cursor = db.execute("DELETE FROM project_chat_messages WHERE project_id = ?", (project_id,))
            return cursor.rowcount

    def list_materials(self, project_id: str) -> list[FileEntry]:
        meta = self.get_project(project_id)
        ws = Path(meta.workspace_dir).resolve()
        mat_dir = ws / "materials"
        if not mat_dir.exists():
            return []
        entries: list[FileEntry] = []
        for p in sorted(mat_dir.rglob("*")):
            if p.is_file() and not any(part in IGNORED_DIRS for part in p.parts):
                rel = p.relative_to(ws).as_posix()
                entries.append(
                    FileEntry(
                        path=rel,
                        size=p.stat().st_size,
                        is_binary=not _is_text_file(p),
                        kind=_classify_kind(p),
                    )
                )
        return entries

    def save_material(
        self,
        project_id: str,
        rel_path: str,
        content: str | bytes,
        is_binary: bool = False,
    ) -> FileEntry:
        meta = self.get_project(project_id)
        ws = Path(meta.workspace_dir).resolve()
        clean = rel_path.strip().lstrip("/\\")
        if not clean.startswith("materials/"):
            clean = f"materials/{clean}"
        target = safe_resolve_in_workspace(ws, clean)
        target.parent.mkdir(parents=True, exist_ok=True)
        if is_binary or isinstance(content, bytes):
            bdata = content if isinstance(content, bytes) else content.encode("utf-8")
            target.write_bytes(bdata)
            size = len(bdata)
        else:
            target.write_text(content, encoding="utf-8")
            size = target.stat().st_size
        return FileEntry(
            path=clean,
            size=size,
            is_binary=is_binary or isinstance(content, bytes),
            kind=_classify_kind(target),
        )

