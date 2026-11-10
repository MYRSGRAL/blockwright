"""Консервативные учебные группы для заполнения и суммирования матрицы."""

from typing import Any

from . import model as M
from .input_study import _retry_context
from .output_study import _index_disposable, _loop_header, _walk
from .random_study import _literal, _plain_int, _range, random_seed


def _macro_free(builder: Any, node: Any) -> bool:
    keywords = {"if", "else", "for", "return", "int", "long", "const", "volatile"}
    return not (keywords & builder._macro_names) and not any(
        builder.raw(child) in builder._macro_names for child in _walk(node)
    )


def _static_array(builder: Any, node: Any, name: str, rank: int, typ: str) -> bool:
    root = node
    while root.parent is not None:
        root = root.parent
    found = False
    for declaration in _walk(root):
        if declaration.type not in {"declaration", "parameter_declaration"}:
            continue
        for declarator in declaration.children_by_field_name("declarator"):
            target = declarator
            dimensions = 0
            while target is not None and target.type == "array_declarator":
                dimensions += 1
                target = target.child_by_field_name("declarator")
            if target is None or builder.raw(target) != name:
                continue
            found = True
            type_node = declaration.child_by_field_name("type")
            if (
                dimensions != rank
                or target.type != "identifier"
                or type_node is None
                or builder.raw(type_node) != typ
                or any(
                    builder.raw(c) in {"volatile", "const", "static", "extern"}
                    for c in declaration.named_children
                )
                or not _macro_free(builder, declaration)
            ):
                return False
    return found and builder._array_ranks.get(name) == rank


def _loops(
    builder: Any, outer: Any, inner: Any, disposable: bool
) -> tuple[list[str], list[str]] | None:
    indices: list[str] = []
    bounds: list[str] = []
    for loop in (outer, inner):
        header = _loop_header(builder, loop)
        if header is None:
            return None
        index, bound, local = header
        condition = builder._unwrap(loop.child_by_field_name("condition"))
        _, limit = builder.sides(condition)
        if (
            not _plain_int(builder, outer, index)
            or (
                limit.type == "identifier"
                and not _plain_int(builder, outer, builder.raw(limit))
            )
            or (limit.type != "identifier" and _literal(builder, limit) is None)
            or (
                disposable
                and not local
                and not _index_disposable(builder, outer, index)
            )
        ):
            return None
        indices.append(index)
        bounds.append(bound)
    if len(set(indices)) != 2 or set(indices) & set(bounds):
        return None
    return indices, bounds


def _element(builder: Any, node: Any, indices: list[str]) -> str | None:
    for index in reversed(indices):
        if node is None or node.type != "subscript_expression":
            return None
        subscript = node.child_by_field_name("indices")
        if (
            subscript is None
            or len(subscript.named_children) != 1
            or subscript.named_children[0].type != "identifier"
            or builder.raw(subscript.named_children[0]) != index
        ):
            return None
        node = node.child_by_field_name("argument")
    return builder.raw(node) if node is not None and node.type == "identifier" else None


def _equality(builder: Any, node: Any, value: str) -> str | None:
    condition = builder._unwrap(node.child_by_field_name("condition"))
    if (
        condition is None
        or condition.type != "binary_expression"
        or builder.op_of(condition) != "=="
    ):
        return None
    left, right = builder.sides(condition)
    if (
        left.type != "identifier"
        or builder.raw(right) != value
        or not _plain_int(builder, node, builder.raw(left))
    ):
        return None
    return builder.raw(left)


def _literal_output(builder: Any, node: Any) -> bool:
    if node.type != "expression_statement":
        return False
    stream = builder._stream_parts(builder._expr(node))
    return bool(stream and stream[0] == M.OUTPUT and stream[1]) and all(
        part.type in {"string_literal", "concatenated_string"} for part in stream[1]
    )


def conditional_matrix_fill(
    builder: Any, nodes: list[Any], position: int
) -> tuple[int, list[object]] | None:
    """Условный seed, приглашение и поэлементный выбор ручного/случайного ввода."""
    if position < 0 or position + 3 > len(nodes):
        return None
    seed, prompt, outer = nodes[position : position + 3]
    if seed.type != "if_statement" or prompt.type != "if_statement":
        return None
    mode = _equality(builder, seed, "2")
    seed_body = builder._statements(seed.child_by_field_name("consequence"))
    prompt_body = builder._statements(prompt.child_by_field_name("consequence"))
    if (
        mode is None
        or _equality(builder, prompt, "1") != mode
        or seed.child_by_field_name("alternative") is not None
        or prompt.child_by_field_name("alternative") is not None
        or len(seed_body) != 1
        or not random_seed(builder, seed_body[0])
        or len(prompt_body) != 1
        or not _literal_output(builder, prompt_body[0])
        or not builder._prompt(prompt_body[0])
        or not all(_macro_free(builder, n) for n in (seed, prompt, outer))
    ):
        return None
    outer_body = builder._statements(outer.child_by_field_name("body"))
    if len(outer_body) != 1:
        return None
    inner = outer_body[0]
    headers = _loops(builder, outer, inner, True)
    if headers is None:
        return None
    indices, bounds = headers
    if mode in indices or mode in bounds:
        return None
    inner_body = builder._statements(inner.child_by_field_name("body"))
    if len(inner_body) != 1 or inner_body[0].type != "if_statement":
        return None
    choice = inner_body[0]
    if _equality(builder, choice, "1") != mode:
        return None
    manual = builder._statements(choice.child_by_field_name("consequence"))
    automatic = builder._statements(choice.child_by_field_name("alternative"))
    if len(manual) != 1 or len(automatic) != 1:
        return None
    context = _retry_context(builder, choice, manual)
    read = manual[0]
    if (
        read.type != "if_statement"
        or not context.error_exit(read, set())
        or not _literal_output(
            builder, builder._statements(read.child_by_field_name("consequence"))[0]
        )
    ):
        return None
    target = context.failed_read(context.condition(read), "")
    name = _element(builder, target, indices)
    assignment = builder._unwrap(builder._expr(automatic[0]))
    if (
        name is None
        or not _static_array(builder, outer, name, 2, "int")
        or automatic[0].type != "expression_statement"
        or assignment.type != "assignment_expression"
        or builder.op_of(assignment) != "="
    ):
        return None
    left, value = builder.sides(assignment)
    interval = _range(builder, value)
    if _element(builder, left, indices) != name or interval is None:
        return None
    array = f"{name}[{bounds[0]}][{bounds[1]}]"
    return position + 3, [
        M.If(
            builder.cond_text(choice.child_by_field_name("condition")),
            M.Seq([M.Simple(M.INPUT, "Ввод " + array)]),
            M.Seq(
                [M.Simple(M.PROCESS, f"{array} = random({interval[0]}, {interval[1]})")]
            ),
        )
    ]


def _loop_model(builder: Any, node: Any, body: M.Seq) -> M.ForLoop:
    init = node.child_by_field_name("initializer")
    condition = node.child_by_field_name("condition")
    update = node.child_by_field_name("update")
    header = (
        builder._canonical_for(init, condition, update)
        if builder.opts.for_style in {"auto", "hexagon"}
        else None
    )
    if header:
        return M.ForLoop(body, style="hexagon", header=header)
    return M.ForLoop(
        body,
        init=builder._simple_from_node(init),
        cond=builder.cond_text(condition),
        update=builder._simple_from_node(update),
    )


def summed_matrix_output(builder: Any, node: Any) -> list[object] | None:
    """Печать int-матрицы и точное сохранение циклов суммирования long long."""
    if node.type != "for_statement" or not _macro_free(builder, node):
        return None
    body = builder._statements(node.child_by_field_name("body"))
    if len(body) != 3:
        return None
    initialize, inner, newline = body
    headers = _loops(builder, node, inner, False)
    if headers is None:
        return None
    indices, bounds = headers
    statements = builder._statements(inner.child_by_field_name("body"))
    if len(statements) != 2:
        return None
    output, addition = statements
    init = builder._unwrap(builder._expr(initialize))
    add = builder._unwrap(builder._expr(addition))
    if (
        initialize.type != "expression_statement"
        or addition.type != "expression_statement"
        or init.type != "assignment_expression"
        or builder.op_of(init) != "="
        or add.type != "assignment_expression"
        or builder.op_of(add) != "+="
    ):
        return None
    total, zero = builder.sides(init)
    destination, element = builder.sides(add)
    sum_name = _element(builder, total, indices[:1])
    name = _element(builder, element, indices)
    if (
        sum_name is None
        or name is None
        or name == sum_name
        or builder.raw(zero) != "0"
        or builder.raw(total) != builder.raw(destination)
        or not _static_array(builder, node, sum_name, 1, "long long")
        or not _static_array(builder, node, name, 2, "int")
    ):
        return None
    stream = (
        builder._stream_parts(builder._expr(output))
        if output.type == "expression_statement"
        else None
    )
    if stream is None or stream[0] != M.OUTPUT or len(stream[1]) != 2:
        return None
    printed, separator = stream[1]
    if (
        _element(builder, printed, indices) != name
        or not (
            builder._string_value(separator) == " " or builder.raw(separator) == "' '"
        )
        or newline.type != "expression_statement"
    ):
        return None
    line_stream = builder._stream_parts(builder._expr(newline))
    if (
        line_stream is None
        or line_stream[0] != M.OUTPUT
        or len(line_stream[1]) != 1
        or not (
            builder.raw(line_stream[1][0]) == '"\\n"'
            or builder.raw(line_stream[1][0]) == "'\\n'"
        )
    ):
        return None
    inner_model = _loop_model(
        builder,
        inner,
        M.Seq(
            [
                M.Simple(
                    M.PROCESS,
                    f"{builder.t(total)} = {builder.t(total)} + {builder.t(element)}",
                )
            ]
        ),
    )
    outer_model = _loop_model(
        builder, node, M.Seq([*builder.stmt_as_process(initialize), inner_model])
    )
    return [M.Simple(M.OUTPUT, f"Вывод {name}[{bounds[0]}][{bounds[1]}]"), outer_model]
