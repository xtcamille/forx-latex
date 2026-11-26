"""Pure-Python BibTeX parser, formatter, deduplicator, validator, and DOI/arXiv fetcher."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional

from .models import BibEntry

_ENTRY_HEAD_RE = re.compile(r"@([A-Za-z]+)\s*([({])\s*([^,\s]+)\s*,")
_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "article": ("author", "title", "journal", "year"),
    "inproceedings": ("author", "title", "booktitle", "year"),
    "conference": ("author", "title", "booktitle", "year"),
    "book": ("title", "publisher", "year"),
    "phdthesis": ("author", "title", "school", "year"),
    "mastersthesis": ("author", "title", "school", "year"),
    "techreport": ("author", "title", "institution", "year"),
    "misc": ("title", "year"),
}


def _read_balanced(text: str, start: int, open_ch: str, close_ch: str) -> tuple[str, int]:
    depth = 0
    i = start
    in_quotes = False
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != "\\"):
            if depth == 1:
                in_quotes = not in_quotes
        elif not in_quotes:
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start + 1 : i], i + 1
        i += 1
    return text[start + 1 :], len(text)


def _parse_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    i = 0
    n = len(body)
    while i < n:
        while i < n and body[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        eq = body.find("=", i)
        if eq == -1:
            break
        name = body[i:eq].strip().lower()
        i = eq + 1
        while i < n and body[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        if body[i] == "{":
            val, i = _read_balanced(body, i, "{", "}")
        elif body[i] == '"':
            j = i + 1
            while j < n:
                if body[j] == '"' and body[j - 1] != "\\":
                    break
                j += 1
            val = body[i + 1 : j]
            i = j + 1
        else:
            j = i
            while j < n and body[j] not in ",\r\n":
                j += 1
            val = body[i:j].strip()
            i = j
        if name:
            fields[name] = " ".join(val.split())
    return fields


def parse_bib(text: str) -> list[BibEntry]:
    """Parse BibTeX content into structured entries using brace-balanced scanning."""
    entries: list[BibEntry] = []
    pos = 0
    while pos < len(text):
        at = text.find("@", pos)
        if at == -1:
            break
        m = _ENTRY_HEAD_RE.match(text, at)
        if not m:
            pos = at + 1
            continue
        etype = m.group(1).lower()
        open_ch = m.group(2)
        close_ch = "}" if open_ch == "{" else ")"
        key = m.group(3).strip()
        brace_pos = text.find(open_ch, at)
        full_block, end_pos = _read_balanced(text, brace_pos, open_ch, close_ch)
        if etype in {"string", "preamble", "comment"}:
            pos = end_pos
            continue
        comma_idx = full_block.find(",")
        body = full_block[comma_idx + 1 :] if comma_idx != -1 else ""
        line = text.count("\n", 0, at) + 1
        entries.append(
            BibEntry(
                key=key,
                entry_type=etype,
                fields=_parse_fields(body),
                raw=text[at:end_pos].strip(),
                line=line,
            )
        )
        pos = end_pos
    return entries


def format_bib_entry(entry: BibEntry) -> str:
    preferred_order = ("author", "title", "journal", "booktitle", "year", "volume", "number", "pages", "publisher", "doi", "url")
    ordered_keys = [k for k in preferred_order if k in entry.fields] + sorted(
        k for k in entry.fields if k not in preferred_order
    )
    lines = [f"@{entry.entry_type}{{{entry.key},"]
    for idx, k in enumerate(ordered_keys):
        comma = "," if idx < len(ordered_keys) - 1 else ""
        lines.append(f"  {k:<10} = {{{entry.fields[k]}}}{comma}")
    lines.append("}")
    return "\n".join(lines)


def format_bib_file(entries: list[BibEntry]) -> str:
    return "\n\n".join(format_bib_entry(e) for e in entries) + ("\n" if entries else "")


def validate_bib(entries: list[BibEntry]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    seen_keys: dict[str, int] = {}
    seen_dois: dict[str, str] = {}
    seen_titles: dict[str, str] = {}

    for e in entries:
        if e.key in seen_keys:
            issues.append({
                "severity": "error",
                "key": e.key,
                "line": e.line,
                "message": f"重复引用 Key `{e.key}`（首次出现于第 {seen_keys[e.key]} 行）",
            })
        else:
            seen_keys[e.key] = e.line

        for req in _REQUIRED_FIELDS.get(e.entry_type, ("title", "year")):
            if not e.fields.get(req):
                issues.append({
                    "severity": "warning",
                    "key": e.key,
                    "line": e.line,
                    "message": f"@{e.entry_type} 条目 `{e.key}` 缺少必要字段 `{req}`",
                })

        doi = e.fields.get("doi", "").strip().lower()
        if doi:
            if doi in seen_dois:
                issues.append({
                    "severity": "warning",
                    "key": e.key,
                    "line": e.line,
                    "message": f"DOI `{doi}` 与 `{seen_dois[doi]}` 重复",
                })
            else:
                seen_dois[doi] = e.key

        norm_title = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", e.fields.get("title", "").lower())
        if norm_title:
            if norm_title in seen_titles:
                issues.append({
                    "severity": "warning",
                    "key": e.key,
                    "line": e.line,
                    "message": f"标题与 `{seen_titles[norm_title]}` 高度重复，建议去重合并",
                })
            else:
                seen_titles[norm_title] = e.key
    return issues


def deduplicate_bib(entries: list[BibEntry]) -> tuple[list[BibEntry], list[str]]:
    kept: list[BibEntry] = []
    removed: list[str] = []
    seen_keys: set[str] = set()
    seen_dois: set[str] = set()
    seen_titles: set[str] = set()

    for e in entries:
        doi = e.fields.get("doi", "").strip().lower()
        norm_title = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", e.fields.get("title", "").lower())
        if e.key in seen_keys or (doi and doi in seen_dois) or (norm_title and norm_title in seen_titles):
            removed.append(e.key)
            continue
        seen_keys.add(e.key)
        if doi:
            seen_dois.add(doi)
        if norm_title:
            seen_titles.add(norm_title)
        kept.append(e)
    return kept, removed


def fetch_bibtex_by_doi(doi: str, *, timeout: float = 12.0) -> BibEntry:
    import httpx
    clean_doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:")
    if not clean_doi or "/" not in clean_doi:
        raise ValueError(f"无效 DOI: {doi!r}")

    headers = {"Accept": "application/x-bibtex; charset=utf-8", "User-Agent": "hermes-latex/0.1"}
    resp = httpx.get(f"https://doi.org/{clean_doi}", headers=headers, follow_redirects=True, timeout=timeout)
    resp.raise_for_status()
    parsed = parse_bib(resp.text)
    if not parsed:
        raise ValueError(f"DOI {clean_doi} 未返回有效 BibTeX")
    return parsed[0]


def fetch_bibtex_by_arxiv(arxiv_id: str, *, timeout: float = 12.0) -> BibEntry:
    import httpx
    clean_id = arxiv_id.strip().removeprefix("arXiv:").removeprefix("https://arxiv.org/abs/").removeprefix("https://arxiv.org/pdf/").removesuffix(".pdf")
    if not clean_id:
        raise ValueError(f"无效 arXiv ID: {arxiv_id!r}")

    resp = httpx.get(
        "https://export.arxiv.org/api/query",
        params={"id_list": clean_id},
        timeout=timeout,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        raise ValueError(f"未找到 arXiv 文献: {clean_id}")
    title = " ".join((entry.findtext("atom:title", "", ns) or "").split())
    published = (entry.findtext("atom:published", "", ns) or "")[:4] or "2026"
    authors = [
        " ".join((a.findtext("atom:name", "", ns) or "").split())
        for a in entry.findall("atom:author", ns)
    ]
    if not title:
        raise ValueError(f"arXiv {clean_id} 元数据不完整")
    first_surname = re.sub(r"[^a-z]", "", (authors[0].split()[-1] if authors else "arxiv").lower()) or "arxiv"
    first_word = re.sub(r"[^a-z]", "", (title.split()[0] if title else "paper").lower()) or "paper"
    key = f"{first_surname}{published}{first_word}"
    bib = BibEntry(
        key=key,
        entry_type="article",
        fields={
            "author": " and ".join(authors) if authors else "Unknown",
            "title": title,
            "journal": f"arXiv preprint arXiv:{clean_id}",
            "year": published,
            "url": f"https://arxiv.org/abs/{clean_id}",
        },
    )
    bib.raw = format_bib_entry(bib)
    return bib


def search_crossref(query: str, *, limit: int = 5, timeout: float = 12.0) -> list[dict[str, Any]]:
    import httpx
    resp = httpx.get(
        "https://api.crossref.org/works",
        params={"query": query, "rows": max(1, min(limit, 15))},
        headers={"User-Agent": "hermes-latex/0.1 (mailto:noreply@example.org)"},
        timeout=timeout,
    )
    resp.raise_for_status()
    items = resp.json().get("message", {}).get("items", [])
    results = []
    for item in items:
        titles = item.get("title") or []
        authors = [
            f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
            for a in (item.get("author") or [])[:5]
        ]
        year_parts = ((item.get("published-print") or item.get("published-online") or {}).get("date-parts") or [[None]])[0]
        results.append({
            "title": titles[0] if titles else "",
            "authors": authors,
            "year": str(year_parts[0]) if year_parts and year_parts[0] else "",
            "venue": (item.get("container-title") or [""])[0],
            "doi": item.get("DOI", ""),
            "type": item.get("type", ""),
        })
    return results


def sync_from_bib_file(source_path: Path, target_path: Path) -> dict[str, Any]:
    """Merge entries from an external .bib (e.g., Zotero Better BibTeX auto-export) into target .bib."""
    if not source_path.is_file():
        raise FileNotFoundError(f"未找到源 BibTeX 文件: {source_path}")
    src_entries = parse_bib(source_path.read_text(encoding="utf-8", errors="replace"))
    dst_entries = parse_bib(target_path.read_text(encoding="utf-8", errors="replace")) if target_path.is_file() else []
    by_key = {e.key: e for e in dst_entries}
    added, updated = 0, 0
    for e in src_entries:
        if e.key not in by_key:
            dst_entries.append(e)
            by_key[e.key] = e
            added += 1
        elif format_bib_entry(by_key[e.key]) != format_bib_entry(e):
            idx = next(i for i, old in enumerate(dst_entries) if old.key == e.key)
            dst_entries[idx] = e
            by_key[e.key] = e
            updated += 1
    deduped, removed = deduplicate_bib(dst_entries)
    target_path.write_text(format_bib_file(deduped), encoding="utf-8")
    return {"added": added, "updated": updated, "deduped_removed": len(removed), "total": len(deduped)}
