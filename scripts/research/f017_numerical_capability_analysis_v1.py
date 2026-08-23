#!/usr/bin/env python3
"""Semantic, fail-closed capability analysis for F017 pure numerical cores.

The analyzer treats imported NumPy and MLX module objects as capabilities.
Capabilities are identified from import semantics, never from a preferred local
spelling.  Module objects and module members may only occur as exact direct
uses authorized by the capability contract; they may not be rebound,
transported, returned, captured, or placed in containers.
"""
from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


NUMPY_MODULE = "PYTHON_MODULE_NUMPY"
MLX_MODULE = "PYTHON_MODULE_MLX_CORE"
UNKNOWN = "UNKNOWN"
SAFE_SCALAR = "SAFE_SCALAR"
ARRAY_VALUE = "ARRAY_VALUE"
HASH_OBJECT = "HASH_OBJECT"
SAFE_LIST = "SAFE_LIST"
SAFE_DICT = "SAFE_DICT"
SAFE_SET = "SAFE_SET"
SAFE_BYTES = "SAFE_BYTES"
SAFE_STRING = "SAFE_STRING"
SOURCE_OBJECT = "PROTOCOL_OBJECT:SOURCE"
STORE_OBJECT = "PROTOCOL_OBJECT:STORE"
ROW_MATRIX = "PROTOCOL_OBJECT:ROW_MATRIX"
ROW_MATRIX_OR_ARRAY = "PROTOCOL_OBJECT:ROW_MATRIX_OR_ARRAY"
CONTAINER_CAPABILITY = "CONTAINER_CONTAINING_CAPABILITY"


class CapabilityViolation(ValueError):
    """A pure core exposes a capability outside the frozen policy."""


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"


def _scope_name(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    parts: list[str] = []
    current: ast.AST | None = node
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            parts.append(current.name)
        elif isinstance(current, ast.Lambda):
            parts.append("<lambda>")
        current = parents.get(current)
    return ".".join(reversed(parts)) or "<module>"


def _semantic_import(module: str, identities: dict[str, str]) -> str | None:
    """Resolve a capability module by semantic package ancestry."""
    matches = [name for name in identities if module == name or module.startswith(name + ".")]
    if not matches:
        return None
    return identities[max(matches, key=len)]


def _scope_candidates(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> list[str]:
    """Return Python lexical scopes, excluding class scope from method lookup."""
    current: ast.AST | None = node
    functions: list[ast.AST] = []
    nearest_class: ast.ClassDef | None = None
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            functions.append(current)
        elif isinstance(current, ast.ClassDef) and nearest_class is None:
            nearest_class = current
        current = parents.get(current)
    if functions:
        return [_scope_name(scope, parents) for scope in functions] + ["<module>"]
    if nearest_class is not None:
        return [_scope_name(nearest_class, parents), "<module>"]
    return ["<module>"]


def _contains(node: ast.AST, target: ast.AST) -> bool:
    return any(part is target for part in ast.walk(node))


def _is_annotation(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    current = node
    while current in parents:
        parent = parents[current]
        if isinstance(parent, ast.arg) and parent.annotation is not None and _contains(parent.annotation, node):
            return True
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)) and parent.returns is not None and _contains(parent.returns, node):
            return True
        if isinstance(parent, ast.AnnAssign) and parent.annotation is not None and _contains(parent.annotation, node):
            return True
        if isinstance(parent, (ast.stmt, ast.Lambda)):
            break
        current = parent
    return False


def _terminal_attribute(callable_node: ast.AST) -> str | None:
    if isinstance(callable_node, ast.Attribute):
        return callable_node.attr
    if isinstance(callable_node, ast.Name):
        return callable_node.id
    return None


def _capability_member(provenance: str) -> bool:
    return provenance.startswith("NUMPY_MEMBER:") or provenance.startswith("MLX_MEMBER:")


def _capability(provenance: str) -> bool:
    return provenance in {NUMPY_MODULE, MLX_MODULE, CONTAINER_CAPABILITY} or _capability_member(provenance)


def _join(values: Iterable[str]) -> str:
    values = set(values)
    if any(_capability(value) for value in values):
        if len(values) == 1:
            return next(iter(values))
        return CONTAINER_CAPABILITY
    if len(values) == 1:
        return next(iter(values))
    if not values:
        return UNKNOWN
    if values <= {SAFE_SCALAR, SAFE_STRING, SAFE_BYTES}:
        return SAFE_SCALAR
    return UNKNOWN


def _target_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for element in target.elts for name in _target_names(element)]
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    # Attribute and subscript assignments mutate an object; they do not bind
    # the root name in Python's lexical environment.
    return []


@dataclass(frozen=True)
class AnalysisResult:
    path: str
    module_aliases: dict[str, str]
    approved_module_uses: tuple[dict, ...]
    approved_receiver_uses: tuple[dict, ...]
    bytecode_names: tuple[str, ...]

    def as_json(self) -> dict:
        return {
            "path": self.path,
            "module_aliases": self.module_aliases,
            "approved_module_uses": list(self.approved_module_uses),
            "approved_receiver_uses": list(self.approved_receiver_uses),
            "bytecode_names": list(self.bytecode_names),
        }


class CapabilityAnalyzer:
    def __init__(self, policy: dict, *, role: str, path: str):
        self.policy = policy
        self.role = role
        self.path = path
        self.module_aliases: dict[str, str] = {}
        self.capability_imports: list[dict] = []
        self.bindings: dict[tuple[str, str], str] = {}
        self.parents: dict[ast.AST, ast.AST] = {}
        self.module_uses: list[dict] = []
        self.receiver_uses: list[dict] = []

    def _error(self, node: ast.AST, classification: str, detail: str) -> None:
        raise CapabilityViolation(
            f"{classification}:{self.path}:{getattr(node, 'lineno', 0)}:{getattr(node, 'col_offset', 0)}:{detail}"
        )

    def _imports(self, tree: ast.AST) -> None:
        identities = self.policy["module_identities"]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    semantic = _semantic_import(alias.name, identities)
                    if semantic:
                        local = alias.asname or alias.name.split(".")[0]
                        self.capability_imports.append({
                            "module": alias.name,
                            "local": local,
                            "scope": _scope_name(node, self.parents),
                        })
                        self.module_aliases[local] = semantic
                        self.bindings[(_scope_name(node, self.parents), local)] = semantic
            elif isinstance(node, ast.ImportFrom):
                if node.module and _semantic_import(node.module, identities):
                    self._error(node, "CAPABILITY_IMPORT_FROM_PROHIBITED", node.module or "")
                if node.names and any(alias.name == "*" for alias in node.names):
                    self._error(node, "CAPABILITY_STAR_IMPORT_PROHIBITED", node.module or "")

    def _expression(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return self._binding_for(node.id, node)
        if isinstance(node, ast.Attribute):
            base = self._expression(node.value)
            if base == NUMPY_MODULE:
                return f"NUMPY_MEMBER:{node.attr}"
            if base == MLX_MODULE:
                return f"MLX_MEMBER:{node.attr}"
            role = self._receiver_role(node.value)
            receiver_policy = self.policy["receiver_roles"].get(role, {})
            returns = receiver_policy.get("methods", {}).get(node.attr)
            return returns or receiver_policy.get("attribute_returns", {}).get(node.attr, UNKNOWN)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = [self._expression(value) for value in node.elts]
            return CONTAINER_CAPABILITY if any(_capability(value) for value in values) else {
                ast.List: SAFE_LIST, ast.Tuple: UNKNOWN, ast.Set: SAFE_SET
            }[type(node)]
        if isinstance(node, ast.Dict):
            values = [self._expression(value) for value in node.values]
            return CONTAINER_CAPABILITY if any(_capability(value) for value in values) else SAFE_DICT
        if isinstance(node, ast.IfExp):
            return _join((self._expression(node.body), self._expression(node.orelse)))
        if isinstance(node, ast.BoolOp):
            return _join(self._expression(value) for value in node.values)
        if isinstance(node, ast.NamedExpr):
            return self._expression(node.value)
        if isinstance(node, ast.Lambda):
            captures = [self._expression(part) for part in ast.walk(node.body) if isinstance(part, ast.Name)]
            return CONTAINER_CAPABILITY if any(_capability(value) for value in captures) else UNKNOWN
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                return SAFE_STRING
            if isinstance(node.value, bytes):
                return SAFE_BYTES
            return SAFE_SCALAR
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                base = self._expression(node.func.value)
                if isinstance(node.func.value, ast.Name) and node.func.value.id in self.policy["standard_module_roots"]:
                    return self.policy["standard_member_return_provenance"].get(
                        f"{node.func.value.id}.{node.func.attr}", UNKNOWN
                    )
                if base in {NUMPY_MODULE, MLX_MODULE}:
                    member = f"{'NUMPY' if base == NUMPY_MODULE else 'MLX'}_MEMBER:{node.func.attr}"
                    return self.policy["member_return_provenance"].get(member, UNKNOWN)
                role = self._receiver_role(node.func.value)
                return self.policy["receiver_roles"].get(role, {}).get("methods", {}).get(node.func.attr, UNKNOWN)
            if isinstance(node.func, ast.Name):
                if node.func.id in self.policy.get("function_return_provenance", {}):
                    return self.policy["function_return_provenance"][node.func.id]
                if node.func.id in {"list", "sorted"}:
                    return SAFE_LIST
                if node.func.id in {"dict"}:
                    return SAFE_DICT
                if node.func.id in {"set"}:
                    return SAFE_SET
                if node.func.id in {"str"}:
                    return SAFE_STRING
                if node.func.id in {"bytes", "bytearray"}:
                    return SAFE_BYTES
                if node.func.id in {"float", "int", "len", "sum", "max", "min", "range", "enumerate", "zip"}:
                    return SAFE_SCALAR
            return UNKNOWN
        if isinstance(node, ast.Subscript):
            base = self._expression(node.value)
            if base == CONTAINER_CAPABILITY:
                return CONTAINER_CAPABILITY
            if base in {ARRAY_VALUE, ROW_MATRIX_OR_ARRAY}:
                return ARRAY_VALUE
            return UNKNOWN
        if isinstance(node, (ast.BinOp, ast.UnaryOp, ast.Compare)):
            if isinstance(node, ast.BinOp):
                children = [self._expression(node.left), self._expression(node.right)]
            elif isinstance(node, ast.UnaryOp):
                children = [self._expression(node.operand)]
            else:
                children = [self._expression(node.left), *(self._expression(value) for value in node.comparators)]
            if any(_capability(value) for value in children):
                return CONTAINER_CAPABILITY
            if ARRAY_VALUE in children:
                return ARRAY_VALUE
            if isinstance(node, ast.BinOp) and children and all(value == SAFE_STRING for value in children):
                return SAFE_STRING
            if isinstance(node, ast.BinOp) and children and all(value == SAFE_BYTES for value in children):
                return SAFE_BYTES
            return SAFE_SCALAR
        return UNKNOWN

    def _seed_parameters(self, tree: ast.AST) -> None:
        parameter_roles = self.policy["parameter_roles"].get(self.role, {})
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            if node.args.vararg is not None:
                arguments.append(node.args.vararg)
            if node.args.kwarg is not None:
                arguments.append(node.args.kwarg)
            for argument in arguments:
                keys = (f"{_scope_name(node, self.parents)}.{argument.arg}", f"{node.name}.{argument.arg}")
                provenance = UNKNOWN
                for key in keys:
                    if key in parameter_roles:
                        provenance = parameter_roles[key]
                        break
                self.bindings[(_scope_name(node, self.parents), argument.arg)] = provenance

    def _binding_for(self, name: str, node: ast.AST) -> str:
        for candidate in _scope_candidates(node, self.parents):
            value = self.bindings.get((candidate, name))
            if value is not None:
                return value
        return self.module_aliases.get(name, UNKNOWN)

    def _fixed_point(self, tree: ast.AST) -> None:
        self._seed_parameters(tree)
        changed = True
        rounds = 0
        while changed:
            changed = False
            rounds += 1
            if rounds > max(16, len(list(ast.walk(tree))) * 2):
                raise CapabilityViolation("CAPABILITY_ANALYSIS_DID_NOT_CONVERGE")
            for node in ast.walk(tree):
                pairs: list[tuple[ast.AST, ast.AST]] = []
                if isinstance(node, ast.Assign):
                    pairs.extend((target, node.value) for target in node.targets)
                elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
                    pairs.append((node.target, node.value))
                elif isinstance(node, (ast.For, ast.AsyncFor)):
                    pairs.append((node.target, node.iter))
                elif isinstance(node, ast.AugAssign):
                    pairs.append((node.target, node.value))
                elif isinstance(node, (ast.With, ast.AsyncWith)):
                    pairs.extend((item.optional_vars, item.context_expr) for item in node.items if item.optional_vars)
                elif isinstance(node, ast.comprehension):
                    pairs.append((node.target, node.iter))
                elif isinstance(node, ast.ExceptHandler) and node.name:
                    target = ast.Name(id=node.name, ctx=ast.Store())
                    ast.copy_location(target, node)
                    pairs.append((target, ast.Constant(value=None)))
                elif isinstance(node, ast.Match):
                    for pattern in ast.walk(node):
                        if isinstance(pattern, ast.MatchAs) and pattern.name:
                            target = ast.Name(id=pattern.name, ctx=ast.Store())
                            ast.copy_location(target, pattern)
                            pairs.append((target, ast.Constant(value=None)))
                        elif isinstance(pattern, ast.MatchStar) and pattern.name:
                            target = ast.Name(id=pattern.name, ctx=ast.Store())
                            ast.copy_location(target, pattern)
                            pairs.append((target, ast.Constant(value=None)))
                for target, value in pairs:
                    scope = _scope_name(node, self.parents)
                    expanded = list(zip(target.elts, value.elts, strict=True)) if (
                        isinstance(target, (ast.Tuple, ast.List))
                        and isinstance(value, (ast.Tuple, ast.List))
                        and len(target.elts) == len(value.elts)
                    ) else [(target, value)]
                    for part_target, part_value in expanded:
                        provenance = self._expression(part_value)
                        for name in _target_names(part_target):
                            binding = (scope, name)
                            old = self.bindings.get(binding)
                            merged = provenance if old is None else _join((old, provenance))
                            if merged != old:
                                self.bindings[binding] = merged
                                changed = True

    def _approved_member_context(self, node: ast.Attribute, semantic: str) -> str | None:
        module_policy = self.policy["semantic_modules"][semantic]
        member = node.attr
        parent = self.parents.get(node)
        if member in module_policy["direct_callable_members"] and isinstance(parent, ast.Call) and parent.func is node:
            return "DIRECT_CALLABLE"
        if member in module_policy["type_dtype_members"]:
            if isinstance(parent, ast.Call) and parent.func is node:
                return "DIRECT_TYPE_OR_DTYPE_CALL"
            if _is_annotation(node, self.parents):
                return "DIRECT_TYPE_ANNOTATION"
            call: ast.Call | None = None
            if isinstance(parent, ast.keyword) and parent.value is node:
                maybe = self.parents.get(parent)
                call = maybe if isinstance(maybe, ast.Call) else None
                if parent.arg != "dtype":
                    return None
            elif isinstance(parent, ast.Call) and node in parent.args:
                call = parent
            if call is not None and _terminal_attribute(call.func) in module_policy["dtype_consumers"]:
                return "DIRECT_DTYPE_ARGUMENT"
        return None

    def _receiver_role(self, node: ast.AST) -> str:
        provenance = self._expression(node)
        if provenance in self.policy["receiver_roles"]:
            return provenance
        if isinstance(node, ast.Name):
            return self._binding_for(node.id, node)
        if isinstance(node, ast.Call):
            return self._expression(node)
        if isinstance(node, ast.Subscript):
            base = self._expression(node.value)
            return ARRAY_VALUE if base in {ARRAY_VALUE, ROW_MATRIX_OR_ARRAY} else UNKNOWN
        if isinstance(node, (ast.BinOp, ast.UnaryOp)):
            return self._expression(node)
        return UNKNOWN

    def _validate_module_uses(self, tree: ast.AST) -> None:
        dynamic_names = set(self.policy["prohibited_dynamic_names"])
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in dynamic_names:
                self._error(node, "DYNAMIC_CAPABILITY_SURFACE", node.id)
            if isinstance(node, ast.Attribute) and node.attr in self.policy["prohibited_meta_attributes"]:
                self._error(node, "META_CAPABILITY_SURFACE", node.attr)
            if not isinstance(node, ast.Name) or node.id not in self.module_aliases:
                continue
            semantic = self.module_aliases[node.id]
            parent = self.parents.get(node)
            if not isinstance(parent, ast.Attribute) or parent.value is not node:
                self._error(node, "MODULE_CAPABILITY_ESCAPE", node.id)
            if isinstance(self.parents.get(parent), ast.Attribute):
                self._error(parent, "CAPABILITY_ATTRIBUTE_CHAIN", ast.unparse(parent))
            context = self._approved_member_context(parent, semantic)
            if context is None:
                self._error(parent, "UNAPPROVED_MODULE_MEMBER_CONTEXT", f"{semantic}.{parent.attr}")
            self.module_uses.append({
                "semantic_module": semantic,
                "member": parent.attr,
                "context_class": context,
                "scope": _scope_name(parent, self.parents),
                "node_class": type(parent).__name__,
                "line": parent.lineno,
                "column": parent.col_offset,
                "direct": True,
                "expected_return_provenance": self.policy["member_return_provenance"].get(
                    f"{'NUMPY' if semantic == NUMPY_MODULE else 'MLX'}_MEMBER:{parent.attr}", UNKNOWN
                ),
            })

    def _validate_capability_transport(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                value = self._expression(node.value)
                if _capability(value):
                    self._error(node, "CAPABILITY_ASSIGNMENT_ESCAPE", value)
            elif isinstance(node, ast.AnnAssign):
                if _capability(self._expression(node.value)):
                    self._error(node, "CAPABILITY_ANNOTATED_ASSIGNMENT_ESCAPE", ast.unparse(node.value))
            elif isinstance(node, ast.NamedExpr):
                if _capability(self._expression(node.value)):
                    self._error(node, "CAPABILITY_NAMED_EXPRESSION_ESCAPE", ast.unparse(node.value))
            elif isinstance(node, ast.AugAssign):
                if _capability(self._expression(node.target)) or _capability(self._expression(node.value)):
                    self._error(node, "CAPABILITY_AUGMENTED_ASSIGNMENT_ESCAPE", ast.unparse(node))
            elif isinstance(node, (ast.Return, ast.Yield, ast.YieldFrom)) and node.value is not None:
                if _capability(self._expression(node.value)):
                    self._error(node, "CAPABILITY_RETURN_ESCAPE", ast.unparse(node.value))
            elif isinstance(node, ast.Call):
                for argument in (*node.args, *(keyword.value for keyword in node.keywords)):
                    if _capability(self._expression(argument)):
                        # Approved dtype arguments are handled by the direct-use rule.
                        if isinstance(argument, ast.Attribute) and isinstance(argument.value, ast.Name) and argument.value.id in self.module_aliases:
                            semantic = self.module_aliases[argument.value.id]
                            if self._approved_member_context(argument, semantic):
                                continue
                        self._error(argument, "CAPABILITY_ARGUMENT_ESCAPE", ast.unparse(argument))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                defaults = (*node.args.defaults, *(value for value in node.args.kw_defaults if value is not None))
                for value in defaults:
                    if _capability(self._expression(value)):
                        self._error(value, "CAPABILITY_DEFAULT_CAPTURE", ast.unparse(value))
                decorators = getattr(node, "decorator_list", ())
                for value in decorators:
                    if _capability(self._expression(value)):
                        self._error(value, "CAPABILITY_DECORATOR_ESCAPE", ast.unparse(value))

    def _validate_receiver_calls(self, tree: ast.AST) -> None:
        ignored = set(self.policy["non_method_attributes"])
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            receiver = node.func.value
            if isinstance(receiver, ast.Name) and receiver.id in self.module_aliases:
                continue
            if isinstance(receiver, ast.Name) and receiver.id in self.policy["standard_module_roots"]:
                continue
            method = node.func.attr
            if method in ignored:
                continue
            role = self._receiver_role(receiver)
            allowed = self.policy["receiver_roles"].get(role, {}).get("methods", {})
            if method not in allowed:
                self._error(node, "UNAPPROVED_RECEIVER_METHOD", f"{role}.{method}")
            self.receiver_uses.append({
                "receiver_role": role,
                "method": method,
                "scope": _scope_name(node, self.parents),
                "node_class": type(node).__name__,
                "line": node.lineno,
                "column": node.col_offset,
                "direct": False,
                "expected_return_provenance": allowed[method],
            })

    def analyze(self, text: str) -> AnalysisResult:
        tree = ast.parse(text, filename=self.path)
        self.parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        self._imports(tree)
        if sorted(self.capability_imports, key=lambda item: (item["module"], item["scope"], item["local"])) != sorted(
            self.policy["exact_capability_imports"][self.role],
            key=lambda item: (item["module"], item["scope"], item["local"]),
        ):
            raise CapabilityViolation(f"CAPABILITY_IMPORT_CENSUS:{self.path}")
        self._fixed_point(tree)
        self._validate_capability_transport(tree)
        self._validate_module_uses(tree)
        self._validate_receiver_calls(tree)
        bytecode_names = tuple(sorted({
            name
            for code in _code_objects(compile(tree, self.path, "exec"))
            for name in code.co_names
        }))
        return AnalysisResult(
            self.path,
            dict(sorted(self.module_aliases.items())),
            tuple(sorted(self.module_uses, key=lambda value: (value["line"], value["column"], value["member"]))),
            tuple(sorted(self.receiver_uses, key=lambda value: (value["line"], value["column"], value["method"]))),
            bytecode_names,
        )


def _code_objects(code):
    yield code
    for constant in code.co_consts:
        if hasattr(constant, "co_consts") and hasattr(constant, "co_names"):
            yield from _code_objects(constant)


def load_policy(path: Path) -> dict:
    value = json.loads(path.read_text())
    if value.get("schema") != "pulsarmlx.f017.numerical-capability-policy/1.0.0":
        raise CapabilityViolation("CAPABILITY_POLICY_SCHEMA")
    return value


def analyze_path(path: Path, policy_path: Path, role: str) -> AnalysisResult:
    return CapabilityAnalyzer(load_policy(policy_path), role=role, path=str(path)).analyze(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--role", choices=("primary", "secondary"), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze_path(args.source, args.policy, args.role).as_json()
    payload = _canonical_json({"result": "PASS", **result})
    if args.output:
        args.output.write_bytes(payload)
    else:
        print(payload.decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
