#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    parser.add_argument("--mode", choices=["backup", "restore"], default="backup")
    parser.add_argument("--name", type=str, default="")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    artifacts_dir = root / "artifacts"
    backups_dir = root / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "backup":
        name = args.name.strip() or datetime.now(timezone.utc).strftime("artifacts_%Y%m%dT%H%M%SZ")
        target = backups_dir / name
        target.mkdir(parents=True, exist_ok=True)
        copy_tree(artifacts_dir, target / "artifacts")
        manifest = {
            "name": name,
            "mode": "backup",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": str(artifacts_dir),
            "target": str((target / "artifacts").resolve()),
        }
        (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "backup_name": name}, ensure_ascii=False))
        return

    name = args.name.strip()
    if not name:
        print(json.dumps({"ok": False, "error": "restore mode requires --name"}, ensure_ascii=False))
        raise SystemExit(2)
    source = backups_dir / name / "artifacts"
    if not source.exists():
        print(json.dumps({"ok": False, "error": "backup not found"}, ensure_ascii=False))
        raise SystemExit(2)
    copy_tree(source, artifacts_dir)
    print(json.dumps({"ok": True, "restored_from": name}, ensure_ascii=False))


if __name__ == "__main__":
    main()
