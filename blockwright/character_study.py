"""Консервативное сокращение ввода и нормализации символьной строки."""

from typing import Any

from . import model as M


def line_protocol(r: Any, position: int) -> tuple[int, str, list[M.Simple]] | None:
    """Сворачиваем только цельный известный протокол без посторонних эффектов."""
    b = r.b
    nodes = r.nodes[position : position + 4]
    if len(nodes) < 2 or not all(r.macro_free(node) for node in nodes[:2]):
        return None
    read, length = nodes[:2]
    if read.type != "if_statement" or not r.error_exit(read, set(), numeric_exit=True):
        return None
    call = r.negated(r.condition(read))
    if call is None or call.type != "call_expression":
        return None
    function = call.child_by_field_name("function")
    if function.type != "field_expression":
        return None
    owner = function.child_by_field_name("argument")
    if not any(b._name(owner, stream) for stream in ("cin", "wcin")):
        return None
    stream = b.raw(owner)
    args = r.member(call, stream, "getline")
    if args is None or len(args) != 2 or args[0].type != "identifier":
        return None
    name = b.raw(args[0])
    if not r.character_buffer(name) or args[1].type != "number_literal":
        return None
    # Указатель/ссылка на буфер не должен обходить распознаваемый протокол.
    if any(
        child.type in {"pointer_expression", "reference_declarator"}
        and name in b.raw(node)
        for node in r.nodes[:position]
        for child in r.walk(node)
    ):
        return None
    capacity = b.raw(args[1])
    if len(capacity) > 5 or not capacity.isdecimal() or not 1 <= int(capacity) <= 32767:
        return None

    if length.type == "declaration":
        declarators = length.children_by_field_name("declarator")
        if (
            b.raw(length.child_by_field_name("type")) != "int"
            or len(length.named_children) != 2
            or len(declarators) != 1
            or declarators[0].type != "init_declarator"
        ):
            return None
        target = declarators[0].child_by_field_name("declarator")
        value = b._unwrap(declarators[0].child_by_field_name("value"))
        if target is None or target.type != "identifier" or b.op_of(value) != "-":
            return None
        count, correction = b.sides(value)
        if (
            r.member(count, stream, "gcount") != []
            or r.member(r.negated(correction), stream, "eof") != []
        ):
            return None
        buffer = r.declarations[name][1]
        size = next(
            (
                b.raw(decl.child_by_field_name("size"))
                for decl in buffer.children_by_field_name("declarator")
                if decl.type == "array_declarator"
                and b.raw(decl.child_by_field_name("declarator")) == name
            ),
            "",
        )
        if (
            capacity.startswith("0")
            or size.startswith("0")
            or len(size) > 10
            or not size.isdecimal()
            or int(size) < int(capacity)
        ):
            return None
        return (
            position + 2,
            name,
            [M.Simple(M.PROCESS, f"{b.raw(target)} = длина {name}")],
        )

    if len(nodes) != 4 or not all(r.macro_free(node) for node in nodes[2:]):
        return None
    correction, loop = nodes[2:]
    assignment = b._expr(length)
    if (
        assignment is None
        or assignment.type != "assignment_expression"
        or b.op_of(assignment) != "="
    ):
        return None
    target = assignment.child_by_field_name("left")
    if (
        not r.scalar(target)
        or r.member(assignment.child_by_field_name("right"), stream, "gcount") != []
    ):
        return None
    count = b.raw(target)
    declaration = r.declarations.get(count)
    # Сужение gcount() меняет длину и границы обработки строки.
    if (
        declaration is None
        or b.raw(declaration[1].child_by_field_name("type")) != "int"
    ):
        return None
    if (
        correction.type != "if_statement"
        or correction.child_by_field_name("alternative") is not None
        or r.member(r.negated(r.condition(correction)), stream, "eof") != []
    ):
        return None
    statements = b._statements(correction.child_by_field_name("consequence"))
    if (
        len(statements) != 1
        or b.raw(b._expr(statements[0])).replace(" ", "") != count + "--"
    ):
        return None
    if loop.type != "for_statement":
        return None
    index = r.local_index(loop.child_by_field_name("initializer"))
    condition = b._unwrap(loop.child_by_field_name("condition"))
    if (
        not index
        or index == count
        or not r.increment(loop.child_by_field_name("update"), index)
    ):
        return None
    if b.op_of(condition) != "<" or tuple(b.raw(x) for x in b.sides(condition)) != (
        index,
        count,
    ):
        return None
    body = b._statements(loop.child_by_field_name("body"))
    if len(body) != 2 or not r.error_exit(body[1], set(), numeric_exit=True):
        return None
    element = f"{name}[{index}]"
    lowering = b._expr(body[0])
    if (
        lowering is None
        or lowering.type != "assignment_expression"
        or b.op_of(lowering) != "="
    ):
        return None
    if "".join(b.raw(lowering.child_by_field_name("left")).split()) != element:
        return None
    transform = lowering.child_by_field_name("right")
    if transform.type != "call_expression" or not any(
        b._name(transform.child_by_field_name("function"), fn)
        for fn in ("towlower", "tolower")
    ):
        return None
    values = b.call_args(transform)
    if len(values) != 1 or "".join(b.raw(values[0]).split()) != element:
        return None

    def character_test(node: Any) -> bool:
        node = b._unwrap(node)
        op = b.op_of(node)
        if op in {"&&", "||"}:
            return all(character_test(side) for side in b.sides(node))
        if op not in {"==", "!=", "<", ">", "<=", ">="}:
            return False
        left, right = b.sides(node)
        return (
            "".join(b.raw(left).split()) == element
            and right.type == "char_literal"
            or "".join(b.raw(right).split()) == element
            and left.type == "char_literal"
        )

    if not character_test(r.condition(body[1])):
        return None
    return (
        position + 4,
        name,
        [
            M.Simple(M.PROCESS, f"{count} = длина {name}"),
            M.Simple(M.PROCESS, f"Привести {name} к нижнему регистру"),
        ],
    )
