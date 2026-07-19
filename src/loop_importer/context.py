from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


TOKEN_PATTERN = re.compile(r"[a-z0-9_./-]+|[\u4e00-\u9fff]", re.IGNORECASE)


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for token in TOKEN_PATTERN.findall(value):
        lowered = token.lower()
        tokens.add(lowered)
        tokens.update(part for part in re.split(r"[./_-]+", lowered) if part)
    return tokens


def _evidence_snapshot(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": artifact["artifact_id"],
        "path": artifact["path"],
        "sha256": artifact.get("sha256"),
    }


def _fact_validity(
    evidence: list[dict[str, Any]], artifacts_by_id: dict[str, dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    if not evidence:
        return "UNVERIFIED", []
    invalidations: list[dict[str, Any]] = []
    unverifiable = False
    for snapshot in evidence:
        artifact_id = snapshot.get("artifact_id")
        current = artifacts_by_id.get(artifact_id)
        if current is None:
            invalidations.append({
                "artifact_id": artifact_id,
                "reason": "EVIDENCE_MISSING",
                "expected_sha256": snapshot.get("sha256"),
                "current_sha256": None,
            })
            continue
        expected = snapshot.get("sha256")
        observed = current.get("sha256")
        if not expected or not observed:
            unverifiable = True
        elif expected != observed:
            invalidations.append({
                "artifact_id": artifact_id,
                "reason": "EVIDENCE_CHANGED",
                "expected_sha256": expected,
                "current_sha256": observed,
            })
    if invalidations:
        return "STALE", invalidations
    if unverifiable:
        return "UNVERIFIED", []
    return "CURRENT", []


def build_knowledge_baseline(
    project_id: str,
    artifacts: list[dict[str, Any]],
    task_candidates: list[dict[str, Any]],
    previous_baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic knowledge index and refresh human fact validity."""
    artifacts_by_id = {item["artifact_id"]: item for item in artifacts}
    artifact_snapshot = [
        _evidence_snapshot(item) for item in sorted(artifacts, key=lambda item: item["path"])
    ]
    artifact_snapshot_digest = _digest(artifact_snapshot)
    facts: list[dict[str, Any]] = []
    invalidations: list[dict[str, Any]] = []

    for task in sorted(task_candidates, key=lambda item: item["task_id"]):
        evidence = [
            _evidence_snapshot(artifacts_by_id[artifact_id])
            for artifact_id in task.get("evidence", [])
            if artifact_id in artifacts_by_id
        ]
        validity, _ = _fact_validity(evidence, artifacts_by_id)
        facts.append({
            "fact_id": _stable_id("KBF", f"task:{task['task_id']}"),
            "kind": "task_candidate",
            "statement": (
                f"{task['kind']} may enter through {task['entrypoint']}; "
                "this is a structural candidate, not a confirmed workflow fact."
            ),
            "value": {
                "task_id": task["task_id"],
                "kind": task["kind"],
                "entrypoint": task["entrypoint"],
                "depends_on_candidates": task.get("depends_on_candidates", []),
            },
            "topics": sorted(_tokens(f"{task['kind']} {task['entrypoint']}")),
            "epistemic_status": "INFERRED",
            "validity": validity,
            "origin": "IMPORTER",
            "evidence": evidence,
            "requires_human_review": True,
        })

    previous_is_compatible = bool(
        previous_baseline
        and previous_baseline.get("schema_version") == "1.0"
        and previous_baseline.get("project_id") == project_id
    )
    if previous_is_compatible:
        for previous in previous_baseline.get("facts", []):
            if previous.get("origin") != "HUMAN" or not previous.get("fact_id"):
                continue
            fact = deepcopy(previous)
            validity, reasons = _fact_validity(fact.get("evidence", []), artifacts_by_id)
            fact["validity"] = validity
            fact["requires_human_review"] = validity != "CURRENT"
            facts.append(fact)
            for reason in reasons:
                invalidations.append({"fact_id": fact["fact_id"], **reason})

    facts.sort(key=lambda item: item["fact_id"])
    fact_counts: dict[str, int] = {}
    for fact in facts:
        validity = fact["validity"]
        fact_counts[validity] = fact_counts.get(validity, 0) + 1
    baseline_identity = {
        "project_id": project_id,
        "artifact_snapshot_digest": artifact_snapshot_digest,
        "facts": facts,
    }
    baseline_digest = _digest(baseline_identity)
    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "status": "DRAFT_HUMAN_REVIEW",
        "baseline_id": _stable_id("KB", f"{project_id}:{artifact_snapshot_digest}"),
        "baseline_digest": baseline_digest,
        "artifact_snapshot_digest": artifact_snapshot_digest,
        "previous_baseline_used": previous_is_compatible,
        "warning": (
            "Only CURRENT facts may enter a context bundle. STALE and UNVERIFIED facts "
            "require evidence refresh or human review."
        ),
        "summary": {
            "fact_count": len(facts),
            "validity": dict(sorted(fact_counts.items())),
            "invalidation_count": len(invalidations),
        },
        "facts": facts,
        "invalidations": sorted(
            invalidations,
            key=lambda item: (item["fact_id"], item.get("artifact_id") or ""),
        ),
    }


def _fact_score(fact: dict[str, Any], query_tokens: set[str]) -> tuple[int, int]:
    searchable = " ".join([
        str(fact.get("kind", "")),
        str(fact.get("statement", "")),
        " ".join(str(item) for item in fact.get("topics", [])),
        json.dumps(fact.get("value"), ensure_ascii=False, sort_keys=True),
    ])
    overlap = len(query_tokens & _tokens(searchable))
    human_weight = 1 if fact.get("epistemic_status") == "HUMAN_CONFIRMED" else 0
    return overlap, human_weight


def _node_score(node: dict[str, Any], query_tokens: set[str]) -> int:
    evidence = node.get("evidence", {})
    searchable = " ".join([
        str(node.get("kind", "")),
        str(node.get("qualified_name", "")),
        str(evidence.get("path", "")),
    ])
    return len(query_tokens & _tokens(searchable))


def _payload_size(payload: dict[str, Any]) -> int:
    return len(_canonical_bytes(payload))


def build_context_bundle(
    baseline: dict[str, Any],
    code_graph: dict[str, Any],
    query: str,
    max_payload_bytes: int = 8_192,
    max_graph_nodes: int = 40,
) -> dict[str, Any]:
    """Select a deterministic, evidence-safe context payload for one task."""
    if max_payload_bytes < 512:
        raise ValueError("max_payload_bytes must be at least 512")
    if max_graph_nodes < 0:
        raise ValueError("max_graph_nodes must be non-negative")
    query_tokens = _tokens(query)
    stale_fact_ids = sorted(
        fact["fact_id"] for fact in baseline.get("facts", [])
        if fact.get("validity") == "STALE"
    )
    unverified_fact_ids = sorted(
        fact["fact_id"] for fact in baseline.get("facts", [])
        if fact.get("validity") == "UNVERIFIED"
    )
    payload: dict[str, Any] = {
        "project_id": baseline["project_id"],
        "baseline_id": baseline["baseline_id"],
        "baseline_digest": baseline["baseline_digest"],
        "query": query,
        "facts": [],
        "code_nodes": [],
        "code_edges": [],
        "warnings": {
            "stale_fact_count": len(stale_fact_ids),
            "stale_fact_ids": stale_fact_ids[:20],
            "stale_fact_ids_truncated": len(stale_fact_ids) > 20,
            "unverified_fact_count": len(unverified_fact_ids),
            "unverified_fact_ids": unverified_fact_ids[:20],
            "unverified_fact_ids_truncated": len(unverified_fact_ids) > 20,
        },
    }
    if _payload_size(payload) > max_payload_bytes:
        raise ValueError("query and mandatory context metadata exceed max_payload_bytes")

    fact_candidates = []
    for fact in baseline.get("facts", []):
        if fact.get("validity") != "CURRENT":
            continue
        score = _fact_score(fact, query_tokens)
        if score[0] > 0:
            fact_candidates.append((score, fact))
    fact_candidates.sort(
        key=lambda item: (-item[0][0], -item[0][1], item[1]["fact_id"])
    )
    for _, fact in fact_candidates:
        payload["facts"].append(fact)
        if _payload_size(payload) > max_payload_bytes:
            payload["facts"].pop()

    node_candidates = []
    for node in code_graph.get("nodes", []):
        score = _node_score(node, query_tokens)
        if score > 0:
            node_candidates.append((score, node))
    node_candidates.sort(key=lambda item: (-item[0], item[1]["node_id"]))
    for _, node in node_candidates[:max_graph_nodes]:
        payload["code_nodes"].append(node)
        if _payload_size(payload) > max_payload_bytes:
            payload["code_nodes"].pop()

    selected_node_ids = {node["node_id"] for node in payload["code_nodes"]}
    for edge in sorted(code_graph.get("edges", []), key=lambda item: item["edge_id"]):
        if (
            edge.get("source_node_id") not in selected_node_ids
            or edge.get("target_node_id") not in selected_node_ids
        ):
            continue
        payload["code_edges"].append(edge)
        if _payload_size(payload) > max_payload_bytes:
            payload["code_edges"].pop()

    payload_bytes = _payload_size(payload)
    digest = _digest(payload)
    return {
        "schema_version": "1.0",
        "status": "DRAFT_HUMAN_REVIEW",
        "selection_policy": "LEXICAL_RELEVANCE_EVIDENCE_SAFE_V1",
        "max_payload_bytes": max_payload_bytes,
        "payload_bytes": payload_bytes,
        "bundle_digest": digest,
        "selected": {
            "fact_count": len(payload["facts"]),
            "code_node_count": len(payload["code_nodes"]),
            "code_edge_count": len(payload["code_edges"]),
        },
        "excluded": {
            "stale_fact_count": len(stale_fact_ids),
            "unverified_fact_count": len(unverified_fact_ids),
        },
        "payload": payload,
    }


def load_packet_context(
    packet: str | Path,
    query: str,
    max_payload_bytes: int = 8_192,
    max_graph_nodes: int = 40,
) -> dict[str, Any]:
    import yaml

    root = Path(packet)
    baseline = yaml.safe_load((root / "knowledge-baseline.yaml").read_text(encoding="utf-8"))
    graph = json.loads((root / "code-graph.json").read_text(encoding="utf-8"))
    return build_context_bundle(
        baseline=baseline,
        code_graph=graph,
        query=query,
        max_payload_bytes=max_payload_bytes,
        max_graph_nodes=max_graph_nodes,
    )
