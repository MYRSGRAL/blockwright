"""Краткие обозначения ввода и вывода без изменения вычислений."""

from . import model as M


def symbolic_labels(item: object) -> None:
    """Форма блока уже обозначает ввод/вывод; в подписи остаются операнды."""
    if isinstance(item, M.Simple):
        prefix = {M.INPUT: "Ввод ", M.OUTPUT: "Вывод "}.get(item.kind)
        if prefix and item.text.startswith(prefix):
            item.text = item.text[len(prefix) :]
    elif isinstance(item, M.Seq):
        result: list[object] = []
        for child in item.items:
            symbolic_labels(child)
            if (
                isinstance(child, M.Simple)
                and child.kind == M.INPUT
                and result
                and isinstance(result[-1], M.Simple)
                and result[-1].kind == M.INPUT
                and len(result[-1].text.split(", ")) + len(child.text.split(", ")) <= 2
                and all(
                    name.isidentifier()
                    for name in (result[-1].text + ", " + child.text).split(", ")
                )
            ):
                result[-1].text += ", " + child.text
            else:
                result.append(child)
        item.items = result
    elif isinstance(item, M.If):
        symbolic_labels(item.then_)
        symbolic_labels(item.else_)
    elif isinstance(item, (M.ForLoop, M.While, M.DoWhile)):
        symbolic_labels(item.body)
    elif isinstance(item, M.Switch):
        for case in item.cases:
            symbolic_labels(case.body)
