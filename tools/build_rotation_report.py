#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def key_id(key: str) -> str:
    if not key:
        return ""
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return f"key_{digest}"


def read_tail_json_lines(path: Path, limit: int = 3000) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    rows: list[dict] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
        except Exception:
            continue
    return rows


def recent_consecutive_ok(rows: list[dict]) -> int:
    n = 0
    for row in reversed(rows):
        if bool(row.get("ok", False)):
            n += 1
        else:
            break
    return n


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    conf = read_json(root / "config" / "security_config.json")
    gate_conf = conf.get("rotation_gate", {})
    access_rows = read_tail_json_lines(root / "artifacts" / "ops" / "access.log", 3000)
    health_rows = read_tail_json_lines(root / "artifacts" / "ops" / "health_history.jsonl", 1000)
    min_consecutive_ok = int(gate_conf.get("min_consecutive_ok", 2) or 2)
    consecutive_ok = recent_consecutive_ok(health_rows)
    groups = conf.get("rotation_groups", [])
    report_rows = []
    for g in groups:
        phase = str(g.get("phase", "dual")).strip() or "dual"
        old_expected = 200 if phase == "dual" else 401
        old_key = str(g.get("old_key", "")).strip()
        new_key = str(g.get("new_key", "")).strip()
        old_id = key_id(old_key)
        new_id = key_id(new_key)
        old_ok = sum(1 for r in access_rows if r.get("api_key_id") == old_id and int(r.get("status", 0)) < 400)
        new_ok = sum(1 for r in access_rows if r.get("api_key_id") == new_id and int(r.get("status", 0)) < 400)
        old_blocked = sum(
            1
            for r in access_rows
            if r.get("api_key_id") == old_id and int(r.get("status", 0)) == 401 and r.get("auth_reason") in ("key_rotated_out", "key_retired")
        )
        suggestion = "monitor"
        if phase == "dual" and new_ok >= 1:
            suggestion = "can_cutover"
        elif phase == "cutover" and old_blocked >= 1 and new_ok >= 1:
            suggestion = "can_retire"
        elif phase == "retire":
            suggestion = "stable"
        target_phase = phase
        if phase == "dual" and suggestion == "can_cutover":
            target_phase = "cutover"
        elif phase == "cutover" and suggestion == "can_retire":
            target_phase = "retire"
        gate_passed = consecutive_ok >= min_consecutive_ok
        row = {
            "name": str(g.get("name", "")).strip(),
            "old_key": old_key,
            "new_key": new_key,
            "phase": phase,
            "old_key_expected_status": old_expected,
            "new_key_expected_status": 200,
            "old_key_id": old_id,
            "new_key_id": new_id,
            "old_success_count": old_ok,
            "new_success_count": new_ok,
            "old_blocked_count": old_blocked,
            "suggestion": suggestion,
            "target_phase": target_phase,
            "eligible": bool(gate_passed and target_phase != phase),
        }
        report_rows.append(row)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "group_count": len(report_rows),
        "gate": {
            "min_consecutive_ok": min_consecutive_ok,
            "recent_consecutive_ok": consecutive_ok,
            "gate_passed": consecutive_ok >= min_consecutive_ok,
        },
        "groups": report_rows,
    }
    out_dir = root / "artifacts" / "ops"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rotation_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 密钥轮换状态报告", "", f"- 轮换组数量: {len(report_rows)}", ""]
    lines.append(f"- 闸门检查: {consecutive_ok}/{min_consecutive_ok} consecutive ok")
    lines.append("")
    for r in report_rows:
        lines.append(
            f"- {r['name']}: phase={r['phase']}, old->{r['old_key_expected_status']}, new->{r['new_key_expected_status']}, suggestion={r['suggestion']}, target={r['target_phase']}, eligible={r['eligible']}"
        )
    (out_dir / "rotation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"group_count": len(report_rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
