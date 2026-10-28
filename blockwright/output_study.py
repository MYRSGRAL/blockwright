"""Распознавание поэлементной печати массива как одного вывода."""

from collections.abc import Iterator
from typing import Any


def _loop_header(builder: Any, node: Any) -> tuple[str, str, bool] | None:
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
    return index, builder.t(length), local


def _walk(node: Any) -> Iterator[Any]:
    if node is not None:
        yield node
        for child in node.named_children:
            yield from _walk(child)


def _references(builder: Any, node: Any, index: str) -> bool:
    return any(n.type == "identifier" and builder.raw(n) == index for n in _walk(node))


def _index_disposable(builder: Any, loop: Any, index: str) -> bool:
    """Локальный индекс не наблюдается после печати до безусловной перезаписи."""
    ancestor = loop.parent
    tails = []
    current = loop
    declared = False
    while ancestor is not None and ancestor.type != "function_definition":
        if ancestor.type == "compound_statement":
            statements = builder._statements(ancestor)
            tails.extend(n for n in statements if n.start_byte >= current.end_byte)
            for statement in statements:
                if (
                    statement.type != "declaration"
                    or statement.end_byte > current.start_byte
                ):
                    continue
                for declarator in statement.children_by_field_name("declarator"):
                    variable = (
                        declarator.child_by_field_name("declarator")
                        if declarator.type == "init_declarator"
                        else declarator
                    )
                    if (
                        variable is not None
                        and variable.type == "identifier"
                        and builder.raw(variable) == index
                    ):
                        declared = True
        elif ancestor.type in {"for_statement", "while_statement", "do_statement"}:
            if _references(builder, ancestor, index):
                return False
        current, ancestor = ancestor, ancestor.parent
    if ancestor is None:
        return False
    body = ancestor.child_by_field_name("body")
    for node in _walk(body):
        if node.start_byte >= loop.start_byte:
            continue
        if node.type == "declaration":
            for declarator in node.children_by_field_name("declarator"):
                if any(
                    n.type == "reference_declarator" for n in _walk(declarator)
                ) and _references(builder, declarator, index):
                    return False
        if node.type == "lambda_expression" and any(
            n.type == "lambda_capture_specifier" and "&" in builder.raw(n)
            for n in node.named_children
        ):
            return False
        if node.type in {
            "pointer_expression",
            "call_expression",
            "lambda_expression",
        } and _references(builder, node, index):
            return False
    if not declared:
        return False

    def flow(node: Any, live: bool) -> tuple[bool, bool]:
        if not live:
            return True, False
        expression = builder._expr(node)
        if (
            expression.type == "assignment_expression"
            and builder.op_of(expression) == "="
        ):
            left, right = builder.sides(expression)
            if (
                builder.raw(left) == index
                and right is not None
                and right.type == "number_literal"
            ):
                return True, False
        if node.type == "compound_statement":
            for statement in builder._statements(node):
                safe, live = flow(statement, live)
                if not safe:
                    return False, live
            return True, live
        if node.type == "for_statement":
            initializer = node.child_by_field_name("initializer")
            if initializer is not None:
                safe, live = flow(initializer, live)
                if not safe:
                    return False, live
            if live and any(
                _references(builder, node.child_by_field_name(field), index)
                for field in ("condition", "update")
            ):
                return False, live
            safe, _ = flow(node.child_by_field_name("body"), live)
            return safe, live
        return not _references(builder, node, index), live

    live = True
    for statement in tails:
        safe, live = flow(statement, live)
        if not safe:
            return False
    return True


def _array_loop(builder: Any, node: Any) -> tuple[str, str] | None:
    indices = []
    bounds = []
    external = []
    arrays = []

    def output(statement: Any, depth: int) -> bool:
        if statement.type != "expression_statement":
            return False
        stream = builder._stream_parts(builder._expr(statement))
        if stream is None or stream[0] != "output":
            return False
        for part in stream[1]:
            if builder._display_manipulator(part):
                continue
            literal = builder._string_value(part)
            if literal is not None and not literal.strip(" ,;\t\r\n[]:"):
                continue
            if part.type == "char_literal" and builder.raw(part) in {
                "' '",
                "','",
                "';'",
                "'\\t'",
                "'\\n'",
                "'['",
                "']'",
                "':'",
            }:
                continue
            if part.type == "binary_expression" and builder.op_of(part) == "+":
                left, right = builder.sides(part)
                if (
                    left.type == "identifier"
                    and builder.raw(left) in indices[:depth]
                    and builder.raw(right) == "1"
                ):
                    continue
            array = part
            subscripts = []
            while array is not None and array.type == "subscript_expression":
                subscript = array.child_by_field_name("indices")
                if subscript is None or len(subscript.named_children) != 1:
                    return False
                value = subscript.named_children[0]
                if value.type != "identifier":
                    return False
                subscripts.insert(0, builder.raw(value))
                array = array.child_by_field_name("argument")
            if (
                array is None
                or array.type != "identifier"
                or builder.raw(array) not in builder._array_names
                or builder._array_ranks.get(builder.raw(array)) != depth
                or subscripts != indices[:depth]
            ):
                return False
            arrays.append(builder.raw(array))
        return True

    def visit(loop: Any) -> bool:
        header = _loop_header(builder, loop)
        if header is None or len(indices) >= 2:
            return False
        index, bound, local = header
        if (
            index in indices
            or bound in [*indices, index]
            or (not local and index in bounds)
        ):
            return False
        indices.append(index)
        bounds.append(bound)
        depth = len(indices)
        if not local:
            external.append(index)
        nested = 0
        for statement in builder._statements(loop.child_by_field_name("body")):
            if statement.type == "for_statement":
                nested += 1
                if nested > 1 or not visit(statement):
                    return False
            elif not output(statement, depth):
                return False
        return True

    if (
        not visit(node)
        or len(arrays) != 1
        or builder._array_ranks[arrays[0]] != len(indices)
        or any(not _index_disposable(builder, node, index) for index in external)
    ):
        return None
    return arrays[0], "][".join(bounds)


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
