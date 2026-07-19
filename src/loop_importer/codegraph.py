from __future__ import annotations

import ast
import hashlib
from collections import Counter
from pathlib import Path
from typing import Any, Protocol


ENGINE_NAME = "python-ast-lite"
FRAGMENT_SCHEMA_VERSION = "1.0"


class CodeGraphBackend(Protocol):
    """Interface for read-only code-structure graph backends."""

    engine_name: str

    def build(
        self,
        source: Path,
        artifacts: list[dict[str, Any]],
        project_id: str,
        max_source_bytes: int,
        previous_graph: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _module_name(relative_path: str) -> str:
    parts = list(Path(relative_path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or "__root__"


def _qualified(module: str, qualname: str) -> str:
    return f"{module}.{qualname}" if qualname else module


def _evidence(
    artifact: dict[str, Any], line_start: int, line_end: int | None = None
) -> dict[str, Any]:
    return {
        "artifact_id": artifact["artifact_id"],
        "sha256": artifact["sha256"],
        "path": artifact["path"],
        "line_start": line_start,
        "line_end": line_end if line_end is not None else line_start,
    }


def _node(
    kind: str,
    canonical: str,
    name: str,
    parent: str | None,
    artifact: dict[str, Any],
    line_start: int,
    line_end: int,
    definition_index: int = 1,
) -> dict[str, Any]:
    return {
        "node_id": _stable_id(
            "CGN",
            f"{kind}:{canonical}:{artifact['artifact_id']}:{definition_index}",
        ),
        "kind": kind,
        "name": name,
        "qualified_name": canonical,
        "definition_index": definition_index,
        "parent_qualified_name": parent,
        "evidence": _evidence(artifact, line_start, line_end),
    }


def _attribute_name(value: ast.AST) -> str | None:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        prefix = _attribute_name(value.value)
        return f"{prefix}.{value.attr}" if prefix else None
    return None


def _resolve_relative_module(
    current_module: str,
    source_is_package: bool,
    imported_module: str | None,
    level: int,
) -> str:
    if level == 0:
        return imported_module or ""
    package = current_module if source_is_package else current_module.rpartition(".")[0]
    package_parts = [] if package in {"", "__root__"} else package.split(".")
    keep = max(0, len(package_parts) - (level - 1))
    base = package_parts[:keep]
    if imported_module:
        base.extend(imported_module.split("."))
    return ".".join(base)


class _BindingVisitor(ast.NodeVisitor):
    """Collect names local to one function without entering nested scopes."""

    def __init__(self) -> None:
        self.names: set[str] = set()
        self.nonlocal_names: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.names.add(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.names.add(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.names.add(alias.asname or alias.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.names.add(node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.names.add(node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.names.add(node.name)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_Global(self, node: ast.Global) -> None:
        self.nonlocal_names.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.nonlocal_names.update(node.names)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.names.add(node.name)
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self.names.add(node.name)
        self.generic_visit(node)


def _function_bindings(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    arguments = {
        argument.arg
        for argument in [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]
    }
    if node.args.vararg:
        arguments.add(node.args.vararg.arg)
    if node.args.kwarg:
        arguments.add(node.args.kwarg.arg)
    visitor = _BindingVisitor()
    for statement in node.body:
        visitor.visit(statement)
    return sorted((arguments | visitor.names) - visitor.nonlocal_names)


class _FragmentVisitor(ast.NodeVisitor):
    def __init__(
        self,
        module: str,
        artifact: dict[str, Any],
        source_is_package: bool,
        line_count: int,
    ) -> None:
        self.module = module
        self.artifact = artifact
        self.source_is_package = source_is_package
        self.scope: list[str] = [module]
        self.scope_kind: list[str] = ["module"]
        self.qualname: list[str] = []
        self.nodes: list[dict[str, Any]] = [
            _node(
                "module", module, module, None, artifact, 1, max(1, line_count)
            )
        ]
        self.imports: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.bindings: dict[str, list[str]] = {}
        self.definition_counts: Counter[tuple[str, str]] = Counter()

    @property
    def owner(self) -> str:
        return self.scope[-1]

    def _visit_definition(self, value: ast.AST, name: str, kind: str) -> None:
        qualname = ".".join([*self.qualname, name])
        canonical = _qualified(self.module, qualname)
        parent = self.owner
        key = (kind, canonical)
        self.definition_counts[key] += 1
        self.nodes.append(
            _node(
                kind,
                canonical,
                name,
                parent,
                self.artifact,
                getattr(value, "lineno", 1),
                getattr(value, "end_lineno", None) or getattr(value, "lineno", 1),
                self.definition_counts[key],
            )
        )
        self.scope.append(canonical)
        self.scope_kind.append(kind)
        self.qualname.append(name)
        for statement in getattr(value, "body", []):
            self.visit(statement)
        self.qualname.pop()
        self.scope_kind.pop()
        self.scope.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_definition(node, node.name, "class")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        kind = "method" if self.scope_kind[-1] == "class" else "function"
        qualname = ".".join([*self.qualname, node.name])
        self.bindings[_qualified(self.module, qualname)] = _function_bindings(node)
        self._visit_definition(node, node.name, kind)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        kind = "method" if self.scope_kind[-1] == "class" else "function"
        qualname = ".".join([*self.qualname, node.name])
        self.bindings[_qualified(self.module, qualname)] = _function_bindings(node)
        self._visit_definition(node, node.name, kind)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            target = alias.name if alias.asname else alias.name.split(".")[0]
            self.imports.append({
                "owner": self.owner,
                "local": local,
                "target": target,
                "target_module": alias.name,
                "line": node.lineno,
            })

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        target_module = _resolve_relative_module(
            self.module, self.source_is_package, node.module, node.level
        )
        for alias in node.names:
            local = alias.asname or alias.name
            target = ".".join(part for part in (target_module, alias.name) if part)
            self.imports.append({
                "owner": self.owner,
                "local": local,
                "target": target,
                "target_module": target_module,
                "line": node.lineno,
            })

    def visit_Call(self, node: ast.Call) -> None:
        expression = _attribute_name(node.func)
        self.calls.append({
            "owner": self.owner,
            "expression": expression,
            "line": node.lineno,
            "dynamic": expression is None,
        })
        self.generic_visit(node)


def _parse_fragment(source: Path, artifact: dict[str, Any]) -> dict[str, Any]:
    relative_path = artifact["path"]
    module = _module_name(relative_path)
    source_is_package = Path(relative_path).name == "__init__.py"
    fragment: dict[str, Any] = {
        "artifact_id": artifact["artifact_id"],
        "path": relative_path,
        "sha256": artifact["sha256"],
        "module": module,
        "nodes": [],
        "imports": [],
        "calls": [],
        "bindings": {},
        "parse_error": None,
    }
    try:
        data = (source / Path(relative_path)).read_bytes()
    except OSError as exc:
        fragment["parse_error"] = {
            "kind": "READ_ERROR",
            "message": str(exc),
            "line": None,
        }
        return fragment

    observed_sha256 = hashlib.sha256(data).hexdigest()
    if observed_sha256 != artifact["sha256"]:
        fragment["parse_error"] = {
            "kind": "EVIDENCE_CHANGED_DURING_SCAN",
            "message": "File content changed after artifact hashing; no symbols were accepted.",
            "line": None,
        }
        return fragment
    text = data.decode("utf-8", errors="replace")

    line_count = len(text.splitlines())
    try:
        tree = ast.parse(text, filename=relative_path)
    except SyntaxError as exc:
        fragment["nodes"] = [
            _node(
                "module", module, module, None, artifact, 1, max(1, line_count)
            )
        ]
        fragment["parse_error"] = {
            "kind": "SYNTAX_ERROR",
            "message": exc.msg,
            "line": exc.lineno,
        }
        return fragment

    visitor = _FragmentVisitor(module, artifact, source_is_package, line_count)
    visitor.visit(tree)
    fragment["nodes"] = visitor.nodes
    fragment["imports"] = visitor.imports
    fragment["calls"] = visitor.calls
    fragment["bindings"] = visitor.bindings
    return fragment


def _edge(
    kind: str,
    source_id: str,
    target_id: str,
    artifact: dict[str, Any],
    line: int,
    confidence: str = "STRUCTURAL",
) -> dict[str, Any]:
    identity = f"{kind}:{source_id}:{target_id}:{artifact['artifact_id']}:{line}"
    return {
        "edge_id": _stable_id("CGE", identity),
        "kind": kind,
        "source_node_id": source_id,
        "target_node_id": target_id,
        "confidence": confidence,
        "evidence": _evidence(artifact, line),
    }


def _alias_maps(
    fragment: dict[str, Any], owner: str
) -> tuple[dict[str, str], dict[str, str]]:
    module_aliases: dict[str, str] = {}
    owner_aliases: dict[str, str] = {}
    for item in fragment["imports"]:
        if item["owner"] == fragment["module"]:
            module_aliases[item["local"]] = item["target"]
        if item["owner"] == owner:
            owner_aliases[item["local"]] = item["target"]
    return module_aliases, owner_aliases


def _resolve_call(
    expression: str,
    owner: str,
    fragment: dict[str, Any],
    nodes_by_name: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    parts = expression.split(".")
    module_aliases, owner_aliases = _alias_maps(fragment, owner)
    local_bindings = set(fragment.get("bindings", {}).get(owner, []))
    candidates: list[str] = []

    if parts[0] in owner_aliases:
        candidates.append(".".join([owner_aliases[parts[0]], *parts[1:]]))
    elif parts[0] not in local_bindings and parts[0] in module_aliases:
        candidates.append(".".join([module_aliases[parts[0]], *parts[1:]]))

    if parts[0] in {"self", "cls"} and len(parts) > 1:
        ancestor = owner
        while ancestor.startswith(fragment["module"]):
            ancestor = ancestor.rpartition(".")[0]
            node = nodes_by_name.get(ancestor)
            if node and node["kind"] == "class":
                candidates.append(".".join([ancestor, *parts[1:]]))
                break

    if parts[0] in local_bindings:
        candidates.append(f"{owner}.{expression}")
        for candidate in dict.fromkeys(candidates):
            target = nodes_by_name.get(candidate)
            if target:
                return target
        return None
    if len(parts) == 1:
        namespace = owner.rpartition(".")[0]
        while namespace and namespace.startswith(fragment["module"]):
            candidates.append(f"{namespace}.{expression}")
            if namespace == fragment["module"]:
                break
            namespace = namespace.rpartition(".")[0]
        candidates.append(f"{fragment['module']}.{expression}")
    else:
        candidates.append(f"{fragment['module']}.{expression}")

    for candidate in dict.fromkeys(candidates):
        target = nodes_by_name.get(candidate)
        if target:
            return target
    return None


def _resolve_graph(
    fragments: list[dict[str, Any]], artifacts_by_id: dict[str, dict[str, Any]]
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    nodes = sorted(
        (node for fragment in fragments for node in fragment["nodes"]),
        key=lambda item: item["node_id"],
    )
    nodes_by_name_groups: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        nodes_by_name_groups.setdefault(node["qualified_name"], []).append(node)
    nodes_by_name = {
        name: group[0]
        for name, group in nodes_by_name_groups.items()
        if len(group) == 1
    }
    ambiguous_symbols = [
        {
            "qualified_name": name,
            "node_ids": sorted(node["node_id"] for node in group),
            "reason": "MULTIPLE_DEFINITIONS",
            "confidence": "UNRESOLVED",
        }
        for name, group in sorted(nodes_by_name_groups.items())
        if len(group) > 1
    ]
    modules = {
        node["qualified_name"]: node for node in nodes if node["kind"] == "module"
    }
    edges: list[dict[str, Any]] = []
    unresolved_calls: list[dict[str, Any]] = []
    external_imports: list[dict[str, Any]] = []

    for fragment in fragments:
        artifact = artifacts_by_id[fragment["artifact_id"]]
        for node in fragment["nodes"]:
            parent_name = node["parent_qualified_name"]
            if parent_name and parent_name in nodes_by_name:
                edges.append(
                    _edge(
                        "CONTAINS",
                        nodes_by_name[parent_name]["node_id"],
                        node["node_id"],
                        artifact,
                        node["evidence"]["line_start"],
                    )
                )

        source_module = modules.get(fragment["module"])
        if source_module:
            for item in fragment["imports"]:
                candidates = [item["target"], item["target_module"]]
                target_module = next(
                    (modules[name] for name in candidates if name in modules), None
                )
                if target_module:
                    edges.append(
                        _edge(
                            "IMPORTS",
                            source_module["node_id"],
                            target_module["node_id"],
                            artifact,
                            item["line"],
                        )
                    )
                else:
                    external_imports.append({
                        "source_node_id": source_module["node_id"],
                        "declared_target": item["target_module"] or item["target"],
                        "confidence": "UNRESOLVED",
                        "evidence": _evidence(artifact, item["line"]),
                    })

        for call in fragment["calls"]:
            owner_node = nodes_by_name.get(call["owner"])
            expression = call["expression"]
            target = (
                _resolve_call(expression, call["owner"], fragment, nodes_by_name)
                if expression
                else None
            )
            if owner_node and target:
                edges.append(
                    _edge(
                        "CALLS",
                        owner_node["node_id"],
                        target["node_id"],
                        artifact,
                        call["line"],
                    )
                )
            elif owner_node:
                unresolved_calls.append({
                    "source_node_id": owner_node["node_id"],
                    "expression": expression,
                    "reason": "DYNAMIC_EXPRESSION" if call["dynamic"] else "NO_LOCAL_TARGET",
                    "confidence": "UNRESOLVED",
                    "evidence": _evidence(artifact, call["line"]),
                })

    unique_edges = {item["edge_id"]: item for item in edges}
    edges = sorted(unique_edges.values(), key=lambda item: item["edge_id"])
    unresolved_calls.sort(
        key=lambda item: (
            item["evidence"]["path"], item["evidence"]["line_start"], item["expression"] or ""
        )
    )
    external_imports.sort(
        key=lambda item: (
            item["evidence"]["path"], item["evidence"]["line_start"], item["declared_target"]
        )
    )
    return nodes, edges, unresolved_calls, external_imports, ambiguous_symbols


class PythonAstCodeGraphBackend:
    engine_name = ENGINE_NAME

    def build(
        self,
        source: Path,
        artifacts: list[dict[str, Any]],
        project_id: str,
        max_source_bytes: int,
        previous_graph: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        previous_is_compatible = bool(
            previous_graph
            and previous_graph.get("engine") == self.engine_name
            and previous_graph.get("fragment_schema_version") == FRAGMENT_SCHEMA_VERSION
            and previous_graph.get("project_id") == project_id
            and isinstance(previous_graph.get("fragments"), list)
        )
        previous_fragments = {
            item["path"]: item
            for item in (previous_graph.get("fragments", []) if previous_is_compatible else [])
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        python_artifacts = sorted(
            (
                item for item in artifacts
                if item.get("language") == "Python" and not item.get("redacted")
            ),
            key=lambda item: item["path"],
        )
        current_paths = {item["path"] for item in python_artifacts}
        fragments: list[dict[str, Any]] = []
        skipped_files: list[dict[str, Any]] = []
        parsed_count = 0
        reused_count = 0
        new_artifact_ids: list[str] = []
        changed_artifact_ids: list[str] = []

        for artifact in python_artifacts:
            previous = previous_fragments.get(artifact["path"])
            if artifact["size_bytes"] > max_source_bytes:
                skipped_files.append({
                    "artifact_id": artifact["artifact_id"],
                    "path": artifact["path"],
                    "reason": "SOURCE_SIZE_LIMIT",
                })
                continue
            if not artifact.get("sha256"):
                skipped_files.append({
                    "artifact_id": artifact["artifact_id"],
                    "path": artifact["path"],
                    "reason": "HASH_UNAVAILABLE",
                })
                continue
            if (
                previous
                and previous.get("artifact_id") == artifact["artifact_id"]
                and previous.get("sha256") == artifact["sha256"]
            ):
                fragments.append(previous)
                reused_count += 1
                continue
            fragments.append(_parse_fragment(source, artifact))
            parsed_count += 1
            if previous:
                changed_artifact_ids.append(artifact["artifact_id"])
            else:
                new_artifact_ids.append(artifact["artifact_id"])

        fragments.sort(key=lambda item: item["path"])
        artifacts_by_id = {item["artifact_id"]: item for item in artifacts}
        (
            nodes,
            edges,
            unresolved_calls,
            external_imports,
            ambiguous_symbols,
        ) = _resolve_graph(fragments, artifacts_by_id)
        parse_errors = [
            {
                "artifact_id": fragment["artifact_id"],
                "path": fragment["path"],
                **fragment["parse_error"],
            }
            for fragment in fragments
            if fragment["parse_error"]
        ]

        previous_nodes = {
            item["node_id"]: item
            for item in (previous_graph.get("nodes", []) if previous_is_compatible else [])
            if isinstance(item, dict) and item.get("node_id")
        }
        current_nodes = {item["node_id"]: item for item in nodes}
        stale_node_ids = sorted(
            node_id for node_id in previous_nodes.keys() & current_nodes.keys()
            if previous_nodes[node_id].get("evidence", {}).get("sha256")
            != current_nodes[node_id].get("evidence", {}).get("sha256")
        )
        removed_node_ids = sorted(previous_nodes.keys() - current_nodes.keys())
        removed_paths = sorted(previous_fragments.keys() - current_paths)
        removed_artifact_ids = sorted(
            previous_fragments[path]["artifact_id"] for path in removed_paths
        )
        kind_counts = Counter(node["kind"] for node in nodes)
        edge_counts = Counter(edge["kind"] for edge in edges)

        return {
            "schema_version": "1.0",
            "project_id": project_id,
            "status": "DRAFT_HUMAN_REVIEW",
            "engine": self.engine_name,
            "fragment_schema_version": FRAGMENT_SCHEMA_VERSION,
            "warning": (
                "This graph contains static Python structure only. Unresolved or dynamic calls "
                "are not promoted to confirmed relationships or scientific facts."
            ),
            "scope": {
                "languages": ["Python"],
                "source_execution": False,
                "source_mutated": False,
            },
            "summary": {
                "python_file_count": len(python_artifacts),
                "fragment_count": len(fragments),
                "node_count": len(nodes),
                "edge_count": len(edges),
                "node_kinds": dict(sorted(kind_counts.items())),
                "edge_kinds": dict(sorted(edge_counts.items())),
                "parse_error_count": len(parse_errors),
                "unresolved_call_count": len(unresolved_calls),
                "ambiguous_symbol_count": len(ambiguous_symbols),
            },
            "incremental": {
                "previous_graph_used": previous_is_compatible,
                "parsed_file_count": parsed_count,
                "reused_file_count": reused_count,
                "new_artifact_ids": sorted(new_artifact_ids),
                "changed_artifact_ids": sorted(changed_artifact_ids),
                "removed_artifact_ids": removed_artifact_ids,
                "stale_node_ids": stale_node_ids,
                "removed_node_ids": removed_node_ids,
            },
            "nodes": nodes,
            "edges": edges,
            "unresolved_calls": unresolved_calls,
            "external_imports": external_imports,
            "ambiguous_symbols": ambiguous_symbols,
            "parse_errors": parse_errors,
            "skipped_files": skipped_files,
            "fragments": fragments,
        }


def build_code_graph(
    source: Path,
    artifacts: list[dict[str, Any]],
    project_id: str,
    max_source_bytes: int,
    previous_graph: dict[str, Any] | None = None,
    backend: CodeGraphBackend | None = None,
) -> dict[str, Any]:
    selected = backend or PythonAstCodeGraphBackend()
    return selected.build(
        source=source,
        artifacts=artifacts,
        project_id=project_id,
        max_source_bytes=max_source_bytes,
        previous_graph=previous_graph,
    )
