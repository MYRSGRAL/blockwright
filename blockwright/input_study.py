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


@dataclass
class _RankRead:
    array: str
    bounds: list[str]
    indices: list[tuple[str, bool]]
    buffer: str = ""
    stream: str = ""
    scratch: str = ""


class _Recognizer:
    def __init__(self, builder: Any, nodes: list[Any]) -> None:
        self.b = builder
        self.nodes = nodes
        self.references: dict[str, set[int]] = {}
        self.declarations: dict[str, tuple[int, Any]] = {}
        self.buffers: dict[str, int] = {}
        self.streams: dict[str, int] = {}
        self.index_escapes: dict[str, set[int]] = {}
        self.text_groups: dict[int, tuple[str, int]] = {}
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
            declarators = node.children_by_field_name("declarator")
            if (
                declarators
                and all(part.type == "identifier" for part in declarators)
                and builder._name(node.child_by_field_name("type"), "string")
                and all(
                    builder.raw(part) in builder._string_names for part in declarators
                )
            ):
                for part in declarators:
                    self.buffers[builder.raw(part)] = position
            if (
                target is not None
                and target.type == "identifier"
                and len(node.children_by_field_name("declarator")) == 1
                and builder._name(node.child_by_field_name("type"), "istringstream")
            ):
                self.streams[builder.raw(target)] = position

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
        targets = self.read_targets(node, stream)
        return targets[0] if len(targets) == 1 else None

    def read_targets(self, node: Any, stream: str) -> list[Any]:
        node = self.b._unwrap(node)
        if node is None or self.b.op_of(node) != ">>":
            return []
        if not stream:
            parts = self.b._stream_parts(node)
            return parts[1] if parts and parts[0] == M.INPUT else []
        parts = self.b._flatten_stream(node, ">>")
        return parts[1:] if self.b.raw(parts[0]) == stream else []

    def failed_targets(self, node: Any, stream: str) -> list[Any]:
        node = self.b._unwrap(node)
        if node is None or node.type != "unary_expression" or self.b.op_of(node) != "!":
            return []
        return self.read_targets(node.child_by_field_name("argument"), stream)

    def failed_read(self, node: Any, stream: str) -> Any:
        targets = self.failed_targets(node, stream)
        return targets[0] if len(targets) == 1 else None

    def member(self, node: Any, owner: str, method: str) -> list[Any] | None:
        node = self.b._unwrap(self.b._expr(node))
        if node is None or node.type != "call_expression":
            return None
        function = node.child_by_field_name("function")
        if function is None or function.type != "field_expression":
            return None
        if (
            self.b.raw(function.child_by_field_name("argument")) != owner
            or self.b.raw(function.child_by_field_name("field")) != method
            or self.b.raw(function.child_by_field_name("operator")) != "."
        ):
            return None
        return self.b.call_args(node)

    def negated(self, node: Any) -> Any:
        node = self.b._unwrap(node)
        return (
            self.b._unwrap(node.child_by_field_name("argument"))
            if node is not None
            and node.type == "unary_expression"
            and self.b.op_of(node) == "!"
            else None
        )

    def boundary(self, node: Any, stream: str) -> bool:
        node = self.b._unwrap(node)
        if not stream or self.b.op_of(node) != "&&":
            return False
        left, right = self.b.sides(node)
        eof, space = self.negated(left), self.negated(right)
        if (
            eof is None
            or space is None
            or self.member(eof, stream, "eof") != []
            or space.type != "call_expression"
            or not self.b._name(space.child_by_field_name("function"), "isspace")
        ):
            return False
        args = self.b.call_args(space)
        return len(args) == 1 and self.member(args[0], stream, "peek") == []

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

    def error_exit(
        self, node: Any, allowed: set[str], *, numeric_exit: bool = False
    ) -> bool:
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
        if value is None or value.type != "number_literal":
            return False
        if numeric_exit:
            try:
                if int(self.b.raw(value), 0) == 0:
                    return False
            except ValueError:
                return False
        elif self.b.raw(value) != "1":
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

    def macro_free(self, node: Any) -> bool:
        return not any(
            child.type in {"identifier", "type_identifier", "field_identifier"}
            and self.b.raw(child) in self.b._macro_names
            for child in self.walk(node)
        )

    def string_name(self, name: str) -> bool:
        return name in self.b._string_names and name in self.declarations

    def getline_target(self, node: Any) -> str | None:
        node = self.b._unwrap(self.b._expr(node))
        if node.type != "call_expression" or not self.b._name(
            node.child_by_field_name("function"), "getline"
        ):
            return None
        args = self.b.call_args(node)
        if (
            len(args) not in {2, 3}
            or not self.b._name(args[0], "cin")
            or args[1].type != "identifier"
            or (len(args) == 3 and args[2].type != "char_literal")
        ):
            return None
        name = self.b.raw(args[1])
        return (
            name
            if self.string_name(name)
            and self.declarations[name][1].end_byte < node.start_byte
            else None
        )

    def constant_bound(self, node: Any) -> bool:
        node = self.b._unwrap(node)
        if node is None:
            return False
        if node.type == "number_literal":
            return True
        if node.type == "unary_expression" and self.b.op_of(node) in {"+", "-"}:
            value = self.b._unwrap(node.child_by_field_name("argument"))
            return value is not None and value.type == "number_literal"
        if not self.scalar(node):
            return False
        declaration = self.declarations.get(self.b.raw(node))
        if declaration is None or not any(
            self.b.raw(child) in {"const", "constexpr"}
            for child in declaration[1].named_children
        ):
            return False
        for declarator in declaration[1].children_by_field_name("declarator"):
            if self.b.raw(declarator.child_by_field_name("declarator")) == self.b.raw(
                node
            ):
                value = declarator.child_by_field_name("value")
                return value is not None and value.type == "number_literal"
        return False

    def string_measure(self, node: Any, methods: set[str]) -> str | None:
        node = self.b._unwrap(node)
        if node is None or node.type != "call_expression":
            return None
        function = node.child_by_field_name("function")
        if function is None or function.type != "field_expression":
            return None
        owner = function.child_by_field_name("argument")
        method = self.b.raw(function.child_by_field_name("field"))
        name = self.b.raw(owner)
        return (
            name
            if owner is not None
            and owner.type == "identifier"
            and self.string_name(name)
            and method in methods
            and self.member(node, name, method) == []
            else None
        )

    def string_validation(self, node: Any) -> str | None:
        names = set()
        for atom in self.atoms(node):
            name = self.string_measure(atom, {"empty"})
            if name:
                names.add(name)
                continue
            left, right = self.b.sides(atom)
            if self.b.op_of(atom) not in {"<", "<=", ">", ">=", "==", "!="}:
                return None
            name = self.string_measure(left, {"size", "length"})
            if name and self.constant_bound(right):
                names.add(name)
                continue
            name = self.string_measure(right, {"size", "length"})
            if not name or not self.constant_bound(left):
                return None
            names.add(name)
        return next(iter(names)) if len(names) == 1 else None

    def text_candidate(self, position: int) -> InputGroup | None:
        node = self.nodes[position]
        if node.type == "if_statement":
            condition = self.condition(node)
            atoms = self.atoms(condition) if condition is not None else []
            read = self.negated(atoms[0]) if atoms else None
            name = self.getline_target(read) if read is not None else None
            if (
                not name
                or any(self.string_validation(atom) != name for atom in atoms[1:])
                or not self.error_exit(node, self.b._scalar_names, numeric_exit=True)
            ):
                return None
        elif node.type == "expression_statement":
            name = self.getline_target(node)
            if not name:
                return None
        else:
            return None
        group = InputGroup(position + 1, "Ввод " + name)
        self.text_groups[id(group)] = name, position
        return group

    def stream_source(self, node: Any) -> tuple[str, str] | None:
        if (
            node.type != "declaration"
            or len(node.children_by_field_name("declarator")) != 1
            or not self.b._name(node.child_by_field_name("type"), "istringstream")
            or not self.macro_free(node)
        ):
            return None
        declarator = node.child_by_field_name("declarator")
        name = declarator.child_by_field_name("declarator")
        params = declarator.child_by_field_name("parameters")
        if (
            declarator.type != "function_declarator"
            or name is None
            or name.type != "identifier"
            or params is None
        ):
            return None
        for text in self.b._string_names:
            if (
                self.string_name(text)
                and "".join(self.b.raw(params).split()) == f"({text})"
            ):
                return self.b.raw(name), text
        return None

    def text_unchanged(
        self, name: str, read: int, end: int, reads: dict[str, list[int]]
    ) -> bool:
        allowed_reads = set(reads.get(name, []))
        if any(
            position < end and position not in allowed_reads
            for position in self.index_escapes.get(name, set())
        ):
            return False
        for position in self.references.get(name, set()):
            if not read < position < end:
                continue
            node = self.nodes[position]
            source = self.stream_source(node)
            if source is not None and source[1] == name:
                continue
            if not self.macro_free(node):
                return False
            for child in self.walk(node):
                if child.type != "identifier" or self.b.raw(child) != name:
                    continue
                field = child.parent
                call = field.parent if field is not None else None
                if (
                    field is None
                    or field.type != "field_expression"
                    or field.child_by_field_name("argument") != child
                    or self.string_measure(call, {"empty", "size", "length"}) != name
                ):
                    return False
        return True

    def initialized_zero(self, name: str) -> int | None:
        declaration = self.declarations.get(name)
        if (
            declaration is None
            or name not in self.b._integer_names
            or any(
                self.b.raw(child) in {"static", "extern", "thread_local", "volatile"}
                for child in declaration[1].named_children
            )
        ):
            return None
        for declarator in declaration[1].children_by_field_name("declarator"):
            if self.b.raw(declarator.child_by_field_name("declarator")) == name:
                value = declarator.child_by_field_name("value")
                return (
                    declaration[0]
                    if value is not None
                    and value.type == "number_literal"
                    and self.b.raw(value) == "0"
                    else None
                )
        return None

    def writes(self, node: Any, name: str) -> Iterator[Any]:
        for child in self.walk(node):
            target = None
            if child.type == "assignment_expression":
                target = child.child_by_field_name("left")
            elif child.type == "update_expression":
                target = child.child_by_field_name("argument")
            elif child.type == "init_declarator":
                target = child.child_by_field_name("declarator")
            if (
                target is not None
                and target.type == "identifier"
                and self.b.raw(target) == name
            ):
                yield child

    def word_count_guard(
        self, condition: Any, end: int, reads: dict[str, list[int]]
    ) -> bool:
        if self.b.op_of(condition) != "==":
            return False
        left, right = self.b.sides(condition)
        if (
            left is not None
            and left.type == "number_literal"
            and self.b.raw(left) == "0"
        ):
            left, right = right, left
        if (
            not self.scalar(left)
            or right is None
            or right.type != "number_literal"
            or self.b.raw(right) != "0"
        ):
            return False
        counter = self.b.raw(left)
        initialized = self.initialized_zero(counter)
        if initialized is None or any(
            position < end for position in self.index_escapes.get(counter, set())
        ):
            return False
        for position in range(initialized + 1, end):
            loop = self.nodes[position]
            if loop.type != "while_statement" or not self.macro_free(loop):
                continue
            condition = self.condition(loop)
            if condition is None or self.b.op_of(condition) != ">>":
                continue
            stream, word = self.b.sides(condition)
            if (
                stream is None
                or stream.type != "identifier"
                or word is None
                or word.type != "identifier"
                or not self.string_name(self.b.raw(word))
            ):
                continue
            binding = self.declarations.get(self.b.raw(stream))
            source = self.stream_source(binding[1]) if binding is not None else None
            if (
                source is None
                or binding[0] >= position
                or self.b.raw(word) == source[1]
                or self.declarations[self.b.raw(word)][0] >= position
            ):
                continue
            origins = [read for read in reads.get(source[1], []) if read < binding[0]]
            if not origins or not self.text_unchanged(
                source[1], max(origins), end, reads
            ):
                continue
            if any(
                binding[0] < use < end and use != position
                for use in self.references.get(source[0], set())
            ):
                continue
            body = self.b._statements(loop.child_by_field_name("body"))
            if (
                not body
                or not self.increment(body[0], counter)
                or self.references_name(loop.child_by_field_name("body"), source[0])
            ):
                continue
            increment = self.b._expr(body[0])
            mutations = [
                write
                for node in self.nodes[initialized + 1 : end]
                for write in self.writes(node, counter)
            ]
            if len(mutations) == 1 and mutations[0] == increment:
                return True
        return False

    def hidden_text_guards(self, groups: dict[int, InputGroup]) -> set[int]:
        reads: dict[str, list[int]] = {}
        for group in groups.values():
            source = self.text_groups.get(id(group))
            if source is not None:
                name, position = source
                reads.setdefault(name, []).append(position)
        hidden = set()
        if not reads:
            return hidden
        for position, node in enumerate(self.nodes):
            if (
                node.type != "if_statement"
                or not self.macro_free(node)
                or not self.error_exit(node, self.b._scalar_names, numeric_exit=True)
            ):
                continue
            condition = self.condition(node)
            if condition is None:
                continue
            name = self.string_validation(condition)
            if name:
                origins = [read for read in reads.get(name, []) if read < position]
                if origins and self.text_unchanged(name, max(origins), position, reads):
                    hidden.add(position)
            elif (
                self.cin_failed(condition)
                and any(position - 1 in positions for positions in reads.values())
                or self.word_count_guard(condition, position, reads)
            ):
                hidden.add(position)
        return hidden

    def scalar_check(self, node: Any, stream: str) -> tuple[list[str], str] | None:
        condition = self.condition(node)
        if condition is None:
            return None
        atoms = self.atoms(condition)
        if atoms and self.cin_failed(atoms[0]):
            atoms = atoms[1:]
        names: list[str] = []
        scratch = ""
        reading = True
        for atom in atoms:
            targets = self.failed_targets(atom, stream) if reading else []
            if targets:
                if scratch or not all(self.scalar(target) for target in targets):
                    return None
                for target in targets:
                    name = self.b.raw(target)
                    if name in names:
                        return None
                    names.append(name)
            elif reading and names and self.boundary(atom, stream):
                continue
            elif reading and stream and names and (extra := self.extra(atom, stream)):
                if extra in names:
                    return None
                scratch, reading = extra, False
            else:
                reading = False
                if not names or not self.validation_atoms([atom], set(names)):
                    return None
        if (
            not names
            or (stream and not scratch)
            or not self.error_exit(node, set(names))
        ):
            return None
        return names, scratch

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
            names = scalar[0]
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
        return self.array_coordinates(node, [index])

    def array_coordinates(self, node: Any, coordinates: list[str]) -> str | None:
        indices = []
        while node is not None and node.type == "subscript_expression":
            arguments = node.child_by_field_name("indices")
            if arguments is None or len(arguments.named_children) != 1:
                return None
            index = arguments.named_children[0]
            if index.type != "identifier":
                return None
            indices.append(self.b.raw(index))
            node = node.child_by_field_name("argument")
        if (
            node is None
            or node.type != "identifier"
            or list(reversed(indices)) != coordinates
        ):
            return None
        name = self.b.raw(node)
        if getattr(self.b, "_array_ranks", {}).get(name) != len(coordinates):
            return None
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
        live = True
        for node in self.nodes[end:]:
            safe, live = self.index_flow(node, index, live)
            if not safe:
                return False
        return True

    def index_flow(self, node: Any, index: str, live: bool) -> tuple[bool, bool]:
        if not live:
            return True, False
        expression = self.b._expr(node)
        if (
            expression.type == "assignment_expression"
            and self.b.op_of(expression) == "="
        ):
            left, right = self.b.sides(expression)
            if (
                self.b.raw(left) == index
                and right is not None
                and right.type == "number_literal"
            ):
                return True, False
        if node.type == "compound_statement":
            for statement in self.b._statements(node):
                safe, live = self.index_flow(statement, index, live)
                if not safe:
                    return False, live
            return True, live
        if node.type == "for_statement":
            initializer = node.child_by_field_name("initializer")
            if self.local_index(initializer) == index:
                return True, live
            if initializer is not None:
                safe, live = self.index_flow(initializer, index, live)
                if not safe:
                    return False, live
            for field in ("condition", "update"):
                part = node.child_by_field_name(field)
                if part is not None and live and self.references_name(part, index):
                    return False, live
            safe, _ = self.index_flow(node.child_by_field_name("body"), index, live)
            return safe, live
        return not self.references_name(node, index), live

    def references_name(self, node: Any, name: str) -> bool:
        return any(
            child.type == "identifier" and self.b.raw(child) == name
            for child in self.walk(node)
        )

    def setup(
        self, nodes: list[Any], start: int, *, row: bool = False
    ) -> tuple[int, str, str] | None:
        position = start
        cleared_buffer = ""
        if position >= len(nodes):
            return None
        for buffer in self.buffers:
            if self.member(nodes[position], buffer, "clear") == []:
                cleared_buffer = buffer
                position += 1
                break
        if position >= len(nodes):
            return None
        call = self.b._expr(nodes[position])
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
        if cleared_buffer and cleared_buffer != buffer:
            return None
        if buffer not in self.buffers or position + 1 >= len(nodes):
            return None
        position += 1
        declaration = nodes[position]
        if (
            declaration.type == "declaration"
            and self.b._name(declaration.child_by_field_name("type"), "istringstream")
            and len(declaration.children_by_field_name("declarator")) == 1
        ):
            declarator = declaration.child_by_field_name("declarator")
            name = declarator.child_by_field_name("declarator")
            params = declarator.child_by_field_name("parameters")
            if (
                declarator.type == "function_declarator"
                and name is not None
                and name.type == "identifier"
                and params is not None
                and "".join(self.b.raw(params).split()) == f"({buffer})"
            ):
                return position + 1, buffer, self.b.raw(name)
            return None
        for stream, declaration_position in self.streams.items():
            cursor = position
            reset = self.member(nodes[cursor], stream, "clear") == []
            if reset:
                cursor += 1
            if cursor >= len(nodes):
                continue
            arguments = self.member(nodes[cursor], stream, "str")
            if (
                arguments is None
                or len(arguments) != 1
                or arguments[0].type != "identifier"
                or self.b.raw(arguments[0]) != buffer
            ):
                continue
            if not reset and (
                row
                or any(
                    declaration_position < use < start
                    for use in self.references.get(stream, set())
                )
            ):
                continue
            return cursor + 1, buffer, stream
        return None

    def rank_element(
        self, statements: list[Any], stream: str, indices: list[str], bounds: list[str]
    ) -> str | None:
        if not statements:
            return None
        check = statements[0]
        if check.type == "if_statement" and len(statements) == 1:
            condition = self.condition(check)
            if condition is None:
                return None
            atoms = self.atoms(condition)
            target = self.failed_read(atoms[0], stream)
            array = self.array_coordinates(target, indices)
            if (
                array
                and all(self.boundary(atom, stream) for atom in atoms[1:])
                and self.error_exit(check, set(bounds))
            ):
                return array
        if len(statements) == 1 and check.type == "expression_statement":
            return self.array_coordinates(
                self.read(self.b._expr(check), stream), indices
            )
        return None

    def rank_loop(
        self,
        node: Any,
        parents: list[tuple[str, bool]],
        dimensions: list[str],
        stream: str = "",
    ) -> _RankRead | None:
        if node.type != "for_statement":
            return None
        initializer = node.child_by_field_name("initializer")
        local = self.local_index(initializer)
        index = local or (
            self.zero_assignment(initializer) if initializer is not None else None
        )
        if not index or index in {name for name, _ in parents}:
            return None
        count = self.bound(node.child_by_field_name("condition"), index)
        update = node.child_by_field_name("update")
        if not count or update is None or not self.increment(update, index):
            return None
        indices = parents + [(index, local is not None)]
        bounds = dimensions + [count]
        body = self.b._statements(node.child_by_field_name("body"))
        if len(body) == 1 and body[0].type == "for_statement":
            return self.rank_loop(body[0], indices, bounds, stream)
        array = self.rank_element(body, stream, [name for name, _ in indices], bounds)
        if array:
            return _RankRead(array, bounds, indices, stream=stream)
        setup = self.setup(body, 0, row=True)
        if setup is None:
            return None
        position, buffer, row_stream = setup
        if len(body) != position + 2:
            return None
        inner = self.rank_loop(body[position], indices, bounds, row_stream)
        if inner is None or inner.buffer:
            return None
        extra = self.tail(body[position + 1], row_stream, inner.bounds[-1])
        if not extra:
            return None
        inner.buffer, inner.stream, inner.scratch = buffer, row_stream, extra
        return inner

    def ranked_candidate(self, position: int) -> InputGroup | None:
        rank = self.rank_loop(self.nodes[position], [], [])
        if rank is None or len(rank.bounds) < 2:
            return None
        end = position + 1
        if any(
            not local and not self.index_disposable(index, end)
            for index, local in rank.indices
        ):
            return None
        target = rank.array + "".join(f"[{bound}]" for bound in rank.bounds)
        return InputGroup(end, "Ввод " + target, rank.buffer, rank.stream, rank.scratch)

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
        setup = self.setup(self.nodes, position)
        if setup is not None:
            end, buffer, stream = setup
            if end < len(self.nodes) and self.nodes[end].type == "if_statement":
                scalar = self.scalar_check(self.nodes[end], stream)
                if scalar:
                    targets, scratch = scalar
                    return InputGroup(
                        end + 1, "Ввод " + ", ".join(targets), buffer, stream, scratch
                    )
            if end + 1 < len(self.nodes):
                rank = self.rank_loop(self.nodes[end], [], [], stream)
                if rank is not None and not rank.buffer:
                    scratch = self.tail(self.nodes[end + 1], stream, rank.bounds[-1])
                    finish = end + 2
                    if scratch and all(
                        local or self.index_disposable(index, finish)
                        for index, local in rank.indices
                    ):
                        target = rank.array + "".join(
                            f"[{bound}]" for bound in rank.bounds
                        )
                        return InputGroup(
                            finish, "Ввод " + target, buffer, stream, scratch
                        )
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
            targets, scratch = scalar
            return InputGroup(
                position + 3, "Ввод " + ", ".join(targets), buffer, stream, scratch
            )
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
        group = (
            recognizer.candidate(position)
            or recognizer.ranked_candidate(position)
            or recognizer.direct(position)
            or recognizer.text_candidate(position)
        )
        if group is None:
            continue
        if any(
            builder.raw(child) in builder._macro_names
            for node in nodes[position : group.end]
            for child in recognizer.walk(node)
            if child.type in {"identifier", "type_identifier", "field_identifier"}
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
            for name in (group.buffer, group.scratch, group.stream):
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
    plan.hidden.update(
        recognizer.streams[group.stream]
        for group in candidates.values()
        if group.stream in recognizer.streams
    )
    plan.hidden.update(recognizer.hidden_text_guards(candidates))
    return plan
