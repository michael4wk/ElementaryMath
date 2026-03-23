#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    parser.add_argument("--commit-snapshot", action="store_true")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    baseline_assets = read_jsonl(project_root / "artifacts" / "baseline" / "assets.jsonl")
    state_dir = project_root / "artifacts" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    previous_path = state_dir / "asset_hashes.json"
    current_snapshot = {a["asset_id"]: {"sha256": a["content_sha256"], "file_path": a["file_path"]} for a in baseline_assets}

    if previous_path.exists():
        previous_snapshot: Dict[str, dict] = json.loads(previous_path.read_text(encoding="utf-8"))
    else:
        previous_snapshot = {}

    changes: List[dict] = []
    for asset_id, cur in current_snapshot.items():
        prev = previous_snapshot.get(asset_id)
        if prev is None:
            changes.append({"change_type": "added", "asset_id": asset_id, "file_path": cur["file_path"]})
        elif prev["sha256"] != cur["sha256"]:
            changes.append({"change_type": "modified", "asset_id": asset_id, "file_path": cur["file_path"]})

    for asset_id, prev in previous_snapshot.items():
        if asset_id not in current_snapshot:
            changes.append({"change_type": "deleted", "asset_id": asset_id, "file_path": prev["file_path"]})

    out_dir = project_root / "artifacts" / "changes"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "asset_changes.jsonl", changes)
    summary = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "total_current_assets": len(current_snapshot),
        "change_count": len(changes),
        "added": sum(1 for c in changes if c["change_type"] == "added"),
        "modified": sum(1 for c in changes if c["change_type"] == "modified"),
        "deleted": sum(1 for c in changes if c["change_type"] == "deleted"),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.commit_snapshot:
        previous_path.write_text(json.dumps(current_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
