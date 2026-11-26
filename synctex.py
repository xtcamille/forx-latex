"""Pure-Python .synctex.gz parser for bidirectional source <-> PDF navigation."""
from __future__ import annotations

import gzip
import re
from pathlib import Path
from typing import Optional

from .models import SyncTeXPoint

_INPUT_RE = re.compile(r"^Input:(\d+):(.+)$")
_PAGE_OPEN_RE = re.compile(r"^\{(\d+)$")
# Record formats: [tag,line:x,y:w,h,d | (tag,line:x,y:w,h,d | htag,line:x,y:w,h,d | xtag,line:x,y | k... | g...
_BOX_NODE_RE = re.compile(r"^[\[\(hv](\d+),(\d+)(?:,\d+)?:(-?\d+),(-?\d+):(-?\d+),(-?\d+),(-?\d+)")
_POINT_NODE_RE = re.compile(r"^[xk\$](\d+),(\d+)(?:,\d+)?:(-?\d+),(-?\d+)")

# 1 TeX scaled point = 1/65536 pt
_SP_PER_PT = 65536.0


def _read_synctex_text(path: Path) -> str:
    if path.suffix == ".gz" or path.name.endswith(".synctex.gz"):
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
            return f.read()
    return path.read_text(encoding="utf-8", errors="replace")


def _normalize_input_path(raw_path: str, workspace: Path) -> str:
    p = Path(raw_path.strip())
    ws = workspace.resolve()
    try:
        resolved = p.resolve()
        if resolved.is_relative_to(ws):
            return resolved.relative_to(ws).as_posix()
    except OSError:
        pass
    cleaned = raw_path.strip().replace("\\", "/")
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def parse_synctex(synctex_path: Path, workspace: Path) -> list[SyncTeXPoint]:
    """Parse .synctex.gz into normalized SyncTeXPoint records (coordinates in PDF points)."""
    if not synctex_path.is_file():
        return []
    text = _read_synctex_text(synctex_path)
    inputs: dict[str, str] = {}
    unit_scale = 1.0
    mag = 1000.0
    current_page = 0
    points: list[SyncTeXPoint] = []

    for line in text.splitlines():
        if not line:
            continue
        if line.startswith("Input:"):
            m = _INPUT_RE.match(line)
            if m:
                inputs[m.group(1)] = _normalize_input_path(m.group(2), workspace)
            continue
        if line.startswith("Unit:"):
            try:
                unit_scale = float(line.split(":", 1)[1].strip())
            except ValueError:
                pass
            continue
        if line.startswith("Magnification:"):
            try:
                mag = float(line.split(":", 1)[1].strip())
            except ValueError:
                pass
            continue
        pm = _PAGE_OPEN_RE.match(line)
        if pm:
            current_page = int(pm.group(1))
            continue
        if line == "}":
            continue
        if current_page <= 0:
            continue

        scale = (unit_scale * (mag / 1000.0)) / _SP_PER_PT
        bm = _BOX_NODE_RE.match(line)
        if bm:
            tag, ln, x, y, w, h, _d = bm.groups()
            fname = inputs.get(tag, "")
            if fname and int(ln) > 0:
                points.append(
                    SyncTeXPoint(
                        page=current_page,
                        x=round(int(x) * scale, 2),
                        y=round(int(y) * scale, 2),
                        width=round(max(0.0, int(w) * scale), 2),
                        height=round(max(0.0, int(h) * scale), 2),
                        file=fname,
                        line=int(ln),
                    )
                )
            continue

        pm_node = _POINT_NODE_RE.match(line)
        if pm_node:
            tag, ln, x, y = pm_node.groups()
            fname = inputs.get(tag, "")
            if fname and int(ln) > 0:
                points.append(
                    SyncTeXPoint(
                        page=current_page,
                        x=round(int(x) * scale, 2),
                        y=round(int(y) * scale, 2),
                        width=24.0,
                        height=10.0,
                        file=fname,
                        line=int(ln),
                    )
                )
    return points


def forward_search(synctex_path: Path, workspace: Path, rel_file: str, line: int) -> list[SyncTeXPoint]:
    """Map source (file, line) -> matching PDF page + box coordinates."""
    target_norm = rel_file.strip().replace("\\", "/").lstrip("./")
    nodes = parse_synctex(synctex_path, workspace)
    file_nodes = [
        n for n in nodes
        if n.file == target_norm or n.file.endswith("/" + target_norm) or target_norm.endswith("/" + n.file)
    ]
    if not file_nodes:
        return []
    exact = [n for n in file_nodes if n.line == line]
    if exact:
        return exact[:6]
    nearest = sorted(file_nodes, key=lambda n: (abs(n.line - line), n.page, n.y))
    return nearest[:4]


def inverse_search(synctex_path: Path, workspace: Path, page: int, x_pt: float, y_pt: float) -> Optional[SyncTeXPoint]:
    """Map PDF (page, x_pt, y_pt) -> nearest source (file, line)."""
    nodes = [n for n in parse_synctex(synctex_path, workspace) if n.page == page]
    if not nodes:
        return None

    def distance(node: SyncTeXPoint) -> tuple[int, float]:
        dx = 0.0
        if x_pt < node.x:
            dx = node.x - x_pt
        elif node.width > 0 and x_pt > node.x + node.width:
            dx = x_pt - (node.x + node.width)
        dy = 0.0
        top = node.y - node.height
        if y_pt < top:
            dy = top - y_pt
        elif y_pt > node.y:
            dy = y_pt - node.y
        inside = 0 if (dx == 0.0 and dy == 0.0) else 1
        return (inside, dx * dx + dy * dy)

    return min(nodes, key=distance)


def page_nodes(synctex_path: Path, workspace: Path, page: int) -> list[SyncTeXPoint]:
    """Return deduplicated SyncTeX line anchors for a given PDF page."""
    nodes = [n for n in parse_synctex(synctex_path, workspace) if n.page == page]
    seen: set[tuple[str, int]] = set()
    out: list[SyncTeXPoint] = []
    for n in nodes:
        key = (n.file, n.line)
        if key not in seen:
            seen.add(key)
            out.append(n)
    return out
