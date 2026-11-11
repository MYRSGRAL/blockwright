"""Распознавание счётного while для оформления без перестановки действий."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Node

    from .build import Builder


def _expression(node: Node | None) -> Node | None:
    while node is not None and node.type in {
        "condition_clause",
        "parenthesized_expression",
        "expression_statement",
    }:
        children = [child for child in node.named_children if child.type != "comment"]
        if len(children) != 1:
            return None
        node = children[0]
    return node


def counter_step(variable: str, text: str) -> int | None:
    """Числовой шаг без изменения исходной записи выражения."""
    variable = re.escape(variable)
    if re.fullmatch(rf"(?:\+\+\s*{variable}|{variable}\s*\+\+)", text):
        return 1
    if re.fullmatch(rf"(?:--\s*{variable}|{variable}\s*--)", text):
        return -1
    match = re.fullmatch(
        rf"{variable}\s*(?:([+-])=\s*|=\s*{variable}\s*([+-])\s*)([+-]?\d+)",
        text,
    )
    if match is None:
        return None
    return int(match[3]) * (-1 if (match[1] or match[2]) == "-" else 1)


def _descendants(node: Node) -> Iterator[Node]:
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        pending.extend(current.named_children)


def _identifiers(builder: Builder, node: Node) -> set[str]:
    return {
        builder.t(child) for child in _descendants(node) if child.type == "identifier"
    }


def _declarator(node: Node) -> Node:
    return node.child_by_field_name("declarator") or node


def _writes(builder: Builder, node: Node) -> set[str] | None:
    """Неизвестный вызов или косвенная запись запрещают перенос знания об init."""
    writes: set[str] = set()
    for child in _descendants(node):
        if child.type in {
            "call_expression",
            "new_expression",
            "delete_expression",
            "lambda_expression",
            "goto_statement",
            "ERROR",
        }:
            return None
        if child.type == "pointer_expression" and builder.op_of(child) == "&":
            return None
        if child.type in {"assignment_expression", "update_expression"}:
            target = child.child_by_field_name("left") or child.child_by_field_name(
                "argument"
            )
            if target is None:
                return None
            if target.type == "identifier":
                writes.add(builder.t(target))
            elif target.type != "subscript_expression":
                return None
        if child.type == "binary_expression" and builder.op_of(child) == ">>":
            # Потоковый ввод может присваивать значение правому операнду.
            _, right = builder.sides(child)
            if right is not None:
                writes.update(_identifiers(builder, right))
        if child.type == "declaration":
            for declarator in child.children_by_field_name("declarator"):
                writes.update(_identifiers(builder, _declarator(declarator)))
        elif child.type == "init_declarator":
            writes.update(_identifiers(builder, _declarator(child)))
    return writes


def _parts(node: Node) -> list[Node]:
    if node.type == "declaration":
        return list(node.children_by_field_name("declarator"))
    expression = _expression(node)
    return [expression] if expression is not None else [node]


def _initializer(builder: Builder, node: Node, variable: str) -> Node | None:
    if node.type == "init_declarator":
        target = node.child_by_field_name("declarator")
        value = node.child_by_field_name("value")
    elif node.type == "assignment_expression" and builder.op_of(node) == "=":
        target, value = builder.sides(node)
    else:
        return None
    if target is None or target.type != "identifier" or builder.t(target) != variable:
        return None
    if value is None:
        return None
    allowed = {
        "identifier",
        "number_literal",
        "binary_expression",
        "unary_expression",
        "parenthesized_expression",
    }
    if any(child.type not in allowed for child in _descendants(value)):
        return None
    return value if variable not in _identifiers(builder, value) else None


def _scan_initialization(
    builder: Builder, nodes: list[Node], variable: str, changed: set[str]
) -> tuple[bool, Node | None]:
    """Ищет ближайшее прямое присваивание; неоднозначную запись не перескакивает."""
    for node in reversed(nodes):
        for part in reversed(_parts(node)):
            writes = _writes(builder, part)
            if writes is None:
                return True, None
            if node.type == "declaration":
                writes.update(_identifiers(builder, _declarator(part)))
            value = _initializer(builder, part, variable)
            if value is not None:
                if _identifiers(builder, value) & changed:
                    return True, None
                return True, value
            if variable in writes or (
                node.type == "declaration" and variable in _identifiers(builder, part)
            ):
                return True, None
            changed.update(writes)
    return False, None


def _unaliased_local(builder: Builder, loop: Node, variable: str) -> bool:
    """Останавливается на локальном объявлении, отвергая ранее созданные aliases."""
    current = loop
    while (parent := current.parent) is not None:
        if parent.type == "compound_statement":
            previous = [
                child
                for child in parent.named_children
                if child.end_byte <= current.start_byte
            ]
            for node in reversed(previous):
                for child in _descendants(node):
                    if (
                        child.type == "pointer_expression"
                        and builder.op_of(child) == "&"
                        and variable in _identifiers(builder, child)
                    ):
                        return False
                    if child.type == "init_declarator":
                        target = _declarator(child)
                        value = child.child_by_field_name("value")
                        if (
                            target.type == "reference_declarator"
                            and value is not None
                            and variable in _identifiers(builder, value)
                        ):
                            return False
                    if child.type == "lambda_expression":
                        return False
                    if child.type == "call_expression" and variable in _identifiers(
                        builder, child
                    ):
                        return False
                if node.type == "declaration":
                    for part in _parts(node):
                        target = _declarator(part)
                        if (
                            target.type == "identifier"
                            and builder.t(target) == variable
                        ):
                            return True
                        if variable in _identifiers(builder, target):
                            return False
        if parent.type in builder.spec.fn_nodes:
            return False
        current = parent
    return False


def _initialization_before(builder: Builder, loop: Node, variable: str) -> str | None:
    current = loop
    changed: set[str] = set()
    repeated: list[Node] = []
    while (parent := current.parent) is not None:
        if parent.type == "compound_statement":
            previous = [
                child
                for child in parent.named_children
                if child.end_byte <= current.start_byte and child.type != "comment"
            ]
            found, value = _scan_initialization(builder, previous, variable, changed)
            if found:
                if value is None:
                    return None
                initial = builder.t(value)
                dependencies = _identifiers(builder, value)
                if any(
                    not _unaliased_local(builder, loop, dependency)
                    for dependency in dependencies
                ):
                    return None
                for enclosing in repeated:
                    body = enclosing.child_by_field_name("body")
                    if body is None:
                        return None
                    # Continue может миновать reset; внутренние циклы не разворачиваем.
                    if any(
                        child.type in {"continue_statement", "goto_statement"}
                        for child in _descendants(body)
                    ):
                        return None
                    _, reset = _scan_initialization(
                        builder, list(body.named_children), variable, set()
                    )
                    if reset is None or builder.t(reset) != initial:
                        return None
                    effects = _writes(builder, enclosing)
                    if dependencies and (effects is None or dependencies & effects):
                        return None
                return initial
        elif parent.type in {"while_statement", "for_statement", "do_statement"}:
            repeated.append(parent)
            for field in ("initializer", "condition", "update"):
                expression = parent.child_by_field_name(field)
                if expression is not None:
                    effects = _writes(builder, expression)
                    if effects is None or variable in effects:
                        return None
                    changed.update(effects)
        elif parent.type in {"if_statement", "else_clause"}:
            condition = parent.child_by_field_name("condition")
            if condition is not None:
                effects = _writes(builder, condition)
                if effects is None or variable in effects:
                    return None
                changed.update(effects)
        else:
            return None
        current = parent
    return None


def counted_while_header(
    builder: Builder, loop: Node, condition: Node | None, body: Node | None
) -> str | None:
    """Описывает известные init/условие/шаг, сохраняя все действия на своих местах."""
    condition = _expression(condition)
    if condition is None or body is None or condition.type != "binary_expression":
        return None
    left, _ = builder.sides(condition)
    operator = builder.op_of(condition)
    if (
        left is None
        or left.type != "identifier"
        or operator not in {"<", "<=", ">", ">="}
    ):
        return None
    statements = (
        [node for node in body.named_children if node.type != "comment"]
        if body.type == "compound_statement"
        else [body]
    )
    if not statements or statements[-1].type != "expression_statement":
        return None
    update = _expression(statements[-1])
    if update is None:
        return None
    variable = builder.t(left)
    effects = _writes(builder, condition)
    if effects is None or variable in effects:
        return None
    text = builder.t(update)
    step = counter_step(variable, text)
    if step is None or not (
        (step > 0 and operator in {"<", "<="}) or (step < 0 and operator in {">", ">="})
    ):
        return None
    initial = _initialization_before(builder, loop, variable)
    if initial is None:
        return None
    if not _unaliased_local(builder, loop, variable):
        return None
    return f"{variable} = {initial}; {builder.cond_text(condition)}; {text}"
