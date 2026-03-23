#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List


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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def convert_with_textutil(input_path: Path, output_path: Path) -> tuple[bool, str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["textutil", "-convert", "txt", "-output", str(output_path), str(input_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return True, ""
    err = (result.stderr or result.stdout).strip()
    return False, err


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    norm_dir = root / "artifacts" / "normalized"
    queue_path = norm_dir / "quarantine" / "retry_queue.jsonl"
    queue = read_jsonl(queue_path)
    pending = [x for x in queue if str(x.get("queue_status", "")).strip() == "pending"]
    if args.limit > 0:
        pending = pending[: args.limit]

    retried = 0
    succeeded = 0
    exhausted = 0
    for item in queue:
        if item not in pending:
            continue
        retried += 1
        file_path = str(item.get("file_path", "")).strip()
        output_text_path = str(item.get("output_text_path", "")).strip()
        input_path = root / file_path
        output_path = root / output_text_path
        ok, err = convert_with_textutil(input_path, output_path)
        attempts = int(item.get("retry_attempts", 0) or 0) + 1
        item["retry_attempts"] = attempts
        item["last_retry_at"] = datetime.now(timezone.utc).isoformat()
        item["last_error_message"] = err
        if ok:
            item["queue_status"] = "resolved"
            succeeded += 1
        else:
            max_attempts = int(item.get("max_retry_attempts", 3) or 3)
            if attempts >= max_attempts:
                item["queue_status"] = "exhausted"
                exhausted += 1
            else:
                item["queue_status"] = "pending"

    write_jsonl(queue_path, queue)
    summary = {
        "queue_total": len(queue),
        "retried_count": retried,
        "resolved_count": len([x for x in queue if str(x.get("queue_status", "")).strip() == "resolved"]),
        "pending_count": len([x for x in queue if str(x.get("queue_status", "")).strip() == "pending"]),
        "exhausted_count": len([x for x in queue if str(x.get("queue_status", "")).strip() == "exhausted"]),
        "succeeded_this_run": succeeded,
        "exhausted_this_run": exhausted,
    }
    (norm_dir / "quarantine" / "retry_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
