"""Core unit and integration tests for forx-latex modules."""
from __future__ import annotations

import asyncio
import gzip
import io
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT.parent))

# Import via importlib package so relative imports inside forx-latex resolve cleanly.
import importlib.util

_PKG = "forx_latex_testpkg"
if _PKG not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        _PKG, PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)]
    )
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_PKG] = _mod
    _spec.loader.exec_module(_mod)

ai_engine = __import__(_PKG + ".ai_engine", fromlist=["csv_to_booktabs"])
bibtex = __import__(_PKG + ".bibtex", fromlist=["parse_bib"])
checker = __import__(_PKG + ".checker", fromlist=["run_preflight_check"])
compiler = __import__(_PKG + ".compiler", fromlist=["export_submission_zip"])
log_parser = __import__(_PKG + ".log_parser", fromlist=["parse_compile_log"])
project_parser = __import__(_PKG + ".project_parser", fromlist=["parse_project"])
storage = __import__(_PKG + ".storage", fromlist=["LatexStore"])
synctex = __import__(_PKG + ".synctex", fromlist=["forward_search"])
syntax_guard = __import__(_PKG + ".syntax_guard", fromlist=["protect_latex_tokens"])
templates = __import__(_PKG + ".templates", fromlist=["list_templates"])


def test_builtin_templates_and_zip_import():
    all_t = templates.list_templates()
    ids = {t.id for t in all_t}
    assert {"ieee-trans", "ieee-conf", "acm-sigconf", "acm-journal", "neurips", "cvpr", "usenix", "springer-lncs", "elsevier-bcra", "iet-blockchain", "cn-blockchain-journal", "cn-thesis"} <= ids

    for t in all_t:
        meta, files = templates.get_template_files(t.id, title="Test Paper", author="Alice")
        assert meta.main_file in files
        assert "refs.bib" in files
        assert "\\documentclass" in files[meta.main_file]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("myproj/main.tex", "\\documentclass{article}\\begin{document}Hi\\end{document}")
        zf.writestr("myproj/../../evil.tex", "bad")
    extracted = templates.extract_zip_template(buf.getvalue())
    assert "main.tex" in extracted
    assert all(".." not in k for k in extracted)


def test_multifile_project_parser(tmp_path):
    (tmp_path / "sections").mkdir()
    (tmp_path / "main.tex").write_text(
        "\\documentclass{IEEEtran}\n\\usepackage{booktabs}\n\\begin{document}\n"
        "\\input{sections/intro}\n\\bibliography{refs}\n\\end{document}\n",
        encoding="utf-8",
    )
    (tmp_path / "sections" / "intro.tex").write_text(
        "\\section{Introduction}\\label{sec:intro}\nAs shown in Table~\\ref{tab:res} and~\\cite{nakamoto2008bitcoin}.\n"
        "\\begin{table}\n\\caption{Main Results}\\label{tab:res}\n\\end{table}\n",
        encoding="utf-8",
    )
    (tmp_path / "refs.bib").write_text("@article{nakamoto2008bitcoin, author={S. Nakamoto}, title={Bitcoin}, journal={DBR}, year={2008}}", encoding="utf-8")

    st = project_parser.parse_project(tmp_path)
    assert st.included_files == ["main.tex", "sections/intro.tex"]
    assert "booktabs" in st.packages
    assert {l.key for l in st.labels} == {"sec:intro", "tab:res"}
    assert {r.key for r in st.refs} == {"tab:res"}
    assert st.cites[0].keys == ["nakamoto2008bitcoin"]
    assert len(st.outline) == 2


def test_bibtex_parse_validate_dedup_and_zotero_sync(tmp_path):
    raw = """
@article{k1,
  author = {Alice and Bob},
  title = {{Consensus} in {Blockchain} Systems},
  journal = {IEEE TIFS},
  year = {2025},
  doi = {10.1109/TEST.1}
}
@article{k2,
  author = {Alice and Bob},
  title = {Consensus in Blockchain Systems},
  year = {2025},
  doi = {10.1109/TEST.1}
}
"""
    entries = bibtex.parse_bib(raw)
    assert len(entries) == 2
    issues = bibtex.validate_bib(entries)
    assert any("journal" in i["message"] for i in issues)
    assert any("DOI" in i["message"] for i in issues)

    kept, removed = bibtex.deduplicate_bib(entries)
    assert len(kept) == 1 and removed == ["k2"]

    src = tmp_path / "zotero.bib"
    dst = tmp_path / "refs.bib"
    src.write_text(bibtex.format_bib_file(kept), encoding="utf-8")
    sync_res = bibtex.sync_from_bib_file(src, dst)
    assert sync_res["added"] == 1 and sync_res["total"] == 1


def test_synctex_forward_and_inverse(tmp_path):
    gz_path = tmp_path / "main.synctex.gz"
    content = (
        "SyncTeX Version:1\n"
        "Input:1:./main.tex\n"
        "Input:2:./sections/intro.tex\n"
        "Unit:1\nMagnification:1000\n"
        "Content:\n"
        "{1\n"
        "h2,15:6553600,13107200:13107200,786432,0\n"
        "}\n"
        "{2\n"
        "h1,40:6553600,26214400:13107200,786432,0\n"
        "}\n"
    )
    with gzip.open(gz_path, "wt", encoding="utf-8") as f:
        f.write(content)

    fwd = synctex.forward_search(gz_path, tmp_path, "sections/intro.tex", 15)
    assert fwd and fwd[0].page == 1 and fwd[0].line == 15 and fwd[0].x == 100.0

    inv = synctex.inverse_search(gz_path, tmp_path, page=2, x_pt=120.0, y_pt=398.0)
    assert inv is not None and inv.file == "main.tex" and inv.line == 40


def test_log_parser_extracts_file_line_and_overfull():
    sample_log = """
(./main.tex
(./sections/03_method.tex
! Undefined control sequence.
l.27 \\badcommand
                {x}
Overfull \\hbox (14.2pt too wide) in paragraph at lines 31--33
)
LaTeX Warning: Reference `fig:missing' on page 2 undefined on input line 19.
)
"""
    parsed = log_parser.parse_compile_log(sample_log, main_file="main.tex")
    assert len(parsed["errors"]) == 1
    assert parsed["errors"][0].file == "sections/03_method.tex"
    assert parsed["errors"][0].line == 27
    assert len(parsed["overfulls"]) == 1
    assert parsed["overfulls"][0].line == 31
    assert len(parsed["warnings"]) == 1


def test_syntax_guard_and_offline_booktabs_and_rewrite():
    src = r"As shown in~\cite{nakamoto2008bitcoin} and Eq.~\eqref{eq:1}, $\alpha + \beta = 1$ holds."
    prot = syntax_guard.protect_latex_tokens(src)
    assert "\\cite" not in prot.masked_text and "\\eqref" not in prot.masked_text and "$" not in prot.masked_text
    restored, ok, errs = syntax_guard.restore_latex_tokens(prot.masked_text.replace("holds", "remains valid"), prot)
    assert ok and not errs
    assert r"\cite{nakamoto2008bitcoin}" in restored and r"$\alpha + \beta = 1$" in restored

    bad_restored, bad_ok, bad_errs = syntax_guard.restore_latex_tokens("broken output", prot)
    assert not bad_ok and len(bad_errs) >= 3

    table = ai_engine.csv_to_booktabs("Method,TPS,Latency\nPBFT,1420,3.85\nOurs,4860,1.12", highlight_best="max")
    assert r"\toprule" in table and r"\textbf{4860}" in table

    @dataclass
    class FakeResp:
        text: str

    class FakeLlm:
        async def acomplete(self, **kwargs):
            return FakeResp(kwargs["input"][0]["text"].replace("holds", "holds strictly"))

    rw = asyncio.run(ai_engine.rewrite_latex_text(src, mode="polish", client=FakeLlm()))
    assert rw.ok and rw.integrity_ok and "holds strictly" in rw.rewritten_text


def test_preflight_checker_and_export_zip(tmp_path):
    store = storage.LatexStore(db_path=tmp_path / "test.db")
    meta = store.create_project(
        name="AuditTest",
        workspace_dir=tmp_path / "ws",
        double_blind=True,
        files={
            "main.tex": (
                "\\documentclass{article}\n\\begin{document}\n"
                "\\author{Zhang San}\n"
                "See Fig.~\\ref{fig:missing} and~\\cite{ghost2026}.\n"
                "Supported by NSFC Grant No. 62000001.\n"
                "Code: https://github.com/zhangsan/repo\n"
                "\\begin{equation}\n\\label{eq:unused}\n x = 1\n"
                "\\bibliography{refs}\n\\end{document}\n"
            ),
            "refs.bib": "@article{unusedkey, author={A}, title={B}, journal={J}, year={2024}}",
        },
    )
    report = checker.run_preflight_check(meta)
    assert not report.ok
    titles = " | ".join(i.title for i in report.issues)
    assert "未定义的交叉引用" in titles
    assert "未定义的文献引用" in titles
    assert "双盲模式疑似泄露作者信息" in titles
    assert "基金/致谢" in titles
    assert "未闭合的环境" in titles

    # Write aux junk and verify clean export excludes it
    (Path(meta.workspace_dir) / "main.aux").write_text("aux", encoding="utf-8")
    out_zip = tmp_path / "out.zip"
    exp = compiler.export_submission_zip(Path(meta.workspace_dir), out_zip)
    assert exp["count"] >= 2
    with zipfile.ZipFile(out_zip) as zf:
        names = zf.namelist()
        assert "main.tex" in names and "refs.bib" in names and "main.aux" not in names
