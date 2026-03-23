#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple


def read_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_topic_id(topic_id: str) -> List[int]:
    parts = []
    for p in topic_id.split("-"):
        if p.isdigit():
            parts.append(int(p))
        else:
            return []
    return parts


def build_base_incoming(topic_ids: List[str]) -> Dict[str, Set[str]]:
    id_set = set(topic_ids)
    incoming: Dict[str, Set[str]] = {tid: set() for tid in topic_ids}

    for tid in topic_ids:
        parts = parse_topic_id(tid)
        if not parts:
            continue
        if parts[-1] > 1:
            candidate = "-".join(str(x) for x in (parts[:-1] + [parts[-1] - 1]))
            if candidate in id_set:
                incoming[tid].add(candidate)
        if len(parts) >= 2 and parts[-2] > 1:
            parent_prev = "-".join(str(x) for x in (parts[:-2] + [parts[-2] - 1, 1]))
            if parent_prev in id_set:
                incoming[tid].add(parent_prev)
    return incoming


def apply_topic_overrides(
    incoming: Dict[str, Set[str]], topic_ids: Set[str], override_map: Dict[str, List[str]]
) -> Tuple[Dict[str, Set[str]], List[dict]]:
    errors: List[dict] = []
    for topic_id, pre_list in override_map.items():
        if topic_id not in topic_ids:
            errors.append({"type": "override_topic_not_found", "topic_id": topic_id})
            continue
        fixed: Set[str] = set()
        for p in pre_list:
            if p == topic_id:
                errors.append({"type": "self_dependency", "topic_id": topic_id, "prerequisite": p})
                continue
            if p not in topic_ids:
                errors.append({"type": "override_prerequisite_not_found", "topic_id": topic_id, "prerequisite": p})
                continue
            fixed.add(p)
        incoming[topic_id] = fixed
    return incoming, errors


def incoming_to_rows(incoming: Dict[str, Set[str]]) -> List[dict]:
    outgoing: Dict[str, Set[str]] = {k: set() for k in incoming.keys()}
    for tid, prereqs in incoming.items():
        for pre in prereqs:
            outgoing.setdefault(pre, set()).add(tid)
    rows: List[dict] = []
    for tid in sorted(incoming.keys()):
        rows.append(
            {
                "topic_id": tid,
                "prerequisites": sorted(incoming[tid]),
                "next_topics": sorted(outgoing.get(tid, set())),
            }
        )
    return rows


def build_graph_rows(topics: List[dict], override_map: Dict[str, List[str]]) -> Tuple[List[dict], List[dict]]:
    topic_ids = sorted([t.get("topic_id", "") for t in topics if t.get("topic_id")])
    incoming = build_base_incoming(topic_ids)
    incoming, errors = apply_topic_overrides(incoming, set(topic_ids), override_map)
    rows = incoming_to_rows(incoming)
    return rows, errors


def topic_to_chapter(topic_id: str) -> str:
    parts = topic_id.split("-")
    if len(parts) < 2:
        return topic_id
    return f"{parts[0]}-{parts[1]}"


def build_chapter_rows(topic_rows: List[dict], chapter_override_map: Dict[str, List[str]]) -> Tuple[List[dict], List[dict]]:
    chapter_nodes: Dict[str, dict] = {}
    chapter_out: Dict[str, Set[str]] = {}
    chapter_in: Dict[str, Set[str]] = {}

    for row in topic_rows:
        topic_id = row["topic_id"]
        chapter_id = topic_to_chapter(topic_id)
        chapter_nodes.setdefault(chapter_id, {"chapter_id": chapter_id, "topic_ids": []})
        chapter_nodes[chapter_id]["topic_ids"].append(topic_id)
        chapter_out.setdefault(chapter_id, set())
        chapter_in.setdefault(chapter_id, set())

    for row in topic_rows:
        cur_ch = topic_to_chapter(row["topic_id"])
        for nxt in row.get("next_topics", []):
            nxt_ch = topic_to_chapter(nxt)
            if nxt_ch != cur_ch:
                chapter_out[cur_ch].add(nxt_ch)
                chapter_in[nxt_ch].add(cur_ch)

    errors: List[dict] = []
    chapter_ids = set(chapter_nodes.keys())
    for chapter_id, pre_list in chapter_override_map.items():
        if chapter_id not in chapter_ids:
            errors.append({"type": "override_chapter_not_found", "chapter_id": chapter_id})
            continue
        fixed: Set[str] = set()
        for p in pre_list:
            if p == chapter_id:
                errors.append({"type": "chapter_self_dependency", "chapter_id": chapter_id, "prerequisite_chapter": p})
                continue
            if p not in chapter_ids:
                errors.append({"type": "override_chapter_prerequisite_not_found", "chapter_id": chapter_id, "prerequisite_chapter": p})
                continue
            fixed.add(p)
        chapter_in[chapter_id] = fixed

    chapter_out = {k: set() for k in chapter_ids}
    for ch, pres in chapter_in.items():
        for pre in pres:
            chapter_out[pre].add(ch)

    rows: List[dict] = []
    for chapter_id in sorted(chapter_nodes.keys()):
        rows.append(
            {
                "chapter_id": chapter_id,
                "topic_count": len(chapter_nodes[chapter_id]["topic_ids"]),
                "topic_ids": sorted(chapter_nodes[chapter_id]["topic_ids"]),
                "prerequisite_chapters": sorted(chapter_in.get(chapter_id, set())),
                "next_chapters": sorted(chapter_out.get(chapter_id, set())),
            }
        )
    return rows, errors


def has_cycle(rows: List[dict], id_key: str, pre_key: str) -> bool:
    ids = [r[id_key] for r in rows]
    in_deg = {k: 0 for k in ids}
    out_map = defaultdict(list)
    for r in rows:
        cur = r[id_key]
        for pre in r.get(pre_key, []):
            out_map[pre].append(cur)
            in_deg[cur] = in_deg.get(cur, 0) + 1
    q = deque([k for k in ids if in_deg.get(k, 0) == 0])
    seen = 0
    while q:
        x = q.popleft()
        seen += 1
        for y in out_map.get(x, []):
            in_deg[y] -= 1
            if in_deg[y] == 0:
                q.append(y)
    return seen != len(ids)


def build_validation_report(topic_rows: List[dict], chapter_rows: List[dict], override_errors: List[dict]) -> dict:
    isolated_topic_count = sum(1 for r in topic_rows if not r.get("prerequisites") and not r.get("next_topics"))
    isolated_chapter_count = sum(
        1 for r in chapter_rows if not r.get("prerequisite_chapters") and not r.get("next_chapters")
    )
    return {
        "topic_cycle_detected": has_cycle(topic_rows, "topic_id", "prerequisites"),
        "chapter_cycle_detected": has_cycle(chapter_rows, "chapter_id", "prerequisite_chapters"),
        "isolated_topic_count": isolated_topic_count,
        "isolated_chapter_count": isolated_chapter_count,
        "override_error_count": len(override_errors),
        "override_errors": override_errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    topics = read_jsonl(project_root / "artifacts" / "curated" / "topics.jsonl")
    override_conf = read_json(project_root / "config" / "prerequisite_overrides.json")
    topic_override_map = override_conf.get("topic_prerequisites", {})
    chapter_override_map = override_conf.get("chapter_prerequisites", {})
    graph_rows, topic_override_errors = build_graph_rows(topics, topic_override_map)
    chapter_rows, chapter_override_errors = build_chapter_rows(graph_rows, chapter_override_map)
    override_errors = topic_override_errors + chapter_override_errors
    validation = build_validation_report(graph_rows, chapter_rows, override_errors)
    out_dir = project_root / "artifacts" / "graph"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "topic_graph.jsonl", graph_rows)
    write_jsonl(out_dir / "chapter_graph.jsonl", chapter_rows)
    (out_dir / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "topic_count": len(graph_rows),
        "edge_count": sum(len(r["prerequisites"]) for r in graph_rows),
        "chapter_count": len(chapter_rows),
        "chapter_edge_count": sum(len(r["prerequisite_chapters"]) for r in chapter_rows),
        "override_error_count": len(override_errors),
        "topic_cycle_detected": validation["topic_cycle_detected"],
        "chapter_cycle_detected": validation["chapter_cycle_detected"],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
