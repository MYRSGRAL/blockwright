"""Консервативные сокращения учебных схем по синтаксическому дереву C++."""

from typing import Any

from . import model as M
from .build import Builder
from .output_study import array_caption, array_output
from .text import normalize

_MAX_INITIALIZATIONS = 3
_MAX_INITIALIZATION_TEXT = 80
_CONSOLE_CODEPAGES = {
    "CP_ACP",
    "CP_OEMCP",
    "CP_MACCP",
    "CP_THREAD_ACP",
    "CP_SYMBOL",
    "CP_UTF7",
    "CP_UTF8",
}
_LOCALE_CATEGORIES = {
    "LC_ALL",
    "LC_COLLATE",
    "LC_CTYPE",
    "LC_MONETARY",
    "LC_NUMERIC",
    "LC_TIME",
}


class StudyBuilder(Builder):
    """Неизвестные конструкции передаются подробному builder без потери текста."""

    def build_body(self, body: Any, is_main: bool = False) -> M.Seq:
        self._shadowed = set()
        self._macro_names = set()
        nodes = list(body) if isinstance(body, list) else [body]
        if not isinstance(body, list):
            parent = body.parent
            while parent is not None and parent.type != "function_definition":
                parent = parent.parent
            if parent is not None:
                nodes.append(parent.child_by_field_name("declarator"))
            root = body
            while root.parent is not None:
                root = root.parent
            macro_nodes = [root]
            while macro_nodes:
                node = macro_nodes.pop()
                if node.type in {"preproc_def", "preproc_function_def"}:
                    name = self.raw(node.child_by_field_name("name"))
                    self._macro_names.add(name)
                    self._shadowed.add(name)
                if node.type in {
                    "class_specifier",
                    "struct_specifier",
                    "alias_declaration",
                    "type_definition",
                }:
                    name = node.child_by_field_name("name") or node.child_by_field_name(
                        "declarator"
                    )
                    if name is not None:
                        self._shadowed.add(self.raw(name))
                macro_nodes.extend(node.named_children)
            global_nodes = [root]
            while global_nodes:
                node = global_nodes.pop()
                if node.type == "function_definition":
                    continue
                if node.type == "declaration":
                    nodes.append(node)
                global_nodes.extend(node.named_children)
        stack = [node for node in nodes if node is not None]
        all_nodes = []
        while stack:
            node = stack.pop()
            all_nodes.append(node)
            if node.has_error:
                raise ValueError("Ошибка синтаксиса C++: учебная схема не построена")
            if node.type in {
                "declaration",
                "parameter_declaration",
                "optional_parameter_declaration",
            }:
                for declarator in node.children_by_field_name("declarator"):
                    while declarator is not None and declarator.type != "identifier":
                        nested = declarator.child_by_field_name("declarator")
                        if (
                            nested is None
                            and declarator.type
                            in {"reference_declarator", "parenthesized_declarator"}
                            and declarator.named_child_count == 1
                        ):
                            nested = declarator.named_children[0]
                        declarator = nested
                    if declarator is not None:
                        self._shadowed.add(self.raw(declarator))
            stack.extend(node.named_children)
        self._identifier_positions = {}
        for node in all_nodes:
            if node.type == "identifier":
                self._identifier_positions.setdefault(self.raw(node), set()).add(
                    node.start_byte
                )
        self._identifier_positions = {
            name: sorted(positions)
            for name, positions in self._identifier_positions.items()
        }
        categories: dict[str, set[str]] = {}
        for node in all_nodes:
            if node.type not in {
                "declaration",
                "parameter_declaration",
                "optional_parameter_declaration",
            }:
                continue
            typ = node.child_by_field_name("type")
            primitive = (
                typ is not None
                and typ.type in {"primitive_type", "sized_type_specifier"}
                and self.raw(typ) not in self._macro_names
                and not any(self.raw(c) == "volatile" for c in node.named_children)
            )
            for declarator in node.children_by_field_name("declarator"):
                target = (
                    declarator.child_by_field_name("declarator")
                    if declarator.type == "init_declarator"
                    else declarator
                )
                leaf = target
                while leaf is not None and leaf.type != "identifier":
                    nested = leaf.child_by_field_name("declarator")
                    if (
                        nested is None
                        and leaf.type
                        in {"reference_declarator", "parenthesized_declarator"}
                        and leaf.named_child_count == 1
                    ):
                        nested = leaf.named_children[0]
                    leaf = nested
                if leaf is None:
                    continue
                category = "other"
                if primitive and target.type == "identifier":
                    category = (
                        "scalar"
                        if any(
                            word in self.raw(typ)
                            for word in ("float", "double", "void")
                        )
                        else "integer"
                    )
                elif (
                    primitive
                    and target.type == "array_declarator"
                    and target.child_by_field_name("declarator").type == "identifier"
                ):
                    category = "array"
                categories.setdefault(self.raw(leaf), set()).add(category)
        # Без разрешения областей видимости противоречивые объявления не сокращаем.
        self._scalar_names = {
            name for name, kinds in categories.items() if kinds <= {"integer", "scalar"}
        } - self._macro_names
        self._integer_names = {
            name for name, kinds in categories.items() if kinds == {"integer"}
        } - self._macro_names
        self._array_names = {
            name for name, kinds in categories.items() if kinds == {"array"}
        } - self._macro_names
        self._sum_display = False
        for node in all_nodes:
            if node.type != "expression_statement":
                continue
            stream = self._stream_parts(self._expr(node))
            if stream and stream[0] == M.OUTPUT:
                literals = [self._string_value(p) for p in stream[1]]
                if "sum" in [self.raw(p) for p in stream[1]] and any(
                    value and value.strip().startswith("Сумма") for value in literals
                ):
                    self._sum_display = True
        self._cin_uses = [
            node
            for node in all_nodes
            if node.type in {"identifier", "qualified_identifier"}
            and self._name(node, "cin")
        ]
        return super().build_body(body, is_main)

    def t(self, node: Any) -> str:
        """C-cast int отображается как целая часть с усечением к нулю."""
        if node is None:
            return ""
        replacements = []
        stack = [node]
        while stack:
            child = stack.pop()
            typ = child.child_by_field_name("type")
            value = child.child_by_field_name("value")
            if (
                child.type == "cast_expression"
                and self.raw(typ) == "int"
                and value is not None
            ):
                replacements.append(
                    (
                        child.start_byte,
                        child.end_byte,
                        "целая часть(" + self.t(self._unwrap(value)) + ")",
                    )
                )
            else:
                stack.extend(child.named_children)
        if not replacements:
            return super().t(node)
        parts = []
        cursor = node.start_byte
        for start, end, text in sorted(replacements):
            parts.append(self.src[cursor:start].decode("utf-8", "replace"))
            parts.append(text)
            cursor = end
        parts.append(self.src[cursor : node.end_byte].decode("utf-8", "replace"))
        text = normalize("".join(parts))
        return text if self.opts.keep_std else self.strip_all(text)

    def make_return(self, txt: str) -> M.Return:
        return M.Return(txt, self.fn_is_main)

    def _unwrap(self, node: Any) -> Any:
        while node is not None and node.type in {
            "parenthesized_expression",
            "condition_clause",
        }:
            node = node.child_by_field_name("value") or next(
                iter(node.named_children), None
            )
        return node

    def _expr(self, node: Any) -> Any:
        if node.type == "expression_statement":
            return next(iter(node.named_children), None)
        return node

    def _name(self, node: Any, name: str) -> bool:
        if node is None or name in self._macro_names:
            return False
        raw = self.raw(node)
        if raw in self.known:
            return False
        return raw == "std::" + name or (raw == name and name not in self._shadowed)

    def _finite(self, node: Any) -> tuple[str, bool] | None:
        node = self._unwrap(node)
        negative = (
            node is not None
            and node.type == "unary_expression"
            and self.op_of(node) == "!"
        )
        if negative:
            node = self._unwrap(node.child_by_field_name("argument"))
        if (
            node is None
            or node.type != "call_expression"
            or not self._name(node.child_by_field_name("function"), "isfinite")
        ):
            return None
        args = self.call_args(node)
        if len(args) == 1 and args[0].type == "identifier":
            return self.t(args[0]), negative
        return None

    def cond_text(self, node: Any, missing: str = "condition") -> str:
        finite = self._finite(node)
        if finite:
            name, negative = finite
            return name + (" не конечна?" if negative else " конечна?")
        return super().cond_text(node, missing)

    def _declaration(self, node: Any) -> list[object] | None:
        typ = node.child_by_field_name("type")
        if self.raw(typ) in self._macro_names:
            return None
        if typ is None or not (
            typ.type in {"primitive_type", "sized_type_specifier"}
            or self._name(typ, "string")
        ):
            return None
        # volatile может выполнять наблюдаемые чтения/записи даже без вызовов.
        if any(
            self.raw(c) in {"volatile", "static", "thread_local", "extern"}
            for c in node.named_children
        ):
            return None
        declarations = node.children_by_field_name("declarator")
        if not declarations:
            return None
        texts = []
        for decl in declarations:
            if decl.type == "identifier":
                continue
            if decl.type == "pointer_declarator":
                target = decl
                while target is not None and target.type == "pointer_declarator":
                    target = target.child_by_field_name("declarator")
                if target is not None and target.type == "identifier":
                    continue
                return None
            if decl.type == "array_declarator":
                size = decl.child_by_field_name("size")
                if size is None or size.type not in {"number_literal", "identifier"}:
                    return None
                continue
            if decl.type != "init_declarator":
                return None
            target = decl.child_by_field_name("declarator")
            value = decl.child_by_field_name("value")
            if target is None or target.type != "identifier" or value is None:
                return None
            texts.append(f"{self.t(target)} = {self.t(value)}")
        return [M.Simple(M.PROCESS, text) for text in texts]

    def k_simple(self, n: Any, r: dict) -> list[object]:
        declarations = self._declaration(n)
        return declarations if declarations is not None else super().k_simple(n, r)

    def _literal_initializations(self, node: Any) -> list[str] | None:
        if node.type != "declaration":
            return None
        statements = self._declaration(node)
        if not statements or len(statements) > _MAX_INITIALIZATIONS:
            return None
        declarations = node.children_by_field_name("declarator")
        if len(declarations) != len(statements):
            return None
        for declaration in declarations:
            value = self._unwrap(declaration.child_by_field_name("value"))
            if (
                value is not None
                and value.type == "unary_expression"
                and self.op_of(value) in {"+", "-"}
            ):
                value = self._unwrap(value.child_by_field_name("argument"))
                if value is None or value.type != "number_literal":
                    return None
            elif value is None or value.type not in {
                "number_literal",
                "char_literal",
                "true",
                "false",
            }:
                return None
        texts = [statement.text for statement in statements]
        return texts if len("; ".join(texts)) <= _MAX_INITIALIZATION_TEXT else None

    def _simple_from_node(self, node: Any) -> M.Simple | None:
        if node is None:
            return None
        if node.type == "declaration":
            declarations = self._declaration(node)
            if declarations:
                return M.Simple(
                    M.PROCESS, "; ".join(item.text for item in declarations)
                )
        if node.type == "update_expression":
            arg = node.child_by_field_name("argument")
            op = self.op_of(node)
            if arg is not None and arg.type == "identifier" and op in {"++", "--"}:
                name = self.t(arg)
                return M.Simple(
                    M.PROCESS, f"{name} = {name} {'+' if op == '++' else '-'} 1"
                )
        return super()._simple_from_node(node)

    def _stream_parts(self, node: Any) -> tuple[str, list[Any]] | None:
        node = self._unwrap(node)
        op = self.op_of(node)
        if op not in {"<<", ">>"}:
            return None
        parts = self._flatten_stream(node, op)
        st = self.spec.streams
        names = st["output"] if op == "<<" else st["input"]
        if not any(self._name(parts[0], name) for name in names):
            return None
        return (M.OUTPUT if op == "<<" else M.INPUT), parts[1:]

    def _display_manipulator(self, node: Any) -> bool:
        if node.type in {"identifier", "qualified_identifier"}:
            return self._is_manipulator(node)
        if node.type == "call_expression" and self._is_manipulator(node):
            return all(
                a.type in {"number_literal", "char_literal", "string_literal"}
                for a in self.call_args(node)
            )
        return False

    def _is_manipulator(self, node: Any) -> bool:
        if not super()._is_manipulator(node):
            return False
        name_node = (
            node.child_by_field_name("function")
            if node.type == "call_expression"
            else node
        )
        name = self.raw(name_node).split("::")[-1]
        return self._name(name_node, name)

    def _compact_output(self, parts: list[Any]) -> bool:
        literals = [
            value.strip()
            for part in parts
            if (value := self._string_value(part)) is not None and value.strip()
        ]
        if not literals:
            return True
        return (
            len(literals) == 1
            and literals[0].endswith((":", "="))
            and not literals[0].startswith("Ошибка")
        )

    def try_io(self, node: Any) -> M.Simple | None:
        stream = self._stream_parts(node)
        if stream:
            kind, parts = stream
            if kind == M.INPUT:
                return M.Simple(kind, "Ввод " + ", ".join(self.t(p) for p in parts))
            visible = [p for p in parts if not self._display_manipulator(p)]
            # Нестандартные манипуляторы и выражения остаются видимыми.
            if any(
                self._is_manipulator(p) and not self._display_manipulator(p)
                for p in parts
            ):
                return M.Simple(kind, self.t(node))
            values = [p for p in visible if self._string_value(p) is None]
            literals = [
                self._string_value(p)
                for p in visible
                if self._string_value(p) is not None
            ]
            if values and self._compact_output(visible):
                return M.Simple(kind, "Вывод " + ", ".join(self.t(p) for p in values))
            if values:
                return M.Simple(kind, self._weave(self._segments(visible), "Вывод "))
            return M.Simple(kind, "Вывод " + "".join(literals).strip())
        result = super().try_io(node)
        # Подробный builder распознаёт имена без учёта затенения.
        if node.type == "binary_expression":
            return None
        if node.type in self.spec.call_nodes:
            function = node.child_by_field_name("function")
            name = self.callee_name(node)
            if not self._name(function, name):
                return None
        if result is None:
            return None
        if node.type in self.spec.call_nodes:
            kind = (
                M.OUTPUT
                if self.io_rule(self.spec.io_output, node) is not None
                else M.INPUT
            )
            return M.Simple(kind, result.text)
        return result

    def _console_setup(self, expr: Any) -> bool:
        """Скрывает только самостоятельную настройку среды с простыми аргументами."""
        if expr is None or expr.type != "call_expression":
            return False
        function = expr.child_by_field_name("function")
        if function is None:
            return False
        args = self.call_args(expr)
        name = self.raw(function)
        if name in {"SetConsoleCP", "SetConsoleOutputCP"}:
            return (
                name not in self._shadowed
                and name not in self.known
                and len(args) == 1
                and (
                    args[0].type == "number_literal"
                    or (
                        self.raw(args[0]) in _CONSOLE_CODEPAGES
                        and self.raw(args[0]) not in self._shadowed
                    )
                )
            )
        if self._name(function, "setlocale"):
            return (
                len(args) == 2
                and self.raw(args[0]) in _LOCALE_CATEGORIES
                and self.raw(args[0]) not in self._shadowed
                and self._string_value(args[1]) is not None
            )
        if name in {
            "std::ios::sync_with_stdio",
            "std::ios_base::sync_with_stdio",
        }:
            owner = name.split("::")[0]
            return (
                name not in self.known
                and owner not in self._shadowed
                and len(args) == 1
                and args[0].type in {"true", "false"}
            )
        if function.type == "field_expression":
            owner = function.child_by_field_name("argument")
            field = function.child_by_field_name("field")
            return (
                self.raw(field) == "tie"
                and any(
                    self._name(owner, stream)
                    for stream in ("cin", "cout", "cerr", "clog")
                )
                and len(args) == 1
                and self.raw(args[0]) in {"nullptr", "0"}
            )
        return False

    def k_expression(self, n: Any, r: dict) -> list[object]:
        expr = self._expr(n)
        if self._console_setup(expr):
            return []
        if (
            expr is not None
            and expr.type == "call_expression"
            and self._name(expr.child_by_field_name("function"), "system")
        ):
            args = self.call_args(expr)
            if (
                len(args) == 1
                and args[0].type == "string_literal"
                and self.raw(args[0]) == '"pause"'
            ):
                return []
        if expr is not None:
            stream = self._stream_parts(expr)
            if (
                stream
                and stream[0] == M.OUTPUT
                and all(
                    self._display_manipulator(p)
                    or (
                        (literal := self._string_value(p)) is not None
                        and not literal.strip()
                    )
                    for p in stream[1]
                )
            ):
                return []
        return super().k_expression(n, r)

    def _statements(self, node: Any) -> list[Any]:
        if node is None:
            return []
        if node.type in {"compound_statement", "else_clause"}:
            children = [
                child for child in self.named(node) if not self.spec.skipped(child)
            ]
            if node.type == "else_clause" and len(children) == 1:
                return self._statements(children[0])
            return children
        return [node]

    def _static_stream_output(self, node: Any) -> str | None:
        if node.type != "expression_statement":
            return None
        stream = self._stream_parts(self._expr(node))
        if stream is None or stream[0] != M.OUTPUT:
            return None
        literals = []
        for part in stream[1]:
            value = self._string_value(part)
            if value is not None:
                literals.append(value)
            elif not self._display_manipulator(part):
                return None
        return "".join(literals).strip() if literals else None

    def _cin_call(self, node: Any, name: str) -> list[Any] | None:
        if node.type != "expression_statement":
            return None
        call = self._expr(node)
        if call is None or call.type != "call_expression":
            return None
        function = call.child_by_field_name("function")
        if function is None or function.type != "field_expression":
            return None
        if (
            not self._name(function.child_by_field_name("argument"), "cin")
            or self.raw(function.child_by_field_name("field")) != name
            or self.raw(function.child_by_field_name("operator")) != "."
        ):
            return None
        return self.call_args(call)

    def _retry_input(self, node: Any) -> tuple[str, str] | None:
        condition = node.child_by_field_name("condition")
        if self._unwrap(condition).type != "true" or len(self.named(condition)) != 1:
            return None
        statements = self._statements(node.child_by_field_name("body"))
        if len(statements) != 2 or not self._prompt(statements[0]):
            return None
        check = statements[1]
        if check.type != "if_statement":
            return None
        read_condition = check.child_by_field_name("condition")
        if read_condition is None or len(self.named(read_condition)) != 1:
            return None
        read = self._stream_parts(self._unwrap(read_condition))
        if (
            read is None
            or read[0] != M.INPUT
            or len(read[1]) != 1
            or read[1][0].type != "identifier"
        ):
            return None
        success = self._statements(check.child_by_field_name("consequence"))
        if len(success) != 1 or success[0].type != "break_statement":
            return None
        failure = self._statements(check.child_by_field_name("alternative"))
        if len(failure) != 3:
            return None
        message = self._static_stream_output(failure[0])
        clear = self._cin_call(failure[1], "clear")
        ignore = self._cin_call(failure[2], "ignore")
        if not message or clear != [] or ignore is None or len(ignore) != 2:
            return None
        if (
            ignore[0].type != "number_literal"
            or self.raw(ignore[0]) != "10000"
            or ignore[1].type != "char_literal"
            or self.raw(ignore[1]) != "'\\n'"
        ):
            return None
        # При внешнем использовании потока сохраняем детали его состояния.
        if any(
            use.start_byte < node.start_byte or use.end_byte > node.end_byte
            for use in self._cin_uses
        ):
            return None
        return self.t(read[1][0]), message

    def k_while(self, n: Any, r: dict) -> list[object]:
        retry = self._retry_input(n)
        if retry is None:
            return super().k_while(n, r)
        target, message = retry
        if self.fn_is_main and getattr(self.opts, "checks", "hide") == "hide":
            return [M.Simple(M.INPUT, "Ввод " + target)]
        return [
            M.Simple(M.INPUT, "Ввод " + target),
            M.While(
                "Ошибка ввода?",
                M.Seq(
                    [
                        M.Simple(M.OUTPUT, message),
                        M.Simple(M.PROCESS, "Очистить ошибочный ввод"),
                        M.Simple(M.INPUT, "Ввод " + target),
                    ]
                ),
            ),
        ]

    def _prompt(self, node: Any) -> bool:
        expr = self._expr(node)
        stream = self._stream_parts(expr) if expr is not None else None
        if not stream or stream[0] != M.OUTPUT:
            return False
        visible = [p for p in stream[1] if not self._display_manipulator(p)]
        literals = [
            value for p in visible if (value := self._string_value(p)) is not None
        ]
        return (
            bool(literals)
            and all(
                self._string_value(p) is not None
                or (p.type == "identifier" and self.raw(p) in self._scalar_names)
                for p in visible
            )
            and "".join(literals)
            .strip()
            .lower()
            .startswith(("введите", "enter", "input"))
        )

    def _read(self, node: Any, stream: str) -> str | None:
        node = self._unwrap(node)
        if node is None or node.type != "binary_expression" or self.op_of(node) != ">>":
            return None
        left, right = self.sides(node)
        if self.raw(left) == stream and right.type == "identifier":
            return self.raw(right)
        return None

    def _validation(self, node: Any, stream: str) -> str | None:
        """Только !чтение || лишний_символ || !isfinite(значение)."""
        node = self._unwrap(node)
        if node is None or self.op_of(node) != "||":
            return None
        left, finite = self.sides(node)
        left = self._unwrap(left)
        if self.op_of(left) != "||":
            return None
        failed, extra = self.sides(left)
        failed = self._unwrap(failed)
        if failed.type != "unary_expression" or self.op_of(failed) != "!":
            return None
        target = self._read(failed.child_by_field_name("argument"), stream)
        extra_name = self._read(extra, stream)
        if (
            target
            and extra_name
            and extra_name != target
            and self._finite(finite) == (target, True)
        ):
            return target
        return None

    def _pipeline(
        self,
        nodes: list[Any],
        index: int,
        references: dict[str, set[int]],
        buffers: dict[str, list[int]],
    ) -> tuple[str, str] | None:
        if index + 2 >= len(nodes):
            return None
        read, declaration, check = nodes[index : index + 3]
        call = self._expr(read)
        if (
            call is None
            or call.type != "call_expression"
            or not self._name(call.child_by_field_name("function"), "getline")
        ):
            return None
        args = self.call_args(call)
        if (
            len(args) != 2
            or not self._name(args[0], "cin")
            or args[1].type != "identifier"
        ):
            return None
        line = self.raw(args[1])
        if declaration.type != "declaration" or not self._name(
            declaration.child_by_field_name("type"), "istringstream"
        ):
            return None
        decl = declaration.child_by_field_name("declarator")
        if decl is None or decl.type != "function_declarator":
            return None
        params = decl.child_by_field_name("parameters")
        name = decl.child_by_field_name("declarator")
        if (
            name is None
            or name.type != "identifier"
            or params is None
            or self.raw(params) != f"({line})"
        ):
            return None
        if check.type != "if_statement":
            return None
        stream = self.raw(name)
        target = self._validation(check.child_by_field_name("condition"), stream)
        if not target:
            return None
        # Обвязку скрываем лишь при отсутствии использования за пределами шаблона.
        buffer_declarations = buffers.get(line, [])
        if len(buffer_declarations) != 1 or buffer_declarations[0] >= index:
            return None
        if references.get(line, set()) - {buffer_declarations[0], index, index + 1}:
            return None
        if references.get(stream, set()) - {index + 1, index + 2}:
            return None
        condition = self._unwrap(check.child_by_field_name("condition"))
        extra_expr = self.sides(self._unwrap(self.sides(condition)[0]))[1]
        extra_name = self._read(extra_expr, stream)
        for position in references.get(extra_name, set()) - {index + 2}:
            other = nodes[position]
            if (
                other.type != "declaration"
                or self.raw(other.child_by_field_name("declarator")) != extra_name
            ):
                return None
        branches = [
            c
            for c in check.named_children
            if c != check.child_by_field_name("condition")
        ]
        for other in branches:
            stack = [other]
            while stack:
                child = stack.pop()
                if child.type in {"identifier", "type_identifier"} and self.raw(
                    child
                ) in {line, stream, extra_name}:
                    return None
                stack.extend(child.named_children)
        return target, line

    def _short_error(self, body: M.Seq, text: str, source: Any) -> None:
        if source is None:
            return
        statements = (
            [child for child in self.named(source) if not self.spec.skipped(child)]
            if source.type == "compound_statement"
            else [source]
        )
        # Сокращаем только статическое сообщение непосредственно перед возвратом.
        if (
            len(statements) != 2
            or statements[0].type != "expression_statement"
            or statements[1].type != "return_statement"
            or len(body.items) != 2
            or not isinstance(body.items[0], M.Simple)
            or body.items[0].kind != M.OUTPUT
            or not isinstance(body.items[1], M.Return)
        ):
            return
        stream = self._stream_parts(self._expr(statements[0]))
        if stream is None or stream[0] != M.OUTPUT:
            return
        parts = stream[1]
        if not any(self._string_value(part) is not None for part in parts):
            return
        if any(
            self._string_value(part) is None and not self._display_manipulator(part)
            for part in parts
        ):
            return
        body.items[0].text = text

    def _service_error_exit(self, node: Any) -> bool:
        """Только статическое сообщение и числовой код завершения main."""
        if not self.fn_is_main or getattr(self.opts, "checks", "hide") != "hide":
            return False
        statements = self._statements(node)
        if len(statements) != 2 or self._static_stream_output(statements[0]) is None:
            return False
        if statements[1].type != "return_statement":
            return False
        value = self._unwrap(next(iter(statements[1].named_children), None))
        if (
            value is not None
            and value.type == "unary_expression"
            and self.op_of(value) in {"+", "-"}
        ):
            value = self._unwrap(value.child_by_field_name("argument"))
        return value is not None and value.type == "number_literal"

    def k_if(self, n: Any, r: dict) -> list[object]:
        finite = self._finite(n.child_by_field_name("condition"))
        if n.child_by_field_name("alternative") is None and self._service_error_exit(
            n.child_by_field_name("consequence")
        ):
            if finite and finite[1]:
                return []
            condition = self._unwrap(n.child_by_field_name("condition"))
            if condition.type == "unary_expression" and self.op_of(condition) == "!":
                read = self._stream_parts(condition.child_by_field_name("argument"))
                if (
                    read
                    and read[0] == M.INPUT
                    and read[1]
                    and all(p.type == "identifier" for p in read[1])
                ):
                    return [
                        M.Simple(
                            M.INPUT, "Ввод " + ", ".join(self.t(p) for p in read[1])
                        )
                    ]
        result = super().k_if(n, r)
        if finite and finite[1]:
            self._short_error(
                result[-1].then_,
                "Ошибка: результат не конечен",
                self.find(n, r.get("then")),
            )
            if finite[0] == "sum" and self._sum_display:
                branch = result[-1]
                branch.cond = "Сумма конечна?"
                branch.then_, branch.else_ = branch.else_ or M.Seq(), branch.then_
        return result

    def k_block(self, n: Any, r: dict) -> list[object]:
        from .input_study import collect_input_groups

        nodes = [c for c in self.named(n) if c.type not in r.get("skip", ())]
        input_plan = collect_input_groups(self, n, nodes)
        references: dict[str, set[int]] = {}
        buffers: dict[str, list[int]] = {}
        for position, node in enumerate(nodes):
            if node.type == "declaration" and self._name(
                node.child_by_field_name("type"), "string"
            ):
                buffers.setdefault(
                    self.raw(node.child_by_field_name("declarator")), []
                ).append(position)
            stack = [node]
            while stack:
                child = stack.pop()
                if child.type in {"identifier", "type_identifier"}:
                    references.setdefault(self.raw(child), set()).add(position)
                stack.extend(child.named_children)
        pipelines = {
            i: match
            for i in range(len(nodes))
            if (match := self._pipeline(nodes, i, references, buffers))
        }
        technical = {line for _, line in pipelines.values()}
        array_outputs = {
            i: value
            for i, node in enumerate(nodes)
            if (value := array_output(self, node)) is not None
        }
        out = []
        index = 0
        output_values = None
        while index < len(nodes):
            node = nodes[index]
            if index in input_plan.hidden:
                index += 1
                continue
            if index in input_plan.groups:
                group = input_plan.groups[index]
                out.append(M.Simple(M.INPUT, group.text))
                output_values = None
                index = group.end
                continue
            if index + 1 in array_outputs and array_caption(self, node):
                index += 1
                continue
            if index in array_outputs:
                values = [array_outputs[index]]
                if output_values and out and out[-1].kind == M.OUTPUT:
                    output_values.extend(values)
                    out[-1].text = "Вывод " + ", ".join(output_values)
                else:
                    out.append(M.Simple(M.OUTPUT, "Вывод " + values[0]))
                    output_values = values
                index += 1
                continue
            initializations = self._literal_initializations(node)
            if initializations:
                next_index = index + 1
                while next_index < len(nodes):
                    following = self._literal_initializations(nodes[next_index])
                    if (
                        not following
                        or len(initializations) + len(following) > _MAX_INITIALIZATIONS
                    ):
                        break
                    combined = initializations + following
                    if len("; ".join(combined)) > _MAX_INITIALIZATION_TEXT:
                        break
                    initializations = combined
                    next_index += 1
                out.append(M.Simple(M.PROCESS, "; ".join(initializations)))
                output_values = None
                index = next_index
                continue
            if (
                node.type == "declaration"
                and self._name(node.child_by_field_name("type"), "string")
                and self.raw(node.child_by_field_name("declarator")) in technical
            ):
                index += 1
                continue
            if index in pipelines:
                target, _ = pipelines[index]
                if out and index and self._prompt(nodes[index - 1]):
                    out.pop()
                out.append(M.Simple(M.INPUT, "Ввод " + target))
                check = nodes[index + 2]
                if check.child_by_field_name(
                    "alternative"
                ) is None and self._service_error_exit(
                    check.child_by_field_name("consequence")
                ):
                    output_values = None
                    index += 3
                    continue
                branch = self.stmt(nodes[index + 2])[-1]
                branch.cond = "Ошибка ввода?"
                self._short_error(
                    branch.then_,
                    "Ошибка ввода",
                    nodes[index + 2].child_by_field_name("consequence"),
                )
                out.append(branch)
                output_values = None
                index += 3
                continue
            # При прямом вводе достаточно одного блока вместе с приглашением.
            if self._prompt(node) and index + 1 < len(nodes):
                following = self._expr(nodes[index + 1])
                stream = (
                    self._stream_parts(following) if following is not None else None
                )
                if stream and stream[0] == M.INPUT:
                    index += 1
                    continue
            statements = self.stmt(node)
            stream = (
                self._stream_parts(self._expr(node))
                if node.type == "expression_statement"
                else None
            )
            values = None
            if stream and stream[0] == M.OUTPUT:
                visible = [
                    p
                    for p in stream[1]
                    if self._string_value(p) is None
                    and not self._display_manipulator(p)
                ]
                if (
                    visible
                    and all(p.type == "identifier" for p in visible)
                    and self._compact_output(stream[1])
                ):
                    values = [self.t(p) for p in visible]
            if values and output_values and out and out[-1].kind == M.OUTPUT:
                output_values.extend(values)
                out[-1].text = "Вывод " + ", ".join(output_values)
            else:
                out.extend(statements)
                if statements or not stream:
                    output_values = values
            index += 1
        return out
