"""Geometric layout of a flowchart.

Layout is structural: every construct (sequence, branch, loop, switch) places
itself and returns a Frame holding its shapes and edges.

Frame invariant: the entry is at (spine, 0) and the exit, if any, at
(spine, height); there is no exit when every path ends in a return. Chaining
frames is then just aligning them on a common vertical axis.

break / continue become open edges (pend) that bubble outwards along free
lanes until the loop or switch they belong to closes them.
"""

from typing import Any

from . import model as M
from .geometry import shape_port
from .text import text_width, wrap_text

FONT_SIZE = 44 / 3
LINE_H = 18
PAD_X = 14
PAD_Y = 8
MIN_W = 128
MIN_H = 34

V_GAP = 16  # vertical gap between blocks
BRANCH_GAP = 30  # branch offset from a decision
CH_GAP = 20  # loop-back / exit channel offset
LANE = 15  # lane pitch for break/continue edges
TOPJOIN = 22  # room above a loop for the back edge
LABEL_SIZE = 12


# ---------------------------------------------------------------- shapes
def make_shape(kind, text, opts):
    lines = wrap_text(text, opts.max_chars)
    tw = max(text_width(l, FONT_SIZE) for l in lines)
    th = len(lines) * LINE_H
    if kind == M.CONNECTOR:
        d = max(40.0, tw + 16, th + 16)
        w = h = d
    elif kind == M.DECISION:
        h = max(54.0, th * 2.0 + 16)
        w = max(150.0, tw * 1.75 + 28)
    elif kind == M.PREP:
        h = max(MIN_H, th + 2 * PAD_Y)
        w = max(MIN_W, tw + 2 * PAD_X + h * 0.8)
    elif kind in (M.IO, "input", "output"):
        h = max(MIN_H, th + 2 * PAD_Y)
        w = max(MIN_W, tw + 2 * PAD_X + h * 0.5)
    elif kind == M.PREDEF:
        h = max(MIN_H, th + 2 * PAD_Y)
        w = max(MIN_W, tw + 2 * PAD_X + 28)
    elif kind == M.TERMINATOR:
        h = max(34.0, th + 2 * PAD_Y - 2)
        w = max(MIN_W, tw + 2 * PAD_X + h * 0.6)
    else:
        h = max(MIN_H, th + 2 * PAD_Y)
        w = max(MIN_W, tw + 2 * PAD_X)
    return {
        "kind": kind,
        "x": 0.0,
        "y": 0.0,
        "text": text,
        "w": round(w, 2),
        "h": round(h, 2),
        "lines": lines,
        "notation": getattr(opts, "notation", "course"),
    }


def _edge(points, arrow=True):
    return {"points": [(float(x), float(y)) for x, y in points], "arrow": arrow}


def _label(x, y, text, anchor="start"):
    return {"x": float(x), "y": float(y), "text": text, "anchor": anchor}


# ----------------------------------------------------------------- frame
class Frame:
    __slots__ = (
        "edges",
        "entry_shape",
        "exit",
        "height",
        "labels",
        "page_count",
        "page_number",
        "pend",
        "shapes",
        "spine",
        "width",
    )

    def __init__(self):
        self.shapes = []
        self.edges = []
        self.labels = []
        self.pend = []
        self.spine = 0.0
        self.width = 0.0
        self.height = 0.0
        self.exit = None
        self.entry_shape = True
        self.page_number = 1
        self.page_count = 1

    def shift(self, dx, dy):
        if dx == 0 and dy == 0:
            return
        for s in self.shapes:
            s["x"] += dx
            s["y"] += dy
        for e in self.edges:
            e["points"] = [(x + dx, y + dy) for x, y in e["points"]]
        for p in self.pend:
            p["points"] = [(x + dx, y + dy) for x, y in p["points"]]
        for l in self.labels:
            l["x"] += dx
            l["y"] += dy
        self.spine += dx
        if self.exit is not None:
            self.exit = (self.exit[0] + dx, self.exit[1] + dy)

    def absorb(self, other):
        self.shapes.extend(other.shapes)
        self.edges.extend(other.edges)
        self.labels.extend(other.labels)
        self.pend.extend(other.pend)

    def bbox(self, include_pend=True):
        xs, ys = [], []
        for s in self.shapes:
            xs += [s["x"], s["x"] + s["w"]]
            ys += [s["y"], s["y"] + s["h"]]
        for e in self.edges:
            for x, y in e["points"]:
                xs.append(x)
                ys.append(y)
        for l in self.labels:
            w = text_width(l["text"], LABEL_SIZE)
            if l["anchor"] == "start":
                xs += [l["x"], l["x"] + w]
            elif l["anchor"] == "end":
                xs += [l["x"] - w, l["x"]]
            else:
                xs += [l["x"] - w / 2, l["x"] + w / 2]
            ys += [l["y"] - LABEL_SIZE, l["y"]]
        if include_pend:
            for p in self.pend:
                for x, y in p["points"]:
                    xs.append(x)
                    ys.append(y)
        if not xs:
            return (0.0, 0.0, 0.0, 0.0)
        return (min(xs), min(ys), max(xs), max(ys))

    def normalize(self):
        _merge_tails(self)
        b = self.bbox()
        if b[0] != 0:
            self.shift(-b[0], 0)
            b = self.bbox()
        self.width = max(b[2], 1.0)
        self.height = max(self.height, b[3])
        return self


def _merge_tails(frame: Frame) -> None:
    """Оставляет общий последний участок слияния и единственный наконечник."""
    groups: dict[tuple[float, float, int, int], list[dict[str, Any]]] = {}
    for edge in frame.edges:
        points = edge["points"]
        cleaned = [points[0]] if points else []
        for point in points[1:]:
            if point != cleaned[-1]:
                cleaned.append(point)
        edge["points"] = cleaned
        if len(cleaned) < 2:
            continue
        a, b = cleaned[-2:]
        dx, dy = b[0] - a[0], b[1] - a[1]
        if dx and dy:
            continue
        key = (b[0], b[1], (dx > 0) - (dx < 0), (dy > 0) - (dy < 0))
        groups.setdefault(key, []).append(edge)
    for (x, y, dx, dy), edges in groups.items():
        if len(edges) < 2:
            continue
        length = min(
            abs(e["points"][-1][0] - e["points"][-2][0])
            + abs(e["points"][-1][1] - e["points"][-2][1])
            for e in edges
        )
        join = (x - dx * length, y - dy * length)
        arrow = any(e.get("arrow") for e in edges)
        for edge in edges:
            edge["points"][-1] = join
            edge["arrow"] = False
        frame.edges.append(_edge([join, (x, y)], arrow=arrow))
    frame.edges = [e for e in frame.edges if len(set(e["points"])) > 1]


def _empty_frame():
    f = Frame()
    f.spine = 0.5
    f.width = 1.0
    f.height = 0.0
    f.exit = (0.5, 0.0)
    f.entry_shape = False
    return f


def escape(fr, pad=LANE):
    """Route open break/continue edges out past the frame's contents."""
    if not fr.pend:
        return
    b = fr.bbox(include_pend=False)
    cx = (b[0] + b[2]) / 2 if fr.shapes else fr.spine
    lefts, rights = [], []
    for p in fr.pend:
        side = p.get("side")
        if side is None:
            hx = p["points"][-1][0]
            if hx < cx - 1:
                side = "left"
            elif hx > cx + 1:
                side = "right"
            else:
                side = "right" if p["kind"] == "break" else "left"
            p["side"] = side
        (lefts if side == "left" else rights).append(p)
    rights.sort(key=lambda p: p["points"][-1][0])
    for i, p in enumerate(rights):
        hx, hy = p["points"][-1]
        tx = max(b[2] + pad * (i + 1), hx)
        if tx > hx + 0.5:
            p["points"].append((tx, hy))
    lefts.sort(key=lambda p: -p["points"][-1][0])
    for i, p in enumerate(lefts):
        hx, hy = p["points"][-1]
        tx = min(b[0] - pad * (i + 1), hx)
        if tx < hx - 0.5:
            p["points"].append((tx, hy))


# -------------------------------------------------------------- dispatch
def layout(item, opts):
    if item is None:
        return _empty_frame()
    if isinstance(item, M.Seq):
        return layout_seq(item.items, opts)
    if isinstance(item, M.Simple):
        return layout_simple(item, opts)
    if isinstance(item, getattr(M, "Return", ())):
        return layout_return(item, opts)
    if isinstance(item, M.Jump):
        return layout_jump(item, opts)
    if isinstance(item, M.If):
        return layout_if(item, opts)
    if isinstance(item, M.While):
        return layout_while(item, opts)
    if isinstance(item, M.DoWhile):
        return layout_do(item, opts)
    if isinstance(item, M.ForLoop):
        return layout_for(item, opts)
    if isinstance(item, M.Switch):
        return layout_switch(item, opts)
    raise TypeError(f"неизвестный элемент IR: {item!r}")


def layout_simple(item, opts):
    sh = make_shape(item.kind, item.text, opts)
    if item.kind == M.TERMINATOR and item.terminal:
        sh["role"] = "end"
    f = Frame()
    f.shapes.append(sh)
    f.spine = sh["w"] / 2
    sh["x"] = 0.0
    sh["y"] = 0.0
    f.width = sh["w"]
    f.height = sh["h"]
    f.exit = None if item.terminal else shape_port(sh, "bottom")
    return f


def layout_return(item: Any, opts: Any) -> Frame:
    """Сохраняет значение возврата и передаёт выход до границы функции."""
    if item.value and not (item.main and item.value.strip() in {"0", "+0", "-0"}):
        f = layout_simple(M.Simple(M.PROCESS, "Возврат " + item.value), opts)
        point = f.exit
    else:
        f = _empty_frame()
        point = f.exit
    f.exit = None
    f.pend.append(
        {
            "kind": "return",
            "points": [point, (point[0], point[1] + V_GAP)],
            "side": "right",
            "return_value": item.value,
        }
    )
    return f


def layout_jump(item, opts):
    f = Frame()
    f.spine = 0.5
    f.width = 1.0
    f.height = 0.0
    f.exit = None
    f.entry_shape = False
    f.pend.append({"kind": item.kind, "points": [(0.5, 0.0)], "side": None})
    return f


def layout_seq(items, opts):
    frames = [layout(i, opts) for i in items]
    if not frames:
        return _empty_frame()
    out = Frame()
    spine = max(f.spine for f in frames)
    y = 0.0
    prev = None
    for f in frames:
        if prev is not None and not f.shapes and not f.entry_shape:
            y = prev.exit[1] if prev.exit is not None else y - V_GAP
        f.shift(spine - f.spine, y)
        if prev is not None and prev.exit is not None:
            out.edges.append(_edge([prev.exit, (spine, y)], arrow=f.entry_shape))
        out.absorb(f)
        y += f.height + V_GAP
        prev = f
        if f.exit is None:
            break
    y -= V_GAP
    out.spine = spine
    out.height = y
    out.exit = prev.exit
    out.entry_shape = frames[0].entry_shape
    return out.normalize()


# ---------------------------------------------------------------- branch
def layout_if(item, opts):
    if getattr(opts, "study", False):
        return _study_if(item, opts)
    d = make_shape(M.DECISION, item.cond, opts)
    ft = layout(item.then_, opts)
    fe = layout(item.else_, opts) if item.else_ is not None else None

    dw, dh = d["w"], d["h"]
    d["x"] = -dw / 2
    d["y"] = 0.0
    cy = dh / 2
    col_top = dh + V_GAP

    f = Frame()
    f.shapes.append(d)

    x_then = -(dw / 2 + BRANCH_GAP) - (ft.width - ft.spine)
    ft.shift(x_then - ft.spine, col_top)
    f.edges.append(
        _edge([(-dw / 2, cy), (x_then, cy), (x_then, col_top)], arrow=ft.entry_shape)
    )
    f.labels.append(_label(-dw / 2 - 5, cy - 6, opts.yes_label, "end"))

    if fe is not None:
        x_else = (dw / 2 + BRANCH_GAP) + fe.spine
        fe.shift(x_else - fe.spine, col_top)
        f.edges.append(
            _edge([(dw / 2, cy), (x_else, cy), (x_else, col_top)], arrow=fe.entry_shape)
        )
    else:
        x_else = dw / 2 + BRANCH_GAP
    f.labels.append(_label(dw / 2 + 5, cy - 6, opts.no_label, "start"))

    f.absorb(ft)
    bottom = col_top + ft.height
    if fe is not None:
        f.absorb(fe)
        bottom = max(bottom, col_top + fe.height)

    merge_y = bottom + V_GAP
    merged = False
    if ft.exit is not None:
        f.edges.append(_edge([ft.exit, (x_then, merge_y), (0.0, merge_y)], arrow=False))
        merged = True
    if fe is not None:
        if fe.exit is not None:
            f.edges.append(
                _edge([fe.exit, (x_else, merge_y), (0.0, merge_y)], arrow=False)
            )
            merged = True
    else:
        f.edges.append(
            _edge(
                [(dw / 2, cy), (x_else, cy), (x_else, merge_y), (0.0, merge_y)],
                arrow=False,
            )
        )
        merged = True

    f.spine = 0.0
    f.height = merge_y if merged else bottom
    f.exit = (0.0, merge_y) if merged else None
    escape(f)
    return f.normalize()


def _ends_path(item: Any) -> bool:
    if isinstance(item, (M.Jump, M.Return)):
        return True
    if isinstance(item, M.Simple):
        return item.terminal
    if isinstance(item, M.Seq):
        return bool(item.items) and _ends_path(item.items[-1])
    return False


def _study_if(item: Any, opts: Any) -> Frame:
    """Основной путь идёт вниз, короткий ранний выход размещается справа."""
    guard = _ends_path(item.then_)
    main = layout(item.else_ if guard else item.then_, opts)
    side = layout(item.then_ if guard else item.else_, opts)
    main_label, side_label = (
        (opts.no_label, opts.yes_label) if guard else (opts.yes_label, opts.no_label)
    )
    d = make_shape(M.DECISION, item.cond, opts)
    d["x"] = -d["w"] / 2
    top = d["h"] + V_GAP
    main.shift(-main.spine, top)
    # Правый столбец учитывает всю вложенную основную ветку.
    side_x = max(d["w"] / 2, main.bbox()[2]) + BRANCH_GAP + side.spine
    side_top = d["h"] / 2 + V_GAP if guard else top
    side.shift(side_x - side.spine, side_top)
    f = Frame()
    f.shapes.append(d)
    f.edges.append(_edge([shape_port(d, "bottom"), (0, top)], arrow=main.entry_shape))
    cy = d["h"] / 2
    direct_jump = (
        not side.shapes
        and not side.edges
        and len(side.pend) == 1
        and side.pend[0]["kind"] in {"break", "continue"}
    )
    if direct_jump:
        # У перехода нет блока назначения: коридор строит замыкание цикла.
        side.pend[0]["points"] = [shape_port(d, "right")]
    else:
        f.edges.append(
            _edge(
                [shape_port(d, "right"), (side_x, cy), (side_x, side_top)],
                arrow=side.entry_shape,
            )
        )
    f.labels.extend(
        [_label(5, d["h"] + 12, main_label), _label(d["w"] / 2 + 5, cy - 6, side_label)]
    )
    f.absorb(main)
    f.absorb(side)
    bottom = max(top + main.height, side_top + side.height)
    merge = bottom if guard else bottom + V_GAP
    for branch in (main, side):
        if branch.exit is not None:
            x, y = branch.exit
            f.edges.append(_edge([(x, y), (x, merge), (0, merge)], arrow=False))
    f.spine = 0
    f.height = merge if main.exit is not None or side.exit is not None else bottom
    f.exit = (0, merge) if main.exit is not None or side.exit is not None else None
    escape(f)
    return f.normalize()


# ----------------------------------------------------------------- loops
def _close_loop(
    f,
    head_cx_half,
    body_bottom,
    body_exit,
    join_y,
    back_target_y,
    continue_target_y=None,
    continue_arrow_y=None,
):
    """Close a loop: back edge, exit, break/continue.

    Returns (exit_y, right_channel).
    """
    escape(f)
    b = f.bbox(include_pend=True)
    left_ch = min(b[0], -head_cx_half) - CH_GAP
    right_ch = max(b[2], head_cx_half) + CH_GAP

    ys = [body_bottom]
    ys += [p["points"][-1][1] for p in f.pend]
    back_y = body_bottom + 20 if body_exit is not None else None
    if back_y:
        ys.append(back_y)
    exit_y = max(ys) + 24

    if body_exit is not None:
        f.edges.append(
            _edge(
                [
                    body_exit,
                    (0.0, back_y),
                    (left_ch, back_y),
                    (left_ch, join_y),
                    (0.0, join_y),
                    (0.0, back_target_y),
                ],
                arrow=True,
            )
        )
    for p in list(f.pend):
        if p["kind"] == "return":
            continue
        hx, _hy = p["points"][-1]
        if p["kind"] == "continue":
            ty = continue_target_y if continue_target_y is not None else back_target_y
            jy = continue_arrow_y if continue_arrow_y is not None else join_y
            f.edges.append(
                _edge(p["points"] + [(hx, jy), (0.0, jy), (0.0, ty)], arrow=True)
            )
        else:
            f.edges.append(
                _edge(p["points"] + [(hx, exit_y), (0.0, exit_y)], arrow=False)
            )
    f.pend = [p for p in f.pend if p["kind"] == "return"]
    return exit_y, right_ch


def _pretest_loop(header_shape, body, opts, labels, pre=None, post=None):
    """Pre-test loop: while and both styles of for."""
    fb = layout(body, opts)
    f = Frame()

    y0 = 0.0
    if pre is not None:
        fp = layout_simple(pre, opts)
        fp.shift(-fp.spine, 0.0)
        f.absorb(fp)
        y0 = fp.height
        f.edges.append(_edge([(0.0, y0), (0.0, y0 + TOPJOIN)], arrow=True))
    else:
        f.edges.append(_edge([(0.0, 0.0), (0.0, TOPJOIN)], arrow=True))

    top = y0 + TOPJOIN
    join_y = y0 + TOPJOIN / 2
    d = header_shape
    d["x"] = -d["w"] / 2
    d["y"] = top
    f.shapes.append(d)
    hy = top + d["h"]
    cy = top + d["h"] / 2

    body_top = hy + V_GAP
    fb.shift(-fb.spine, body_top)
    f.edges.append(_edge([(0.0, hy), (0.0, body_top)], arrow=fb.entry_shape))
    if labels[0]:
        f.labels.append(_label(5, hy + 12, labels[0], "start"))
    f.absorb(fb)
    body_bottom = body_top + fb.height
    body_exit = fb.exit

    # the update step of an expanded for
    cont_target = None
    cont_join = None
    has_continue = any(p["kind"] == "continue" for p in f.pend)
    if post is not None and (body_exit is not None or has_continue):
        fu = layout_simple(post, opts)
        upd_top = body_bottom + V_GAP
        fu.shift(-fu.spine, upd_top)
        if body_exit is not None:
            f.edges.append(_edge([body_exit, (0.0, upd_top)], arrow=True))
        f.absorb(fu)
        cont_target = upd_top
        cont_join = upd_top - 14
        body_bottom = upd_top + fu.height
        body_exit = fu.exit

    exit_y, right_ch = _close_loop(
        f,
        d["w"] / 2,
        body_bottom,
        body_exit,
        join_y,
        top,
        continue_target_y=cont_target,
        continue_arrow_y=cont_join,
    )

    f.edges.append(
        _edge(
            [(d["w"] / 2, cy), (right_ch, cy), (right_ch, exit_y), (0.0, exit_y)],
            arrow=False,
        )
    )
    if labels[1]:
        f.labels.append(_label(d["w"] / 2 + 5, cy - 6, labels[1], "start"))

    f.spine = 0.0
    f.height = exit_y
    f.exit = (0.0, exit_y)
    return f.normalize()


def layout_while(item, opts):
    if getattr(opts, "study", False) and item.cond.strip() in {"true", "1"}:
        body = layout(item.body, opts)
        f = Frame()
        body.shift(-body.spine, TOPJOIN)
        f.edges.append(_edge([(0.0, 0.0), (0.0, TOPJOIN)], arrow=body.entry_shape))
        f.absorb(body)
        has_break = any(p["kind"] == "break" for p in f.pend)
        exit_y, _ = _close_loop(
            f, 0, TOPJOIN + body.height, body.exit, TOPJOIN / 2, TOPJOIN
        )
        f.spine = 0.0
        f.height = exit_y
        f.exit = (0.0, exit_y) if has_break else None
        f.entry_shape = False
        return f.normalize()
    d = make_shape(M.DECISION, item.cond, opts)
    return _pretest_loop(d, item.body, opts, (opts.yes_label, opts.no_label))


def layout_for(item, opts):
    if item.style == "hexagon" and not getattr(opts, "study", False):
        d = make_shape(M.PREP, item.header, opts)
        return _pretest_loop(d, item.body, opts, ("", ""))
    d = make_shape(M.DECISION, item.cond or "истина", opts)
    return _pretest_loop(
        d,
        item.body,
        opts,
        (opts.yes_label, opts.no_label),
        pre=item.init,
        post=item.update,
    )


def layout_do(item, opts):
    fb = layout(item.body, opts)
    f = Frame()
    top = TOPJOIN
    join_y = TOPJOIN / 2
    f.edges.append(_edge([(0.0, 0.0), (0.0, top)], arrow=fb.entry_shape))
    fb.shift(-fb.spine, top)
    f.absorb(fb)
    body_bottom = top + fb.height

    d = make_shape(M.DECISION, item.cond, opts)
    dec_y = body_bottom + V_GAP
    d["x"] = -d["w"] / 2
    d["y"] = dec_y
    f.shapes.append(d)
    cy = dec_y + d["h"] / 2
    if fb.exit is not None:
        f.edges.append(_edge([fb.exit, (0.0, dec_y)], arrow=True))

    escape(f)
    b = f.bbox(include_pend=True)
    right_ch = max(b[2], d["w"] / 2) + CH_GAP
    ys = [dec_y + d["h"]] + [p["points"][-1][1] for p in f.pend]
    exit_y = max(ys) + 24

    # "yes" goes back to the top of the body; for `until` it is "no"
    back, out = (
        (opts.no_label, opts.yes_label)
        if item.until
        else (opts.yes_label, opts.no_label)
    )
    f.edges.append(
        _edge(
            [
                (d["w"] / 2, cy),
                (right_ch, cy),
                (right_ch, join_y),
                (0.0, join_y),
                (0.0, top),
            ],
            arrow=True,
        )
    )
    f.labels.append(_label(d["w"] / 2 + 5, cy - 6, back, "start"))

    for p in list(f.pend):
        if p["kind"] == "return":
            continue
        hx, _hy = p["points"][-1]
        if p["kind"] == "continue":
            f.edges.append(
                _edge(
                    p["points"] + [(hx, dec_y - 14), (0.0, dec_y - 14), (0.0, dec_y)],
                    arrow=True,
                )
            )
        else:
            f.edges.append(
                _edge(p["points"] + [(hx, exit_y), (0.0, exit_y)], arrow=False)
            )
    f.pend = [p for p in f.pend if p["kind"] == "return"]

    f.edges.append(_edge([(0.0, dec_y + d["h"]), (0.0, exit_y)], arrow=False))
    f.labels.append(_label(5, dec_y + d["h"] + 12, out, "start"))

    f.spine = 0.0
    f.height = exit_y
    f.exit = (0.0, exit_y)
    return f.normalize()


# ---------------------------------------------------------------- switch
def layout_switch(item, opts):
    head = make_shape(M.DECISION, item.expr, opts)
    head["x"] = -head["w"] / 2
    head["y"] = 0.0
    hy = head["h"]
    bus_y = hy + 24
    col_top = bus_y + 28

    cols = [layout(c.body, opts) for c in item.cases]
    f = Frame()
    f.shapes.append(head)
    if not cols:
        f.spine = 0.0
        f.height = hy
        f.exit = (0.0, hy)
        return f.normalize()

    gap = 46
    total = sum(c.width for c in cols) + gap * (len(cols) - 1)
    x = -total / 2
    spines, rights, lefts = [], [], []
    for c in cols:
        c.shift(x, col_top)  # c.spine is absolute after the shift
        spines.append(c.spine)
        lefts.append(x)
        rights.append(x + c.width)
        x += c.width + gap

    f.edges.append(_edge([(0.0, hy), (0.0, bus_y)], arrow=False))
    if len(spines) > 1:
        f.edges.append(_edge([(spines[0], bus_y), (spines[-1], bus_y)], arrow=False))
    for sp, c in zip(spines, cols):
        f.edges.append(_edge([(sp, bus_y), (sp, col_top)], arrow=c.entry_shape))
    for sp, case in zip(spines, item.cases):
        f.labels.append(_label(sp + 6, col_top - 8, ", ".join(case.labels), "start"))

    for c in cols:
        f.absorb(c)
    bottom = col_top + max(c.height for c in cols)
    fall_y = bottom + 18
    merge_y = fall_y + 24

    has_default = any(c.is_default for c in item.cases)
    merged = False
    for i, (case, c, sp) in enumerate(zip(item.cases, cols, spines)):
        if c.exit is None:
            continue
        if case.fallthrough and i + 1 < len(cols):
            lane = (rights[i] + lefts[i + 1]) / 2
            f.edges.append(
                _edge(
                    [
                        c.exit,
                        (sp, fall_y),
                        (lane, fall_y),
                        (lane, col_top - 16),
                        (spines[i + 1], col_top - 16),
                        (spines[i + 1], col_top),
                    ],
                    arrow=True,
                )
            )
        else:
            f.edges.append(_edge([c.exit, (sp, merge_y), (0.0, merge_y)], arrow=False))
            merged = True

    # a break inside a case drops straight down: its column is empty below,
    # so no side detour is needed
    breaks = [p for p in f.pend if p["kind"] == "break"]
    f.pend = [p for p in f.pend if p["kind"] != "break"]
    for p in breaks:
        hx = p["points"][-1][0]
        f.edges.append(
            _edge(p["points"] + [(hx, merge_y), (0.0, merge_y)], arrow=False)
        )
        merged = True
    escape(f)

    if not has_default:
        b = f.bbox(include_pend=True)
        ex = max(b[2], head["w"] / 2) + CH_GAP
        f.edges.append(
            _edge(
                [(spines[-1], bus_y), (ex, bus_y), (ex, merge_y), (0.0, merge_y)],
                arrow=False,
            )
        )
        f.labels.append(
            _label(ex + 5, bus_y - 6, getattr(opts, "default_label", "иначе"), "start")
        )
        merged = True

    f.spine = 0.0
    f.height = merge_y if merged else bottom
    f.exit = (0.0, merge_y) if merged else None
    return f.normalize()


# -------------------------------------------------------------- function
def layout_function(fn, opts):
    start = M.Simple(M.TERMINATOR, opts.begin_label if opts.plain_begin else fn.short)
    fs = layout_simple(start, opts)
    fs.shapes[0]["role"] = "start"
    fb = layout(fn.body, opts)

    out = Frame()
    spine = max(fs.spine, fb.spine)
    fs.shift(spine - fs.spine, 0.0)
    out.absorb(fs)
    y = fs.height + V_GAP
    fb.shift(spine - fb.spine, y)
    out.edges.append(_edge([fs.exit, (spine, y)], arrow=fb.entry_shape))
    out.absorb(fb)
    y += fb.height

    returns = [p for p in out.pend if p["kind"] == "return"]
    if fb.exit is not None or returns:
        fe = layout_simple(M.Simple(M.TERMINATOR, opts.end_label), opts)
        fe.shapes[0]["role"] = "end"
        fe.shift(spine - fe.spine, y + V_GAP)
        join_y = y + V_GAP / 2
        if fb.exit is not None:
            out.edges.append(_edge([fb.exit, (spine, join_y)], arrow=False))
        # Основной возврат продолжается по вертикали; ранние вливаются в один коридор.
        last_shape_y = max(shape["y"] for shape in out.shapes)
        early: list[dict[str, Any]] = []
        for p in returns:
            origin = p["points"][0]
            if abs(origin[0] - spine) < 0.01 and origin[1] >= last_shape_y:
                edge = _edge([origin, (spine, join_y)], arrow=False)
                edge["return_value"] = p["return_value"]
                out.edges.append(edge)
            else:
                early.append(p)
        if early:
            lane = out.bbox()[2] + CH_GAP
            for p in early:
                hy = p["points"][-1][1]
                edge = _edge(p["points"] + [(lane, hy)], arrow=False)
                edge["return_value"] = p["return_value"]
                out.edges.append(edge)
            first_y = min(p["points"][-1][1] for p in early)
            out.edges.append(
                _edge([(lane, first_y), (lane, join_y), (spine, join_y)], arrow=False)
            )
        out.edges.append(_edge([(spine, join_y), (spine, y + V_GAP)], arrow=True))
        out.absorb(fe)
        y = y + V_GAP + fe.height

    # break/continue outside any loop: end the edge cleanly
    for p in out.pend:
        if p["kind"] != "return":
            out.edges.append(_edge(p["points"], arrow=False))
    out.pend = []

    out.spine = spine
    out.height = y
    out.exit = None
    return out.normalize()
