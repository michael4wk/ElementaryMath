#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List


def read_assets(path: Path) -> List[dict]:
    rows: List[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def convert_with_textutil(input_path: Path, output_path: Path) -> tuple[bool, str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["textutil", "-convert", "txt", "-output", str(output_path), str(input_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return True, ""
    err = (result.stderr or result.stdout).strip()
    return False, err


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    assets_path = project_root / "artifacts" / "baseline" / "assets.jsonl"
    out_dir = project_root / "artifacts" / "normalized"
    out_dir.mkdir(parents=True, exist_ok=True)

    assets = read_assets(assets_path)
    if args.limit > 0:
        assets = assets[: args.limit]

    extraction_rows: List[dict] = []
    failed_rows: List[dict] = []
    retry_rows: List[dict] = []
    success = 0
    failed = 0

    for asset in assets:
        input_path = project_root / asset["file_path"]
        output_path = out_dir / f'{asset["asset_id"]}.txt'
        ok, error_message = convert_with_textutil(input_path, output_path)
        if ok:
            success += 1
        else:
            failed += 1
            failed_item = {
                "asset_id": asset["asset_id"],
                "file_path": asset["file_path"],
                "edition": asset["edition"],
                "topic_code": asset["course_code"],
                "output_text_path": output_path.relative_to(project_root).as_posix(),
                "extract_status": "failed",
                "error_message": error_message,
                "first_failed_at": datetime.now(timezone.utc).isoformat(),
            }
            failed_rows.append(failed_item)
            retry_rows.append(
                {
                    **failed_item,
                    "retry_attempts": 0,
                    "max_retry_attempts": 3,
                    "next_retry_after": datetime.now(timezone.utc).isoformat(),
                    "queue_status": "pending",
                }
            )
        extraction_rows.append(
            {
                "asset_id": asset["asset_id"],
                "file_path": asset["file_path"],
                "edition": asset["edition"],
                "topic_code": asset["course_code"],
                "output_text_path": output_path.relative_to(project_root).as_posix(),
                "extract_status": "success" if ok else "failed",
                "error_message": error_message,
            }
        )

    write_jsonl(out_dir / "extract_status.jsonl", extraction_rows)
    quarantine_dir = out_dir / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(quarantine_dir / "failed_assets.jsonl", failed_rows)
    write_jsonl(quarantine_dir / "retry_queue.jsonl", retry_rows)
    summary = {
        "total_attempted": len(assets),
        "success_count": success,
        "failed_count": failed,
        "failed_quarantine_count": len(failed_rows),
        "retry_queue_pending_count": len(retry_rows),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
