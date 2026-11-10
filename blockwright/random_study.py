"""Чистое заполнение int-матрицы стандартным генератором случайных чисел."""

from typing import Any

from .output_study import _index_disposable, _loop_header, _walk


def _standard_call(builder: Any, node: Any, name: str) -> list[Any] | None:
    node = builder._unwrap(node)
    if (
        node is None
        or node.type != "call_expression"
        or {name, "std"} & builder._shadowed
        or name in builder.known
        or {name, "std"} & builder._macro_names
        or not builder._name(node.child_by_field_name("function"), name)
    ):
        return None
    arguments = node.child_by_field_name("arguments")
    return list(arguments.named_children) if arguments is not None else None


def _literal(builder: Any, node: Any) -> int | None:
    node = builder._unwrap(node)
    if node is None or node.type != "number_literal":
        return None
    text = builder.raw(node)
    # Десятичные int без суффиксов исключают преобразования unsigned и переполнение.
    if (
        len(text) > 10
        or not text.isascii()
        or not text.isdecimal()
        or (len(text) > 1 and text[0] == "0")
    ):
        return None
    value = int(text)
    return value if value <= 2_147_483_647 else None


def _range(builder: Any, node: Any) -> tuple[int, int] | None:
    node = builder._unwrap(node)
    if node is None or node.type != "binary_expression" or builder.op_of(node) != "-":
        return None
    remainder, shift = builder.sides(node)
    offset = _literal(builder, shift)
    remainder = builder._unwrap(remainder)
    if (
        offset is None
        or remainder.type != "binary_expression"
        or builder.op_of(remainder) != "%"
    ):
        return None
    call, modulus = builder.sides(remainder)
    size = _literal(builder, modulus)
    # Стандарт гарантирует RAND_MAX >= 32767 даже на платформах с меньшим rand.
    if (
        size is None
        or not 1 <= size <= 32768
        or _standard_call(builder, call, "rand") != []
    ):
        return None
    return -offset, size - 1 - offset


def _plain_int(builder: Any, node: Any, name: str) -> bool:
    """Одноимённые объявления другого типа не позволяют доказать тип элемента."""
    root = node
    while root.parent is not None:
        root = root.parent
    found = False
    for declaration in _walk(root):
        if declaration.type not in {
            "declaration",
            "parameter_declaration",
            "optional_parameter_declaration",
        }:
            continue
        for declarator in declaration.children_by_field_name("declarator"):
            target = declarator
            while target is not None and target.type != "identifier":
                target = target.child_by_field_name("declarator")
            if target is None or builder.raw(target) != name:
                continue
            found = True
            typ = declaration.child_by_field_name("type")
            if (
                typ is None
                or typ.type != "primitive_type"
                or builder.raw(typ) != "int"
                or "int" in builder._macro_names
                or any(
                    builder.raw(c) in {"volatile", "const"}
                    for c in declaration.named_children
                )
            ):
                return False
    return found


def random_fill(builder: Any, node: Any) -> str | None:
    """Сворачивает только два вложенных цикла с единственным присваиванием."""
    indices = []
    bounds = []
    external = []
    outer = node
    for _ in range(2):
        header = _loop_header(builder, node)
        if header is None:
            return None
        index, bound, local = header
        # Узкие индексы могут оборачиваться до достижения границы цикла.
        if not _plain_int(builder, outer, index):
            return None
        condition = builder._unwrap(node.child_by_field_name("condition"))
        _, limit = builder.sides(condition)
        if limit.type == "identifier":
            if not _plain_int(builder, outer, builder.raw(limit)):
                return None
        elif _literal(builder, limit) is None:
            return None
        if index in indices or bound in [*indices, index] or index in bounds:
            return None
        indices.append(index)
        bounds.append(bound)
        if not local:
            external.append(index)
        body = builder._statements(node.child_by_field_name("body"))
        if len(body) != 1:
            return None
        node = body[0]
    if node.type != "expression_statement":
        return None
    expression = builder._unwrap(builder._expr(node))
    if expression.type != "assignment_expression" or builder.op_of(expression) != "=":
        return None
    array, value = builder.sides(expression)
    interval = _range(builder, value)
    if interval is None:
        return None
    for index in reversed(indices):
        if array is None or array.type != "subscript_expression":
            return None
        subscript = array.child_by_field_name("indices")
        if (
            subscript is None
            or len(subscript.named_children) != 1
            or subscript.named_children[0].type != "identifier"
            or builder.raw(subscript.named_children[0]) != index
        ):
            return None
        array = array.child_by_field_name("argument")
    name = builder.raw(array)
    if (
        array is None
        or array.type != "identifier"
        or name not in builder._array_names
        or builder._array_ranks.get(name) != 2
        or not _plain_int(builder, outer, name)
        or any(builder.raw(n) in builder._macro_names for n in _walk(outer))
        or any(not _index_disposable(builder, outer, i) for i in external)
    ):
        return None
    return f"{name}[{bounds[0]}][{bounds[1]}] = random({interval[0]}, {interval[1]})"


def random_seed(builder: Any, node: Any) -> bool:
    """Распознаёт самостоятельный srand(time(0)), не изменяя модель схемы."""
    if node.type != "expression_statement":
        return False
    arguments = _standard_call(builder, builder._expr(node), "srand")
    if arguments is None or len(arguments) != 1:
        return False
    time_arguments = _standard_call(builder, arguments[0], "time")
    if time_arguments is None or len(time_arguments) != 1:
        return False
    argument = builder._unwrap(time_arguments[0])
    return builder.raw(argument) in {"0", "nullptr"} and not any(
        builder.raw(n) in builder._macro_names for n in _walk(node)
    )
