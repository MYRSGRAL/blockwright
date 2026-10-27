"""Распознавание поэлементной печати массива как одного вывода."""

from bisect import bisect_left
from typing import Any


def _array_loop(builder: Any, node: Any) -> tuple[str, str] | None:
    if node.type != "for_statement":
        return None
    init = node.child_by_field_name("initializer")
    local = init is not None and init.type == "declaration"
    if local:
        typ = init.child_by_field_name("type")
        if (
            typ is None
            or typ.type not in {"primitive_type", "sized_type_specifier"}
            or builder.raw(typ) in builder._macro_names
            or any(word in builder.raw(typ) for word in ("float", "double", "void"))
            or any(builder.raw(c) == "volatile" for c in init.named_children)
        ):
            return None
        declarations = init.children_by_field_name("declarator")
        if len(declarations) != 1 or declarations[0].type != "init_declarator":
            return None
        variable = declarations[0].child_by_field_name("declarator")
        value = declarations[0].child_by_field_name("value")
    elif (
        init is not None
        and init.type == "assignment_expression"
        and builder.op_of(init) == "="
    ):
        variable, value = builder.sides(init)
    else:
        return None
    if variable is None or variable.type != "identifier" or builder.raw(value) != "0":
        return None
    index = builder.raw(variable)
    if index in builder._macro_names or (
        not local and index not in builder._integer_names
    ):
        return None
    condition = builder._unwrap(node.child_by_field_name("condition"))
    if (
        condition is None
        or condition.type != "binary_expression"
        or builder.op_of(condition) != "<"
    ):
        return None
    left, length = builder.sides(condition)
    if builder.raw(left) != index or length.type not in {
        "identifier",
        "number_literal",
    }:
        return None
    if (
        length.type == "identifier"
        and builder.raw(length) not in builder._integer_names
    ):
        return None
    if length.type == "number_literal":
        try:
            int(builder.raw(length).rstrip("uUlL"), 0)
        except ValueError:
            return None
    update = node.child_by_field_name("update")
    if (
        update is None
        or update.type != "update_expression"
        or builder.op_of(update) != "++"
        or builder.raw(update.child_by_field_name("argument")) != index
    ):
        return None
    if not local:
        positions = builder._identifier_positions.get(index, [])
        if bisect_left(positions, node.end_byte) < len(positions):
            return None
    arrays = []
    for statement in builder._statements(node.child_by_field_name("body")):
        if statement.type != "expression_statement":
            return None
        stream = builder._stream_parts(builder._expr(statement))
        if stream is None or stream[0] != "output":
            return None
        for part in stream[1]:
            if builder._display_manipulator(part):
                continue
            literal = builder._string_value(part)
            if literal is not None and not literal.strip(" ,;\t\r\n"):
                continue
            if part.type == "char_literal" and builder.raw(part) in {
                "' '",
                "','",
                "';'",
                "'\\t'",
                "'\\n'",
            }:
                continue
            if part.type != "subscript_expression":
                return None
            array = part.child_by_field_name("argument")
            indices = part.child_by_field_name("indices")
            if (
                array is None
                or array.type != "identifier"
                or builder.raw(array) not in builder._array_names
                or builder._array_ranks.get(builder.raw(array)) != 1
                or indices is None
            ):
                return None
            values = indices.named_children
            if (
                len(values) != 1
                or values[0].type != "identifier"
                or builder.raw(values[0]) != index
            ):
                return None
            arrays.append(builder.raw(array))
    if len(arrays) != 1:
        return None
    return arrays[0], builder.t(length)


def array_output(builder: Any, node: Any) -> str | None:
    """Возвращает a[n] только для чистой печати всех элементов от нуля до n-1."""
    result = _array_loop(builder, node)
    if result:
        return f"{result[0]}[{result[1]}]"
    if node.type != "if_statement":
        return None
    alternative = builder._statements(node.child_by_field_name("alternative"))
    if len(alternative) != 1:
        return None
    result = _array_loop(builder, alternative[0])
    if result is None:
        return None
    condition = builder._unwrap(node.child_by_field_name("condition"))
    if (
        condition is None
        or condition.type != "binary_expression"
        or builder.op_of(condition) != "=="
    ):
        return None
    a, b = builder.sides(condition)
    if {builder.raw(a), builder.raw(b)} != {result[1], "0"}:
        return None
    empty = builder._statements(node.child_by_field_name("consequence"))
    if len(empty) > 1:
        return None
    if empty:
        label = builder._static_stream_output(empty[0])
        if label is None or label.strip().lower() not in {
            "пустой",
            "пусто",
            "массив пуст",
            "массив пустой",
            "empty",
            "empty array",
            "[]",
        }:
            return None
    return f"{result[0]}[{result[1]}]"


def array_caption(builder: Any, node: Any) -> bool:
    """Текстовая подпись перед распознанным выводом относится к этому выводу."""
    label = builder._static_stream_output(node)
    return label is not None and label.endswith(":")
