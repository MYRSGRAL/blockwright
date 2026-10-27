"""Распознавание локальных протоколов ввода без скрытия произвольных эффектов."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from . import model as M


@dataclass
class InputGroup:
    end: int
    text: str
    buffer: str = ""
    stream: str = ""
    scratch: str = ""
    index: str = ""


@dataclass
class InputPlan:
    groups: dict[int, InputGroup] = field(default_factory=dict)
    hidden: set[int] = field(default_factory=set)


class _Recognizer:
    def __init__(self, builder: Any, nodes: list[Any]) -> None:
        self.b = builder
        self.nodes = nodes
        self.references: dict[str, set[int]] = {}
        self.declarations: dict[str, tuple[int, Any]] = {}
        self.buffers: dict[str, int] = {}
        self.index_escapes: dict[str, set[int]] = {}
        for position, node in enumerate(nodes):
            for child in self.walk(node):
                if child.type in {"identifier", "type_identifier"}:
                    self.references.setdefault(builder.raw(child), set()).add(position)
                if child.type == "pointer_expression" and builder.op_of(child) == "&":
                    argument = child.child_by_field_name("argument")
                    if argument is not None and argument.type == "identifier":
                        self.index_escapes.setdefault(builder.raw(argument), set()).add(
                            position
                        )
                if child.type == "init_declarator":
                    declarator = child.child_by_field_name("declarator")
                    value = child.child_by_field_name("value")
                    if (
                        declarator is not None
                        and declarator.type == "reference_declarator"
                        and value is not None
                        and value.type == "identifier"
                    ):
                        self.index_escapes.setdefault(builder.raw(value), set()).add(
                            position
                        )
                if child.type == "call_expression":
                    for argument in builder.call_args(child):
                        if argument.type == "identifier":
                            self.index_escapes.setdefault(
                                builder.raw(argument), set()
                            ).add(position)
                if child.type == "lambda_expression":
                    # Без анализа захватов сохраняем все используемые замыканием имена.
                    for reference in self.walk(child):
                        if reference.type == "identifier":
                            self.index_escapes.setdefault(
                                builder.raw(reference), set()
                            ).add(position)
            if node.type != "declaration":
                continue
            for declarator in node.children_by_field_name("declarator"):
                target = declarator
                while target is not None and target.type != "identifier":
                    target = target.child_by_field_name("declarator")
                if target is not None:
                    self.declarations[builder.raw(target)] = position, node
            target = node.child_by_field_name("declarator")
            if (
                target is not None
                and target.type == "identifier"
                and builder._name(node.child_by_field_name("type"), "string")
            ):
                self.buffers[builder.raw(target)] = position

    @staticmethod
    def walk(node: Any) -> Iterator[Any]:
        stack = [node]
        while stack:
            child = stack.pop()
            yield child
            stack.extend(child.named_children)

    def condition(self, node: Any) -> Any:
        condition = node.child_by_field_name("condition")
        if condition is None or len(self.b.named(condition)) != 1:
            return None
        return self.b._unwrap(condition)

    def atoms(self, node: Any) -> list[Any]:
        result = []
        stack = [node]
        while stack:
            current = self.b._unwrap(stack.pop())
            if self.b.op_of(current) == "||":
                left, right = self.b.sides(current)
                stack.extend((right, left))
            else:
                result.append(current)
        return result

    def read(self, node: Any, stream: str) -> Any:
        node = self.b._unwrap(node)
        if node is None or self.b.op_of(node) != ">>":
            return None
        if not stream:
            parts = self.b._stream_parts(node)
            return (
                parts[1][0]
                if parts and parts[0] == M.INPUT and len(parts[1]) == 1
                else None
            )
        left, right = self.b.sides(node)
        return right if left is not None and self.b.raw(left) == stream else None

    def failed_read(self, node: Any, stream: str) -> Any:
        node = self.b._unwrap(node)
        if node is None or node.type != "unary_expression" or self.b.op_of(node) != "!":
            return None
        return self.read(node.child_by_field_name("argument"), stream)

    def cin_failed(self, node: Any) -> bool:
        node = self.b._unwrap(node)
        if node.type == "call_expression":
            function = node.child_by_field_name("function")
            return (
                function is not None
                and function.type == "field_expression"
                and self.b._name(function.child_by_field_name("argument"), "cin")
                and self.b.raw(function.child_by_field_name("operator")) == "."
                and self.b.raw(function.child_by_field_name("field")) == "fail"
                and not self.b.call_args(node)
            )
        return (
            node.type == "unary_expression"
            and self.b.op_of(node) == "!"
            and self.b._name(
                self.b._unwrap(node.child_by_field_name("argument")), "cin"
            )
        )

    def scalar(self, node: Any) -> bool:
        return (
            node is not None
            and node.type == "identifier"
            and self.b.raw(node) in self.b._scalar_names
        )

    def value(self, node: Any) -> bool:
        return node is not None and (node.type == "number_literal" or self.scalar(node))

    def extra(self, node: Any, stream: str) -> str | None:
        target = self.read(node, stream)
        if not self.scalar(target):
            return None
        name = self.b.raw(target)
        declaration = self.declarations.get(name)
        if (
            declaration is None
            or self.b.raw(declaration[1].child_by_field_name("type")) != "char"
        ):
            return None
        return name

    def error_exit(self, node: Any, allowed: set[str]) -> bool:
        if (
            node.type != "if_statement"
            or node.child_by_field_name("alternative") is not None
        ):
            return False
        statements = self.b._statements(node.child_by_field_name("consequence"))
        if (
            len(statements) != 2
            or statements[0].type != "expression_statement"
            or statements[1].type != "return_statement"
        ):
            return False
        value = next(iter(statements[1].named_children), None)
        if value is None or value.type != "number_literal" or self.b.raw(value) != "1":
            return False
        stream = self.b._stream_parts(self.b._expr(statements[0]))
        if stream is None or stream[0] != M.OUTPUT:
            return False
        literal = False
        for part in stream[1]:
            if self.b._string_value(part) is not None:
                literal = True
            elif self.b._display_manipulator(part):
                continue
            elif not self.scalar(part) or self.b.raw(part) not in allowed:
                return False
        return literal

    def scalar_check(self, node: Any, stream: str) -> tuple[str, str] | None:
        condition = self.condition(node)
        if condition is None:
            return None
        atoms = self.atoms(condition)
        if atoms and self.cin_failed(atoms[0]):
            atoms = atoms[1:]
        if not atoms or (stream and len(atoms) < 2):
            return None
        target = self.failed_read(atoms[0], stream)
        if not self.scalar(target):
            return None
        name = self.b.raw(target)
        extra = ""
        rest = atoms[1:]
        if stream:
            extra = self.extra(atoms[1], stream)
            if not extra or extra == name:
                return None
            rest = atoms[2:]
        if not self.validation_atoms(rest, {name}):
            return None
        return (name, extra) if self.error_exit(node, {name}) else None

    def validation_atoms(self, atoms: list[Any], names: set[str]) -> bool:
        for atom in atoms:
            if self.cin_failed(atom):
                continue
            if any(self.b._finite(atom) == (name, True) for name in names):
                continue
            left, right = self.b.sides(atom)
            if self.b.op_of(atom) not in {"<", "<=", ">", ">=", "==", "!="}:
                return False
            if not (
                (self.b.raw(left) in names and self.value(right))
                or (self.b.raw(right) in names and self.value(left))
            ):
                return False
        return True

    def direct_validation(self, node: Any, names: set[str]) -> bool:
        if node.type != "if_statement":
            return False
        condition = self.condition(node)
        return (
            condition is not None
            and self.validation_atoms(self.atoms(condition), names)
            and self.error_exit(node, names)
        )

    def local_index(self, node: Any) -> str | None:
        if (
            node is None
            or node.type != "declaration"
            or len(node.children_by_field_name("declarator")) != 1
        ):
            return None
        typ = node.child_by_field_name("type")
        if (
            typ is None
            or self.b.raw(typ) != "int"
            or any(
                self.b.raw(child)
                in {"static", "volatile", "const", "extern", "thread_local"}
                for child in node.named_children
            )
        ):
            return None
        declarator = node.child_by_field_name("declarator")
        target = declarator.child_by_field_name("declarator")
        value = declarator.child_by_field_name("value")
        if (
            target is not None
            and target.type == "identifier"
            and value is not None
            and value.type == "number_literal"
            and self.b.raw(value) == "0"
        ):
            return self.b.raw(target)
        return None

    def direct_body(self, statements: list[Any], index: str, count: str) -> str | None:
        if not statements:
            return None
        node = statements[0]
        if node.type == "if_statement" and len(statements) == 1:
            condition = self.condition(node)
            target = self.failed_read(condition, "") if condition is not None else None
            array = self.array(target, index)
            return array if array and self.error_exit(node, {count}) else None
        if node.type != "expression_statement":
            return None
        array = self.array(self.read(self.b._expr(node), ""), index)
        if not array:
            return None
        if len(statements) == 1:
            return array
        if len(statements) == 2:
            check = statements[1]
            condition = self.condition(check) if check.type == "if_statement" else None
            if (
                condition is not None
                and all(self.cin_failed(atom) for atom in self.atoms(condition))
                and self.error_exit(check, {count})
            ):
                return array
        return None

    def direct_array(self, start: int) -> InputGroup | None:
        node = self.nodes[start]
        scoped = False
        if node.type == "for_statement":
            initializer = node.child_by_field_name("initializer")
            index = self.local_index(initializer)
            scoped = index is not None
            index = index or (
                self.zero_assignment(initializer) if initializer is not None else None
            )
            if not index:
                return None
            count = self.bound(node.child_by_field_name("condition"), index)
            update = node.child_by_field_name("update")
            statements = self.b._statements(node.child_by_field_name("body"))
            if not count or update is None or not self.increment(update, index):
                return None
            array = self.direct_body(statements, index, count)
            end = start + 1
        else:
            index = self.zero_assignment(node) or self.local_index(node)
            if not index or start + 1 >= len(self.nodes):
                return None
            loop = self.nodes[start + 1]
            if loop.type != "while_statement":
                return None
            condition = self.condition(loop)
            if condition is None:
                return None
            statements = self.b._statements(loop.child_by_field_name("body"))
            if not statements or not self.increment(statements[-1], index):
                return None
            if self.b.op_of(condition) == "&&":
                left, right = self.b.sides(condition)
                count = self.bound(left, index)
                array = self.array(self.read(right, ""), index)
                end = start + 3
                if (
                    not count
                    or not array
                    or len(statements) != 1
                    or end > len(self.nodes)
                ):
                    return None
                check = self.nodes[end - 1]
                tail = self.condition(check) if check.type == "if_statement" else None
                atoms = self.atoms(tail) if tail is not None else []
                mismatch = False
                for atom in atoms:
                    left, right = self.b.sides(atom)
                    if (
                        self.b.op_of(atom) == "!="
                        and self.b.raw(left) == index
                        and self.b.raw(right) == count
                    ):
                        mismatch = True
                    elif not self.cin_failed(atom):
                        return None
                if not mismatch or not self.error_exit(check, {count}):
                    return None
            else:
                count = self.bound(condition, index)
                array = (
                    self.direct_body(statements[:-1], index, count) if count else None
                )
                end = start + 2
        if not array or (not scoped and not self.index_disposable(index, end)):
            return None
        return InputGroup(end, f"Ввод {array}[{count}]", index=index)

    def direct(self, position: int) -> InputGroup | None:
        node = self.nodes[position]
        if node.type == "if_statement":
            scalar = self.scalar_check(node, "")
            if scalar is None:
                return None
            names = [scalar[0]]
        elif node.type == "expression_statement":
            stream = self.b._stream_parts(self.b._expr(node))
            if (
                stream is None
                or stream[0] != M.INPUT
                or not stream[1]
                or not all(self.scalar(target) for target in stream[1])
            ):
                return self.direct_array(position)
            names = [self.b.raw(target) for target in stream[1]]
        else:
            return self.direct_array(position)
        end = position + 1
        while end < len(self.nodes) and self.direct_validation(
            self.nodes[end], set(names)
        ):
            end += 1
        return InputGroup(end, "Ввод " + ", ".join(names))

    def zero_assignment(self, node: Any) -> str | None:
        node = self.b._expr(node)
        if (
            node is None
            or node.type != "assignment_expression"
            or self.b.op_of(node) != "="
        ):
            return None
        left, right = self.b.sides(node)
        if (
            self.scalar(left)
            and self.b.raw(left) in self.b._integer_names
            and right.type == "number_literal"
            and self.b.raw(right) == "0"
        ):
            return self.b.raw(left)
        return None

    def increment(self, node: Any, index: str) -> bool:
        node = self.b._expr(node)
        return (
            node is not None
            and node.type == "update_expression"
            and self.b.op_of(node) == "++"
            and self.b.raw(node.child_by_field_name("argument")) == index
        )

    def array(self, node: Any, index: str) -> str | None:
        if node is None or node.type != "subscript_expression":
            return None
        argument = node.child_by_field_name("argument")
        indices = node.child_by_field_name("indices")
        if (
            argument is None
            or argument.type != "identifier"
            or indices is None
            or len(indices.named_children) != 1
            or self.b.raw(indices.named_children[0]) != index
        ):
            return None
        name = self.b.raw(argument)
        declaration = self.declarations.get(name)
        if declaration is None:
            return None
        if any(
            self.b.raw(child) == "volatile" for child in declaration[1].named_children
        ):
            return None
        typ = declaration[1].child_by_field_name("type")
        return (
            name
            if typ is not None
            and typ.type in {"primitive_type", "sized_type_specifier"}
            else None
        )

    def bound(self, node: Any, index: str) -> str | None:
        node = self.b._unwrap(node)
        left, right = self.b.sides(node)
        if (
            self.b.op_of(node) == "<"
            and self.b.raw(left) == index
            and self.scalar(right)
            and self.b.raw(right) in self.b._integer_names
            and index in self.b._integer_names
        ):
            return self.b.raw(right)
        return None

    def tail(self, node: Any, stream: str, count: str, index: str = "") -> str | None:
        condition = self.condition(node)
        if condition is None:
            return None
        atoms = self.atoms(condition)
        if atoms and self.cin_failed(atoms[0]):
            atoms = atoms[1:]
        if index:
            if not atoms:
                return None
            left, right = self.b.sides(atoms[0])
            if (
                self.b.op_of(atoms[0]) != "!="
                or self.b.raw(left) != index
                or self.b.raw(right) != count
            ):
                return None
            atoms = atoms[1:]
        if len(atoms) != 1:
            return None
        extra = self.extra(atoms[0], stream)
        return extra if extra and self.error_exit(node, {count}) else None

    def index_disposable(self, index: str, end: int) -> bool:
        if index not in self.declarations:
            return False
        if any(position < end for position in self.index_escapes.get(index, set())):
            return False
        # Первое следующее использование должно заново задать индекс.
        for position in sorted(self.references.get(index, set())):
            if position < end:
                continue
            node = self.nodes[position]
            if (
                node.type == "for_statement"
                and self.local_index(node.child_by_field_name("initializer")) == index
            ):
                continue
            initializer = (
                node.child_by_field_name("initializer")
                if node.type == "for_statement"
                else node
            )
            return (
                self.zero_assignment(initializer) == index
                if initializer is not None
                else False
            )
        return True

    def array_check(self, start: int, stream: str) -> tuple[int, str, str, str] | None:
        node = self.nodes[start]
        index = ""
        count = None
        array = None
        end = start
        if node.type == "for_statement":
            initializer = node.child_by_field_name("initializer")
            index = (
                self.zero_assignment(initializer) if initializer is not None else None
            )
            if not index:
                return None
            count = self.bound(node.child_by_field_name("condition"), index)
            update = node.child_by_field_name("update")
            body = self.b._statements(node.child_by_field_name("body"))
            if (
                not count
                or update is None
                or not self.increment(update, index)
                or len(body) != 1
                or body[0].type != "if_statement"
            ):
                return None
            condition = self.condition(body[0])
            array = (
                self.array(self.failed_read(condition, stream), index)
                if condition is not None
                else None
            )
            if not array or not self.error_exit(body[0], {count}):
                return None
            end = start + 1
            checked_index = ""
        else:
            index = self.zero_assignment(node)
            if not index or start + 1 >= len(self.nodes):
                return None
            loop = self.nodes[start + 1]
            if loop.type != "while_statement":
                return None
            condition = self.condition(loop)
            if condition is None or self.b.op_of(condition) != "&&":
                return None
            left, right = self.b.sides(condition)
            count = self.bound(left, index)
            array = self.array(self.read(right, stream), index)
            body = self.b._statements(loop.child_by_field_name("body"))
            if (
                not count
                or not array
                or len(body) != 1
                or not self.increment(body[0], index)
            ):
                return None
            end = start + 2
            checked_index = index
        if end >= len(self.nodes):
            return None
        extra = self.tail(self.nodes[end], stream, count, checked_index)
        end += 1
        if not extra or not self.index_disposable(index, end):
            return None
        return end, f"{array}[{count}]", extra, index

    def candidate(self, position: int) -> InputGroup | None:
        if position + 2 >= len(self.nodes):
            return None
        call = self.b._expr(self.nodes[position])
        if (
            call is None
            or call.type != "call_expression"
            or not self.b._name(call.child_by_field_name("function"), "getline")
        ):
            return None
        args = self.b.call_args(call)
        if (
            len(args) != 2
            or not self.b._name(args[0], "cin")
            or args[1].type != "identifier"
        ):
            return None
        buffer = self.b.raw(args[1])
        if buffer not in self.buffers or self.buffers[buffer] >= position:
            return None
        declaration = self.nodes[position + 1]
        if (
            declaration.type != "declaration"
            or len(declaration.children_by_field_name("declarator")) != 1
            or not self.b._name(
                declaration.child_by_field_name("type"), "istringstream"
            )
        ):
            return None
        declarator = declaration.child_by_field_name("declarator")
        name = (
            declarator.child_by_field_name("declarator")
            if declarator is not None
            else None
        )
        params = (
            declarator.child_by_field_name("parameters")
            if declarator is not None
            else None
        )
        if (
            name is None
            or name.type != "identifier"
            or params is None
            or "".join(self.b.raw(params).split()) != f"({buffer})"
        ):
            return None
        stream = self.b.raw(name)
        check = self.nodes[position + 2]
        scalar = (
            self.scalar_check(check, stream) if check.type == "if_statement" else None
        )
        if scalar:
            target, scratch = scalar
            return InputGroup(position + 3, "Ввод " + target, buffer, stream, scratch)
        array = self.array_check(position + 2, stream)
        if array:
            end, target, scratch, index = array
            return InputGroup(end, "Ввод " + target, buffer, stream, scratch, index)
        return None


def collect_input_groups(builder: Any, block: Any, nodes: list[Any]) -> InputPlan:
    """Скрывать проверки разрешено только в main и явном учебном режиме hide."""
    plan = InputPlan()
    # Препроцессор может менять даже смысл ключевых слов и встроенных типов.
    if builder._macro_names & {
        "return",
        "if",
        "else",
        "for",
        "while",
        "break",
        "continue",
        "int",
        "char",
        "double",
        "float",
        "bool",
        "short",
        "long",
        "signed",
        "unsigned",
        "const",
        "volatile",
        "true",
        "false",
    }:
        return plan
    if (
        not builder.fn_is_main
        or getattr(builder.opts, "checks", "hide") != "hide"
        or block.parent is None
        or block.parent.type != "function_definition"
    ):
        return plan
    recognizer = _Recognizer(builder, nodes)
    root = block
    while root.parent is not None:
        root = root.parent
    for node in recognizer.walk(root):
        if node.type in {
            "class_specifier",
            "struct_specifier",
            "alias_declaration",
            "type_definition",
        }:
            name = node.child_by_field_name("name") or node.child_by_field_name(
                "declarator"
            )
            if builder.raw(name) in {"string", "istringstream"}:
                return plan
    candidates = {}
    for position in range(len(nodes)):
        group = recognizer.candidate(position) or recognizer.direct(position)
        if group is None:
            continue
        if any(
            builder.raw(child) in builder._macro_names
            for node in nodes[position : group.end]
            for child in recognizer.walk(node)
            if child.type in {"identifier", "type_identifier"}
        ):
            continue
        if group.stream and recognizer.references.get(group.stream, set()) - set(
            range(position, group.end)
        ):
            continue
        start = (
            position - 1
            if position and builder._prompt(nodes[position - 1])
            else position
        )
        candidates[start] = group
    # Не скрываем буфер или служебный символ, если их использует неподтверждённый код.
    while candidates:
        covered = {
            position
            for start, group in candidates.items()
            for position in range(start, group.end)
        }
        invalid = set()
        for start, group in candidates.items():
            for name in (group.buffer, group.scratch):
                if not name:
                    continue
                declaration = recognizer.declarations.get(name)
                allowed = covered | (
                    {declaration[0]} if declaration is not None else set()
                )
                if recognizer.references.get(name, set()) - allowed:
                    invalid.add(start)
        if not invalid:
            break
        candidates = {
            start: group for start, group in candidates.items() if start not in invalid
        }
    plan.groups = candidates
    plan.hidden = {
        recognizer.buffers[group.buffer]
        for group in candidates.values()
        if group.buffer
    }
    return plan
