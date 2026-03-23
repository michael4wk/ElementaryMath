#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


COURSE_CODE_RE = re.compile(r"^(\d+(?:-\d+)+)")
EDITION_MARKERS = {
    "student": ("学生版",),
    "teacher": ("教师版",),
}


@dataclass
class AssetRecord:
    asset_id: str
    file_path: str
    edition: str
    file_name: str
    ext: str
    course_code: str
    title: str
    size_bytes: int
    modified_at: str
    content_sha256: str
    source_priority: int


def load_config(project_root: Path) -> dict:
    config_path = project_root / "config" / "baseline_config.json"
    return json.loads(config_path.read_text(encoding="utf-8"))


def sha256_file(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def stable_asset_id(rel_path: str) -> str:
    digest = hashlib.sha1(rel_path.encode("utf-8")).hexdigest()
    return f"asset_{digest[:16]}"


def detect_edition(file_path: Path) -> str:
    name = file_path.name
    if any(marker in name for marker in EDITION_MARKERS["teacher"]):
        return "teacher"
    if any(marker in name for marker in EDITION_MARKERS["student"]):
        return "student"
    parent = file_path.parent.name
    if any(marker in parent for marker in EDITION_MARKERS["teacher"]):
        return "teacher"
    return "student"


def normalize_title(stem: str) -> str:
    text = stem
    text = re.sub(r"^(\d+(?:-\d+)+)\s*", "", text)
    text = re.sub(r"[.\s]*学生版$", "", text)
    text = re.sub(r"[.\s]*教师版$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_course_code(stem: str) -> str:
    match = COURSE_CODE_RE.match(stem.strip())
    if not match:
        return ""
    return match.group(1)


def list_candidate_files(base_dir: Path, extensions: Iterable[str]) -> List[Path]:
    ext_set = {ext.lower() for ext in extensions}
    files: List[Path] = []
    for path in base_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in ext_set:
            files.append(path)
    return sorted(files)


def build_assets(project_root: Path, config: dict) -> List[AssetRecord]:
    student_dir = project_root / config["student_dir"]
    teacher_dir = project_root / config["teacher_dir"]
    files = list_candidate_files(student_dir, config["extensions"]) + list_candidate_files(
        teacher_dir, config["extensions"]
    )

    assets: List[AssetRecord] = []
    for file_path in files:
        rel_path = file_path.relative_to(project_root).as_posix()
        stat = file_path.stat()
        stem = file_path.stem
        edition = detect_edition(file_path)
        course_code = extract_course_code(stem)
        title = normalize_title(stem)
        assets.append(
            AssetRecord(
                asset_id=stable_asset_id(rel_path),
                file_path=rel_path,
                edition=edition,
                file_name=file_path.name,
                ext=file_path.suffix.lower(),
                course_code=course_code,
                title=title,
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                content_sha256=sha256_file(file_path),
                source_priority=0 if edition == "teacher" else 1,
            )
        )
    return assets


def build_topics_and_issues(assets: List[AssetRecord]) -> Tuple[List[dict], List[dict], dict]:
    issues: List[dict] = []
    by_topic: Dict[str, List[AssetRecord]] = {}
    duplicate_probe: Dict[Tuple[str, str], List[str]] = {}

    for asset in assets:
        topic_key = asset.course_code if asset.course_code else f"title::{asset.title}"
        by_topic.setdefault(topic_key, []).append(asset)
        if asset.course_code:
            duplicate_probe.setdefault((asset.course_code, asset.edition), []).append(asset.asset_id)
        else:
            issues.append(
                {
                    "issue_type": "missing_course_code",
                    "asset_id": asset.asset_id,
                    "file_path": asset.file_path,
                    "title": asset.title,
                }
            )

    for (course_code, edition), asset_ids in duplicate_probe.items():
        if len(asset_ids) > 1:
            issues.append(
                {
                    "issue_type": "duplicate_course_code_in_edition",
                    "course_code": course_code,
                    "edition": edition,
                    "asset_ids": sorted(asset_ids),
                }
            )

    topics: List[dict] = []
    paired_count = 0
    teacher_only = 0
    student_only = 0

    for topic_key, topic_assets in sorted(by_topic.items(), key=lambda x: x[0]):
        teacher_assets = [a for a in topic_assets if a.edition == "teacher"]
        student_assets = [a for a in topic_assets if a.edition == "student"]
        canonical = sorted(topic_assets, key=lambda a: (a.source_priority, a.asset_id))[0]

        if teacher_assets and student_assets:
            pair_status = "paired"
            paired_count += 1
            teacher_title = normalize_title(teacher_assets[0].title)
            student_title = normalize_title(student_assets[0].title)
            if teacher_title != student_title:
                issues.append(
                    {
                        "issue_type": "title_mismatch_between_editions",
                        "topic_key": topic_key,
                        "teacher_title": teacher_title,
                        "student_title": student_title,
                    }
                )
        elif teacher_assets:
            pair_status = "teacher_only"
            teacher_only += 1
            issues.append(
                {
                    "issue_type": "missing_student_edition",
                    "topic_key": topic_key,
                    "teacher_assets": [a.asset_id for a in teacher_assets],
                }
            )
        else:
            pair_status = "student_only"
            student_only += 1
            issues.append(
                {
                    "issue_type": "missing_teacher_edition",
                    "topic_key": topic_key,
                    "student_assets": [a.asset_id for a in student_assets],
                }
            )

        topics.append(
            {
                "topic_key": topic_key,
                "topic_id": topic_key if not topic_key.startswith("title::") else "",
                "title": canonical.title,
                "canonical_edition": canonical.edition,
                "canonical_asset_id": canonical.asset_id,
                "pair_status": pair_status,
                "teacher_asset_ids": [a.asset_id for a in sorted(teacher_assets, key=lambda x: x.asset_id)],
                "student_asset_ids": [a.asset_id for a in sorted(student_assets, key=lambda x: x.asset_id)],
            }
        )

    summary = {
        "total_assets": len(assets),
        "teacher_assets": sum(1 for a in assets if a.edition == "teacher"),
        "student_assets": sum(1 for a in assets if a.edition == "student"),
        "total_topics": len(topics),
        "paired_topics": paired_count,
        "teacher_only_topics": teacher_only,
        "student_only_topics": student_only,
        "issue_count": len(issues),
    }
    return topics, issues, summary


def write_jsonl(file_path: Path, rows: Iterable[dict]) -> None:
    with file_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    config = load_config(project_root)
    output_dir = project_root / config["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    assets = build_assets(project_root, config)
    topics, issues, summary = build_topics_and_issues(assets)

    write_jsonl(output_dir / "assets.jsonl", (asdict(asset) for asset in assets))
    write_jsonl(output_dir / "topics.jsonl", topics)
    write_jsonl(output_dir / "issues.jsonl", issues)
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
