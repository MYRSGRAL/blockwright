"""Общие контуры, порты и проверки геометрии учебных схем."""

from collections import defaultdict
from math import floor, hypot
from typing import Any

Shape = dict[str, Any]
Point = tuple[float, float]


def junction_arrows(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Стрелки перед Т-образными слияниями; пересечение без конца ребра не соединяет линии."""
    grid: dict[tuple[int, int], list[tuple[int, Point, Point]]] = defaultdict(list)
    cell = 128
    for index, edge in enumerate(edges):
        for a, b in zip(edge["points"], edge["points"][1:]):
            for x in range(
                floor(min(a[0], b[0]) / cell), floor(max(a[0], b[0]) / cell) + 1
            ):
                for y in range(
                    floor(min(a[1], b[1]) / cell), floor(max(a[1], b[1]) / cell) + 1
                ):
                    grid[x, y].append((index, a, b))
    arrows = []
    for index, edge in enumerate(edges):
        points = edge["points"]
        if edge.get("arrow", True) or len(points) < 2:
            continue
        p = points[-1]
        a = next(
            (
                q
                for q in reversed(points[:-1])
                if hypot(q[0] - p[0], q[1] - p[1]) > 0.01
            ),
            p,
        )
        length = hypot(p[0] - a[0], p[1] - a[1])
        if length < 6:
            continue
        ux, uy = (p[0] - a[0]) / length, (p[1] - a[1]) / length
        rays = {(round(-ux, 6), round(-uy, 6))}
        for other, start, end in grid[floor(p[0] / cell), floor(p[1] / cell)]:
            if other == index:
                continue
            dx, dy = end[0] - start[0], end[1] - start[1]
            span = hypot(dx, dy)
            if (
                not span
                or abs((p[0] - start[0]) * dy - (p[1] - start[1]) * dx) > 0.01 * span
            ):
                continue
            if not (
                min(start[0], end[0]) - 0.01 <= p[0] <= max(start[0], end[0]) + 0.01
                and min(start[1], end[1]) - 0.01 <= p[1] <= max(start[1], end[1]) + 0.01
            ):
                continue
            for q in (start, end):
                distance = hypot(q[0] - p[0], q[1] - p[1])
                if distance > 0.01:
                    rays.add(
                        (
                            round((q[0] - p[0]) / distance, 6),
                            round((q[1] - p[1]) / distance, 6),
                        )
                    )
        if len(rays) >= 3:
            stub = min(10.0, length - 3.0)
            arrows.append(
                {
                    "points": [
                        (p[0] - ux * (stub + 3), p[1] - uy * (stub + 3)),
                        (p[0] - ux * 3, p[1] - uy * 3),
                    ],
                    "arrow": True,
                }
            )
    return arrows


def allowed_ports(shape: Shape, outgoing: bool) -> tuple[str, ...]:
    """Более строгий вертикальный профиль в рамках п.4.2.4 ГОСТ 19.701-90."""
    if shape["kind"] == "connector" and shape.get("flow") == "up":
        return ("right",) if outgoing else ("left",)
    if shape["kind"] == "terminator":
        if shape.get("role") == "start" and not outgoing:
            return ()
        if shape.get("role") == "end" and outgoing:
            return ()
    if outgoing:
        return ("bottom", "right") if shape["kind"] == "decision" else ("bottom",)
    return ("top",)


def validate_ports(frame: Any) -> list[str]:
    """Проверяет порт и нормаль каждого привязанного конца соединения."""
    problems: list[str] = []
    ports: dict[tuple[float, float], list[tuple[Shape, str]]] = {}
    for shape in frame.shapes:
        for side in ("top", "bottom", "left", "right"):
            point = shape_port(shape, side)
            ports.setdefault((round(point[0], 2), round(point[1], 2)), []).append(
                (shape, side)
            )
    for edge in frame.edges:
        points = edge["points"]
        for outgoing, index, neighbour in ((True, 0, 1), (False, -1, -2)):
            if len(points) < 2:
                continue
            point = points[index]
            hits = ports.get((round(point[0], 2), round(point[1], 2)), [])
            for shape, side in hits:
                if side not in allowed_ports(shape, outgoing):
                    problems.append(f"Недопустимый порт {side}: {shape['text']}")
                    continue
                other = points[neighbour]
                dx, dy = other[0] - point[0], other[1] - point[1]
                correct = (
                    (side == "top" and abs(dx) < 0.1 and dy <= 0.1)
                    or (side == "bottom" and abs(dx) < 0.1 and dy >= -0.1)
                    or (side == "right" and abs(dy) < 0.1 and dx >= -0.1)
                    or (side == "left" and abs(dy) < 0.1 and dx <= 0.1)
                )
                if not correct:
                    problems.append(
                        f"Линия не направлена к центру порта {side}: {shape['text']}"
                    )
    return list(dict.fromkeys(problems))


def document_bottom(w: float, h: float, t: float) -> Point:
    """Кубическая волна от правого края к левому; x линейно зависит от t."""
    u = 1 - t
    return w * u, h * (
        0.8 * u**3 + 3 * 0.78 * u * u * t + 3 * 1.16 * u * t * t + 0.92 * t**3
    )


def shape_port(shape: Shape, side: str) -> Point:
    x, y, w, h = (float(shape[k]) for k in ("x", "y", "w", "h"))
    if side == "bottom":
        if shape["kind"] == "output" and shape.get("notation", "course") == "course":
            px, py = document_bottom(w, h, 0.5)
            return x + px, y + py
        return x + w / 2, y + h
    if side == "top":
        return x + w / 2, y
    if side == "left":
        inset = (
            min(h * 0.34, w * 0.3) / 2
            if shape["kind"] in ("io", "input")
            or (shape["kind"] == "output" and shape.get("notation") == "gost")
            else 0
        )
        return x + inset, y + h / 2
    if side == "right":
        inset = (
            min(h * 0.34, w * 0.3) / 2
            if shape["kind"] in ("io", "input")
            or (shape["kind"] == "output" and shape.get("notation") == "gost")
            else 0
        )
        return x + w - inset, y + h / 2
    raise ValueError(f"Неизвестный порт: {side}")


def validate_geometry(frame: Any) -> list[str]:
    """Проверяет наложение блоков и подписей, пересечение рёбер с блоками."""
    from .text import text_width

    problems: list[str] = []
    shapes = frame.shapes
    # Пространственный индекс исключает полный перебор блоков для каждого сегмента.
    cells: dict[tuple[int, int], set[int]] = defaultdict(set)
    pitch = 128
    for i, shape in enumerate(shapes):
        for cx in range(
            floor(shape["x"] / pitch), floor((shape["x"] + shape["w"]) / pitch) + 1
        ):
            for cy in range(
                floor(shape["y"] / pitch), floor((shape["y"] + shape["h"]) / pitch) + 1
            ):
                cells[cx, cy].add(i)

    def candidates(left: float, top: float, right: float, bottom: float) -> list[int]:
        found: set[int] = set()
        for cx in range(floor(left / pitch), floor(right / pitch) + 1):
            for cy in range(floor(top / pitch), floor(bottom / pitch) + 1):
                found.update(cells.get((cx, cy), ()))
        return sorted(found)

    for i, a in enumerate(shapes):
        for j in candidates(a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]):
            if j <= i:
                continue
            b = shapes[j]
            if (
                max(a["x"], b["x"]) < min(a["x"] + a["w"], b["x"] + b["w"]) - 0.1
                and max(a["y"], b["y"]) < min(a["y"] + a["h"], b["y"] + b["h"]) - 0.1
            ):
                problems.append(f"Перекрытие блоков: {a['text']} / {b['text']}")
    for label in frame.labels:
        width = text_width(label["text"], 12)
        left = label["x"] - (
            width
            if label["anchor"] == "end"
            else width / 2
            if label["anchor"] == "middle"
            else 0
        )
        for i in candidates(left, label["y"] - 12, left + width, label["y"]):
            s = shapes[i]
            if max(left, s["x"]) < min(left + width, s["x"] + s["w"]) and max(
                label["y"] - 12, s["y"]
            ) < min(label["y"], s["y"] + s["h"]):
                problems.append(
                    f"Подпись перекрывает блок: {label['text']} / {s['text']}"
                )
    for edge in frame.edges:
        for a, b in zip(edge["points"], edge["points"][1:]):
            for i in candidates(
                min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])
            ):
                s = shapes[i]
                left, right = s["x"] + 1, s["x"] + s["w"] - 1
                top, bottom = s["y"] + 1, s["y"] + s["h"] - 1
                if (
                    a[0] == b[0]
                    and left < a[0] < right
                    and max(min(a[1], b[1]), top) < min(max(a[1], b[1]), bottom)
                ):
                    # Волна занимает лишь часть ограничивающего прямоугольника.
                    if (
                        s["kind"] == "output"
                        and min(a[1], b[1]) >= shape_port(s, "bottom")[1] - 0.1
                    ):
                        continue
                    problems.append(f"Ребро пересекает блок: {s['text']}")
                if (
                    a[1] == b[1]
                    and top < a[1] < bottom
                    and max(min(a[0], b[0]), left) < min(max(a[0], b[0]), right)
                ):
                    problems.append(f"Ребро пересекает блок: {s['text']}")
    return list(dict.fromkeys(problems))
