"""Rendering a laid-out chart to SVG.

The output is meant to import cleanly into vector editors:

* arrowheads are real polygons rather than markers, which Figma,
  Illustrator and Inkscape all keep;
* shapes live in named groups, so Figma shows a tidy layer tree;
* no external resources or CSS variables, just geometry.
"""

import itertools
import math
import re

from . import model as M
from .geometry import junction_arrows
from .layout import FONT_SIZE, LABEL_SIZE, LINE_H
from .text import FONT_MONO, FONT_UI, wrap_text, xml_escape

THEMES = {
    "light": {
        "stroke": "#1f2933",
        "text": "#10151b",
        "bg": "#ffffff",
        "fill": {
            M.PROCESS: "#ffffff",
            M.IO: "#eef4ff",
            M.DECISION: "#fff6e5",
            M.TERMINATOR: "#e9f3ec",
            M.PREDEF: "#f3eefc",
            M.PREP: "#e8f5f1",
            M.CONNECTOR: "#ffffff",
        },
    },
    "dark": {
        "stroke": "#9aa4b2",
        "text": "#e9eef5",
        "bg": "#11161d",
        "fill": {
            M.PROCESS: "#1a212b",
            M.IO: "#152436",
            M.DECISION: "#2c2517",
            M.TERMINATOR: "#152a20",
            M.PREDEF: "#231d33",
            M.PREP: "#14271f",
            M.CONNECTOR: "#1a212b",
        },
    },
}

# the active palette, switched by use_theme()
STROKE = "#000000"
LINE = STROKE
TEXT = "#000000"
BACKGROUND = THEMES["light"]["bg"]
FILL = {}


def use_theme(name):
    global STROKE, LINE, TEXT, BACKGROUND, FILL
    theme = {"stroke": "#000000", "text": "#000000", "bg": "#ffffff", "fill": {}}
    STROKE = LINE = theme["stroke"]
    TEXT = theme["text"]
    BACKGROUND = theme["bg"]
    FILL = dict(theme["fill"])
    return theme


KIND_RU = {
    M.PROCESS: "Процесс",
    M.IO: "ВводВывод",
    M.INPUT: "Ввод",
    M.OUTPUT: "Вывод",
    M.DECISION: "Решение",
    M.TERMINATOR: "Терминатор",
    M.PREDEF: "Подпрограмма",
    M.PREP: "Цикл",
    M.CONNECTOR: "Соединитель",
}

MARGIN = 12
TITLE_H = 34
ARROW_LEN = 9.0
ARROW_HALF = 3.6
CORNER = 0.0

_SLUG_BAD = re.compile(r"[^0-9A-Za-zА-Яа-яЁё_-]+")


def n(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def slug(text, limit=28):
    s = _SLUG_BAD.sub("_", (text or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:limit] or "блок"


def number_shapes(frame):
    """Number shapes top to bottom and give them layer names."""
    for i, s in enumerate(sorted(frame.shapes, key=lambda s: (s["y"], s["x"])), 1):
        s["n"] = i
        s["id"] = f"{i:02d}_{KIND_RU.get(s['kind'], 'Блок')}_{slug(s.get('text', ''))}"
    return frame


# ------------------------------------------------------------------ shapes
def shape_outline(s):
    x, y, w, h = s["x"], s["y"], s["w"], s["h"]
    k = s["kind"]
    fill = FILL.get(k, BACKGROUND)
    st = f'fill="{fill}" stroke="{STROKE}" stroke-width="1.6"'
    if k == M.TERMINATOR:
        return [
            (
                f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" '
                f'rx="{n(h / 2)}" ry="{n(h / 2)}" {st}/>'
            )
        ]
    if k == M.DECISION:
        pts = f"{n(x + w / 2)},{n(y)} {n(x + w)},{n(y + h / 2)} {n(x + w / 2)},{n(y + h)} {n(x)},{n(y + h / 2)}"
        return [f'<polygon points="{pts}" {st}/>']
    if k == "output" and s.get("notation", "course") == "course":
        return [
            (
                f'<path d="M{n(x)},{n(y)} L{n(x + w)},{n(y)} L{n(x + w)},{n(y + 0.8 * h)} '
                f'C{n(x + 2 * w / 3)},{n(y + 0.78 * h)} {n(x + w / 3)},{n(y + 1.16 * h)} {n(x)},{n(y + 0.92 * h)} Z" {st}/>'
            )
        ]
    if k in (M.IO, "input", "output"):
        s2 = min(h * 0.34, w * 0.3)
        pts = f"{n(x + s2)},{n(y)} {n(x + w)},{n(y)} {n(x + w - s2)},{n(y + h)} {n(x)},{n(y + h)}"
        return [f'<polygon points="{pts}" {st}/>']
    if k == M.PREP:
        c = min(h * 0.5, w * 0.25)
        pts = (
            f"{n(x + c)},{n(y)} {n(x + w - c)},{n(y)} {n(x + w)},{n(y + h / 2)} "
            f"{n(x + w - c)},{n(y + h)} {n(x + c)},{n(y + h)} {n(x)},{n(y + h / 2)}"
        )
        return [f'<polygon points="{pts}" {st}/>']
    if k == M.PREDEF:
        out = [f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" {st}/>']
        for dx in (11, w - 11):
            out.append(
                f'<line x1="{n(x + dx)}" y1="{n(y)}" x2="{n(x + dx)}" y2="{n(y + h)}" '
                f'stroke="{STROKE}" stroke-width="1.4"/>'
            )
        return out
    if k == M.CONNECTOR:
        return [
            f'<circle cx="{n(x + w / 2)}" cy="{n(y + h / 2)}" r="{n(w / 2)}" {st}/>'
        ]
    return [(f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" {st}/>')]


def shape_text(s):
    cx, cy = s["x"] + s["w"] / 2, s["y"] + s["h"] / 2
    if s["kind"] == M.OUTPUT and s.get("notation", "course") == "course":
        cy = s["y"] + 0.43 * s["h"]
    lines = s["lines"]
    y0 = cy - (len(lines) - 1) * LINE_H / 2 + FONT_SIZE * 0.36
    return [
        f'<text x="{n(cx)}" y="{n(y0 + i * LINE_H)}" text-anchor="middle" '
        f'font-family="{FONT_MONO}" font-size="{FONT_SIZE}" fill="{TEXT}">'
        f"{xml_escape(ln)}</text>"
        for i, ln in enumerate(lines)
    ]


def _shape_group(s):
    gid = xml_escape(s.get("id") or slug(s.get("text", "")))
    body = shape_outline(s) + shape_text(s)
    return f'<g id="{gid}">\n  ' + "\n  ".join(body) + "\n</g>"


# ------------------------------------------------------------------- edges
def _clean_points(pts):
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - out[-1][0]) > 0.01 or abs(p[1] - out[-1][1]) > 0.01:
            out.append(p)
    return out


def round_path(pts, r=CORNER):
    """Polyline with rounded corners."""
    if len(pts) < 3:
        return "M" + " L".join(f"{n(x)},{n(y)}" for x, y in pts)
    d = [f"M{n(pts[0][0])},{n(pts[0][1])}"]
    for i in range(1, len(pts) - 1):
        (ax, ay), (cx, cy), (bx, by) = pts[i - 1], pts[i], pts[i + 1]
        l1 = math.hypot(cx - ax, cy - ay)
        l2 = math.hypot(bx - cx, by - cy)
        cross = abs((cx - ax) * (by - cy) - (cy - ay) * (bx - cx))
        rr = min(r, l1 / 2 if l1 else 0, l2 / 2 if l2 else 0)
        if rr < 1 or cross < 1 or not l1 or not l2:
            d.append(f" L{n(cx)},{n(cy)}")
            continue
        d.append(
            f" L{n(cx + (ax - cx) / l1 * rr)},{n(cy + (ay - cy) / l1 * rr)}"
            f" Q{n(cx)},{n(cy)} "
            f"{n(cx + (bx - cx) / l2 * rr)},{n(cy + (by - cy) / l2 * rr)}"
        )
    d.append(f" L{n(pts[-1][0])},{n(pts[-1][1])}")
    return "".join(d)


def edge_svg(e):
    pts = e["points"]
    if len(pts) < 2:
        return []
    pts = _clean_points(pts)
    if len(pts) < 2:
        return []
    out = []
    for index, ((ax, ay), (bx, by)) in enumerate(itertools.pairwise(pts)):
        if index > 0 and by - ay > 60 and abs(ax - bx) < 0.01:
            my = (ay + by) / 2
            out.append(
                f'<path d="M{n(ax)},{n(my)} L{n(ax - ARROW_HALF)},{n(my - ARROW_LEN)} '
                f'L{n(ax + ARROW_HALF)},{n(my - ARROW_LEN)} Z" fill="{LINE}"/>'
            )
        if ay - by > 35 and abs(ax - bx) < 0.01:
            my = (ay + by) / 2
            out.append(
                f'<path d="M{n(ax)},{n(my)} L{n(ax - ARROW_HALF)},{n(my + ARROW_LEN)} '
                f'L{n(ax + ARROW_HALF)},{n(my + ARROW_LEN)} Z" fill="{LINE}"/>'
            )
        if ax - bx > 35 and abs(ay - by) < 0.01:
            mx = (ax + bx) / 2
            out.append(
                f'<path d="M{n(mx)},{n(ay)} L{n(mx + ARROW_LEN)},{n(ay - ARROW_HALF)} '
                f'L{n(mx + ARROW_LEN)},{n(ay + ARROW_HALF)} Z" fill="{LINE}"/>'
            )
    if e.get("arrow"):
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        bx, by = x1 - ux * ARROW_LEN, y1 - uy * ARROW_LEN
        px, py = -uy * ARROW_HALF, ux * ARROW_HALF
        if L > ARROW_LEN:
            pts = pts[:-1] + [(bx, by)]
        out.append(
            f'<path d="M{n(x1)},{n(y1)} L{n(bx + px)},{n(by + py)} '
            f'L{n(bx - px)},{n(by - py)} Z" fill="{LINE}"/>'
        )
    out.insert(
        0,
        f'<path d="{round_path(pts)}" fill="none" stroke="{LINE}" '
        f'stroke-width="1.5" stroke-linecap="round"/>',
    )
    return out


def label_svg(l):
    return (
        f'<text x="{n(l["x"])}" y="{n(l["y"])}" text-anchor="{l["anchor"]}" '
        f'font-family="{FONT_UI}" font-size="{LABEL_SIZE}" fill="{TEXT}">'
        f"{xml_escape(l['text'])}</text>"
    )


# -------------------------------------------------------------------- SVG
def render_svg(frame, title=None, standalone=True, name="Блок-схема", theme=None):
    use_theme(theme)
    number_shapes(frame)
    b = frame.bbox()
    x0, y0, x1, y1 = b
    top = MARGIN + (TITLE_H if title else 0)
    w = (x1 - x0) + 2 * MARGIN
    h = (y1 - y0) + MARGIN + top
    dx = MARGIN - x0
    dy = top - y0

    parts = [
        (
            f'<rect id="Фон" x="0" y="0" width="{n(w)}" height="{n(h)}" '
            f'fill="{BACKGROUND}"/>'
        )
    ]
    if title:
        parts.append(
            f'<text id="Заголовок" x="{n(w / 2)}" y="{n(MARGIN + 6)}" '
            f'text-anchor="middle" font-family="{FONT_UI}" font-size="15" '
            f'font-weight="600" fill="{TEXT}">{xml_escape(title)}</text>'
        )

    lines = []
    for e in frame.edges:
        lines.extend(edge_svg(e))
    for arrow in junction_arrows(frame.edges):
        lines.extend(edge_svg(arrow))
    labels = [label_svg(l) for l in frame.labels]
    shapes = [
        _shape_group(s) for s in sorted(frame.shapes, key=lambda s: (s["y"], s["x"]))
    ]

    parts.append(
        f'<g id="{xml_escape(slug(name, 48))}" transform="translate({n(dx)},{n(dy)})">'
    )
    parts.append('<g id="Связи">\n' + "\n".join(lines) + "\n</g>")
    if labels:
        parts.append('<g id="Подписи">\n' + "\n".join(labels) + "\n</g>")
    parts.append('<g id="Блоки">\n' + "\n".join(shapes) + "\n</g>")
    parts.append("</g>")

    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{n(w)}" height="{n(h)}" '
        f'viewBox="0 0 {n(w)} {n(h)}" role="img">'
    )
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n' if standalone else ""
    return xml + head + "\n" + "\n".join(parts) + "\n</svg>\n"


# ------------------------------------------------------ editor model
def frame_to_dict(frame, opts):
    """Serialise the chart for the browser editor, which redraws it itself."""
    number_shapes(frame)
    return {
        "shapes": [
            {
                "id": s["id"],
                "kind": s["kind"],
                "x": round(s["x"], 2),
                "y": round(s["y"], 2),
                "w": round(s["w"], 2),
                "h": round(s["h"], 2),
                "text": s.get("text", ""),
                "notation": s.get("notation", "course"),
                **({"role": s["role"]} if "role" in s else {}),
                **({"flow": s["flow"]} if "flow" in s else {}),
                "lines": list(s.get("lines", [])),
                **({"page_target": s["page_target"]} if "page_target" in s else {}),
            }
            for s in sorted(frame.shapes, key=lambda s: (s["y"], s["x"]))
        ],
        "edges": [
            {
                "points": [[round(x, 2), round(y, 2)] for x, y in e["points"]],
                "arrow": bool(e.get("arrow")),
                **({"return_value": e["return_value"]} if "return_value" in e else {}),
            }
            for e in frame.edges
        ],
        "labels": [
            {
                "x": round(l["x"], 2),
                "y": round(l["y"], 2),
                "text": l["text"],
                "anchor": l["anchor"],
            }
            for l in frame.labels
        ],
        "page_number": frame.page_number,
        "page_count": frame.page_count,
        "maxChars": opts.max_chars,
        "notation": getattr(opts, "notation", "course"),
    }


def rewrap(text, max_chars):
    return wrap_text(text, max_chars)
