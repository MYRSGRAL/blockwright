"""Разбиение высоких схем без потери направленных переходов."""

import itertools
from copy import deepcopy
from typing import Any

from .layout import Frame

CONNECTOR_DIAMETER = 28


def split_pages(frame: Frame, opts: Any) -> list[Frame]:
    """Возвращает страницы с парными соединителями для каждого пересечения разреза."""
    limit = float(getattr(opts, "page_height", 1060))
    if limit < 0:
        raise ValueError("Высота страницы не может быть отрицательной")
    if limit == 0 or frame.height <= limit:
        return [deepcopy(frame)]
    span = limit - 96
    if span <= 80:
        raise ValueError("Высота страницы слишком мала для соединителей")
    cuts = [0.0]
    bottom = frame.bbox()[3]
    while bottom - cuts[-1] > span:
        target = cuts[-1] + span
        intervals = sorted((s["y"] - 4, s["y"] + s["h"] + 4) for s in frame.shapes)
        intervals.extend((l["y"] - 18, l["y"] + 8) for l in frame.labels)
        cut = target
        while True:
            collisions = [a for a, b in intervals if a < cut < b]
            if not collisions:
                break
            cut = min(collisions) - 1
        if cut <= cuts[-1] + 40:
            raise ValueError(
                "Блок или группа блоков выше доступной страницы; увеличьте page_height"
            )
        cuts.append(cut)
    cuts.append(max(bottom, cuts[-1] + 1))
    pages = [Frame() for _ in range(len(cuts) - 1)]
    for i, page in enumerate(pages):
        start, end = cuts[i : i + 2]
        page.spine = frame.spine
        page.width = frame.width
        page.height = end - start + 84
        page.page_number = i + 1
        page.page_count = len(pages)
        for s in frame.shapes:
            if start <= s["y"] < end:
                shape = deepcopy(s)
                shape["y"] += 42 - start
                page.shapes.append(shape)
        for l in frame.labels:
            if start <= l["y"] < end:
                label = deepcopy(l)
                label["y"] += 42 - start
                page.labels.append(label)

    def page_at(y: float) -> int:
        return min(sum(y >= cut for cut in cuts[1:-1]), len(pages) - 1)

    serial = 0
    occupied: dict[float, list[float]] = {}
    for edge in frame.edges:
        points = edge["points"]
        if len(points) < 2:
            continue
        index = page_at(points[0][1])
        current = [(points[0][0], points[0][1] - cuts[index] + 42)]
        for a, b in itertools.pairwise(points):
            boundaries = [
                c for c in cuts[1:-1] if (a[1] < c <= b[1]) or (b[1] < c <= a[1])
            ]
            boundaries.sort(reverse=b[1] < a[1])
            for boundary in boundaries:
                serial += 1
                label = f"A{serial}"
                t = (boundary - a[1]) / (b[1] - a[1])
                x = a[0] + t * (b[0] - a[0])
                down = b[1] > a[1]
                next_index = index + (1 if down else -1)
                positions = occupied.setdefault(boundary, [])
                pitch = 60
                lower, upper = 30.0, max(30.0, frame.width - 30)
                candidates = [max(lower, min(x, upper))]
                candidates.extend(
                    lower + step * pitch
                    for step in range(int((upper - lower) / pitch) + 1)
                )
                candidates.sort(key=lambda value: abs(value - x))
                lane = next(
                    (
                        value
                        for value in candidates
                        if all(abs(value - other) >= pitch for other in positions)
                    ),
                    upper + pitch,
                )
                while any(abs(lane - other) < pitch for other in positions):
                    lane += pitch
                positions.append(lane)
                cy = pages[index].height - 16 if down else 16
                ny = 16 if down else pages[next_index].height - 16
                end_y = cy - 14 if down else cy + 14
                crossing_y = boundary - cuts[index] + 42
                if down:
                    current.extend([(x, crossing_y), (lane, crossing_y), (lane, end_y)])
                else:
                    current.extend(
                        [
                            (x, crossing_y),
                            (lane - 30, crossing_y),
                            (lane - 30, cy),
                            (lane - 14, cy),
                        ]
                    )
                part = deepcopy(edge)
                part.update(points=current, arrow=True)
                pages[index].edges.append(part)
                for pi, yy, target in (
                    (index, cy, next_index),
                    (next_index, ny, index),
                ):
                    pages[pi].shapes.append(
                        {
                            "kind": "connector",
                            "x": lane - 14,
                            "y": yy - 14,
                            "w": 28,
                            "h": 28,
                            "lines": [label],
                            "text": label,
                            "page_target": target + 1,
                            "notation": "course",
                            "flow": "down" if down else "up",
                        }
                    )
                index = next_index
                next_y = boundary - cuts[index] + 42
                current = (
                    [(lane, ny + 14), (lane, next_y), (x, next_y)]
                    if down
                    else [
                        (lane + 14, ny),
                        (lane + 30, ny),
                        (lane + 30, next_y),
                        (x, next_y),
                    ]
                )
            current.append((b[0], b[1] - cuts[index] + 42))
        part = deepcopy(edge)
        part["points"] = current
        pages[index].edges.append(part)
    return pages


def export_pages(frame: Frame, opts: Any) -> list[Frame]:
    """Совместимое имя публичного интерфейса экспорта страниц."""
    return split_pages(frame, opts)
