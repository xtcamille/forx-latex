"""TeX compiler detection, one-click Tectonic installer, multi-pass orchestration, and clean/arXiv export."""
from __future__ import annotations

import io
import os
import platform
import re
import shutil
import stat
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Any, Optional

from .log_parser import parse_compile_log
from .models import CompileResult, ProjectMeta
from .project_parser import parse_project
from .storage import AUX_EXTENSIONS, IGNORED_DIRS, bin_root

_PDF_PAGE_COUNT_RE = re.compile(rb"/Type\s*/Page\b(?!s)")


def count_pdf_pages(pdf_path: Path) -> Optional[int]:
    if not pdf_path.is_file():
        return None
    try:
        data = pdf_path.read_bytes()
    except OSError:
        return None
    # Prefer /Count inside /Pages root if present
    counts = [int(m) for m in re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", data, flags=re.S)]
    if counts:
        return max(counts)
    matches = _PDF_PAGE_COUNT_RE.findall(data)
    return len(matches) if matches else None


def _managed_tectonic_path() -> Path:
    exe = "tectonic.exe" if platform.system().lower() == "windows" else "tectonic"
    return bin_root() / exe


def detect_compilers() -> dict[str, Any]:
    """Detect managed Tectonic, system Tectonic, TeX Live/MiKTeX binaries, and optional PDF rasterizers."""
    managed = _managed_tectonic_path()
    found: dict[str, Optional[str]] = {
        "tectonic_managed": str(managed) if managed.is_file() else None,
        "tectonic": shutil.which("tectonic"),
        "latexmk": shutil.which("latexmk"),
        "xelatex": shutil.which("xelatex"),
        "pdflatex": shutil.which("pdflatex"),
        "lualatex": shutil.which("lualatex"),
        "bibtex": shutil.which("bibtex"),
        "biber": shutil.which("biber"),
        "latexdiff": shutil.which("latexdiff"),
        "pdftoppm": shutil.which("pdftoppm"),
    }
    active = None
    if found["tectonic_managed"]:
        active = "tectonic"
    elif found["tectonic"]:
        active = "tectonic"
    elif found["latexmk"]:
        active = "latexmk"
    elif found["xelatex"]:
        active = "xelatex"
    elif found["pdflatex"]:
        active = "pdflatex"
    elif found["lualatex"]:
        active = "lualatex"

    return {
        "ready": active is not None,
        "active_engine": active,
        "binaries": found,
        "platform": platform.system().lower(),
        "arch": platform.machine().lower(),
    }


def _select_tectonic_asset(assets: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    sys_name = platform.system().lower()
    arch = platform.machine().lower()
    is_arm = "arm" in arch or "aarch64" in arch

    if sys_name == "windows":
        needles = ["x86_64-pc-windows-msvc.zip", "windows-msvc.zip"]
    elif sys_name == "darwin":
        needles = ["aarch64-apple-darwin.tar.gz"] if is_arm else ["x86_64-apple-darwin.tar.gz"]
    else:
        needles = ["aarch64-unknown-linux-gnu.tar.gz"] if is_arm else ["x86_64-unknown-linux-gnu.tar.gz", "x86_64-unknown-linux-musl.tar.gz"]

    for needle in needles:
        for asset in assets:
            name = (asset.get("name") or "").lower()
            if needle in name and not name.endswith(".sha256"):
                return asset
    return None


def install_tectonic(*, timeout: float = 120.0) -> dict[str, Any]:
    """Download and install standalone Tectonic binary into profile plugin-data/bin (no full TeX distro needed)."""
    import httpx

    target = _managed_tectonic_path()
    if target.is_file():
        return {"ok": True, "already_installed": True, "path": str(target)}

    release_url = "https://api.github.com/repos/tectonic-typesetting/tectonic/releases/latest"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "hermes-latex/0.1"}
    resp = httpx.get(release_url, headers=headers, follow_redirects=True, timeout=20.0)
    resp.raise_for_status()
    data = resp.json()
    asset = _select_tectonic_asset(data.get("assets") or [])
    if not asset or not asset.get("browser_download_url"):
        raise RuntimeError(f"未找到适配当前系统 ({platform.system()}/{platform.machine()}) 的 Tectonic 发行包")

    dl = httpx.get(asset["browser_download_url"], headers=headers, follow_redirects=True, timeout=timeout)
    dl.raise_for_status()
    raw = dl.content
    exe_name = target.name

    target.parent.mkdir(parents=True, exist_ok=True)
    if asset["name"].lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            member = next((m for m in zf.infolist() if not m.is_dir() and Path(m.filename).name == exe_name), None)
            if member is None:
                raise RuntimeError(f"压缩包中未找到 {exe_name}")
            target.write_bytes(zf.read(member))
    else:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
            member = next((m for m in tf.getmembers() if m.isfile() and Path(m.name).name == exe_name), None)
            if member is None:
                raise RuntimeError(f"归档中未找到 {exe_name}")
            extracted = tf.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"无法解压 {exe_name}")
            target.write_bytes(extracted.read())

    if platform.system().lower() != "windows":
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    ver = subprocess.run([str(target), "--version"], capture_output=True, text=True, timeout=15)
    return {
        "ok": True,
        "already_installed": False,
        "path": str(target),
        "version": (ver.stdout or ver.stderr).strip(),
        "tag": data.get("tag_name", ""),
    }


def _resolve_compiler_command(meta: ProjectMeta, requested_engine: str) -> tuple[str, str]:
    info = detect_compilers()
    bins = info["binaries"]
    engine = meta.engine if requested_engine == "auto" else requested_engine

    if engine == "auto":
        if bins["tectonic_managed"]:
            return "tectonic", bins["tectonic_managed"]
        if bins["tectonic"]:
            return "tectonic", bins["tectonic"]
        if bins["latexmk"]:
            return "latexmk", bins["latexmk"]
        for cand in ("xelatex", "pdflatex", "lualatex"):
            if bins[cand]:
                return cand, bins[cand]
        raise FileNotFoundError("未找到可用的 LaTeX 编译器（Tectonic / TeX Live / MiKTeX）")

    if engine == "tectonic":
        p = bins["tectonic_managed"] or bins["tectonic"]
        if not p:
            raise FileNotFoundError("未安装 Tectonic 编译器")
        return "tectonic", p

    p = bins.get(engine)
    if not p:
        raise FileNotFoundError(f"未找到指定编译器: {engine}")
    return engine, p


def compile_project(
    meta: ProjectMeta,
    *,
    engine: str = "auto",
    timeout: int = 180,
) -> CompileResult:
    """Compile a LaTeX project with automatic multi-pass bibliography and SyncTeX output."""
    ws = Path(meta.workspace_dir).resolve()
    structure = parse_project(ws, meta.main_file)
    main_file = structure.main_file
    main_path = (ws / main_file).resolve()
    if not main_path.is_file():
        return CompileResult(
            ok=False,
            engine_used="none",
            hint=f"主文件不存在: {main_file}",
        )

    t0 = time.monotonic()
    try:
        eng, bin_path = _resolve_compiler_command(meta, engine)
    except FileNotFoundError as exc:
        return CompileResult(
            ok=False,
            engine_used="none",
            hint=(
                f"{exc}。本机尚未安装 TeX 发行版，可运行 `hermes latex setup` "
                "或调用工具 `latex_setup_compiler` 一键安装免配置轻量编译器 Tectonic。"
            ),
        )

    stem = main_path.stem
    pdf_path = main_path.with_suffix(".pdf")
    log_path = main_path.with_suffix(".log")
    synctex_path = main_path.parent / f"{stem}.synctex.gz"

    stdout_all = []
    stderr_all = []
    returncode = 0

    try:
        if eng == "tectonic":
            cmd = [bin_path, "-X", "compile", main_file, "--synctex", "--keep-logs", "--keep-intermediates"]
            proc = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
            returncode = proc.returncode
            stdout_all.append(proc.stdout or "")
            stderr_all.append(proc.stderr or "")
        elif eng == "latexmk":
            flag = "-xelatex" if structure.recommended_engine == "xelatex" or any(p in structure.packages for p in ("ctex", "xeCJK", "fontspec")) else "-pdf"
            cmd = [bin_path, flag, "-interaction=nonstopmode", "-synctex=1", "-file-line-error", main_file]
            proc = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
            returncode = proc.returncode
            stdout_all.append(proc.stdout or "")
            stderr_all.append(proc.stderr or "")
        else:
            # Multi-pass classic engine (pdflatex / xelatex / lualatex)
            base_cmd = [bin_path, "-interaction=nonstopmode", "-synctex=1", "-file-line-error", main_file]
            proc1 = subprocess.run(base_cmd, cwd=str(ws), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
            stdout_all.append(proc1.stdout or "")
            stderr_all.append(proc1.stderr or "")
            returncode = proc1.returncode
            if structure.bib_files or structure.cites:
                bib_bin = shutil.which("biber" if structure.uses_biber else "bibtex")
                if bib_bin:
                    bib_target = stem
                    bp = subprocess.run([bib_bin, bib_target], cwd=str(main_path.parent), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
                    stdout_all.append(bp.stdout or "")
                    stderr_all.append(bp.stderr or "")
            for _ in range(2):
                proc_n = subprocess.run(base_cmd, cwd=str(ws), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
                stdout_all.append(proc_n.stdout or "")
                stderr_all.append(proc_n.stderr or "")
                returncode = proc_n.returncode
    except subprocess.TimeoutExpired:
        return CompileResult(
            ok=False,
            engine_used=eng,
            compiler_path=bin_path,
            duration_ms=int((time.monotonic() - t0) * 1000),
            hint=f"编译超时（>{timeout}s），请检查是否存在死循环宏定义或网络拉取宏包受阻。",
        )

    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else "\n".join(stdout_all)
    stderr_text = "\n".join(stderr_all)
    parsed = parse_compile_log(log_text, stderr_text, main_file=main_file)
    ok = (returncode == 0) and pdf_path.is_file()
    page_count = count_pdf_pages(pdf_path) if pdf_path.is_file() else None

    tail_lines = (log_text or stderr_text).splitlines()[-40:]
    return CompileResult(
        ok=ok,
        engine_used=eng,
        compiler_path=bin_path,
        pdf_path=str(pdf_path) if pdf_path.is_file() else None,
        synctex_path=str(synctex_path) if synctex_path.is_file() else None,
        log_path=str(log_path) if log_path.is_file() else None,
        page_count=page_count,
        duration_ms=int((time.monotonic() - t0) * 1000),
        errors=parsed["errors"],
        warnings=parsed["warnings"],
        overfulls=parsed["overfulls"],
        raw_log_tail="\n".join(tail_lines),
        hint="编译成功" if ok else "编译存在错误，可调用 AI 自愈或查看结构化错误列表。",
    )


def clean_auxiliary_files(workspace: Path) -> list[str]:
    removed: list[str] = []
    ws = workspace.resolve()
    for p in sorted(ws.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() in AUX_EXTENSIONS or p.name.endswith(".synctex.gz"):
            try:
                rel = p.relative_to(ws).as_posix()
                p.unlink()
                removed.append(rel)
            except OSError:
                pass
    return removed


def export_submission_zip(workspace: Path, output_zip: Path, *, main_file: str = "main.tex", strip_comments: bool = False) -> dict[str, Any]:
    """Export a clean submission/arXiv source archive (no aux/build junk)."""
    ws = workspace.resolve()
    structure = parse_project(ws, main_file)
    included: list[str] = []

    candidates = set(structure.included_files) | set(structure.bib_files)
    # Add .sty/.cls and graphics
    for p in ws.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ws).as_posix()
        if any(part in IGNORED_DIRS for part in rel.split("/")):
            continue
        if p.suffix.lower() in {".sty", ".cls", ".bst", ".bbl"}:
            candidates.add(rel)
        elif p.suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg"}:
            # Keep graphics referenced in tex or under figures/
            stem_no_ext = rel.rsplit(".", 1)[0]
            if any(g == rel or g == stem_no_ext or rel.endswith(g) for g in structure.graphics_files) or rel.startswith(("fig", "image", "assets")):
                if p.name != Path(structure.main_file).with_suffix(".pdf").name:
                    candidates.add(rel)

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in sorted(candidates):
            src = (ws / rel).resolve()
            if not src.is_file() or not src.is_relative_to(ws):
                continue
            if strip_comments and src.suffix.lower() == ".tex":
                text = src.read_text(encoding="utf-8", errors="replace")
                cleaned = "\n".join(
                    line for line in text.splitlines()
                    if not line.lstrip().startswith("%")
                ) + "\n"
                zf.writestr(rel, cleaned.encode("utf-8"))
            else:
                zf.write(src, arcname=rel)
            included.append(rel)
    return {"zip_path": str(output_zip), "files": included, "count": len(included)}
