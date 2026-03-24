#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


SHAPE_RE = re.compile(r"SHAPE \\* MERGEFORMAT")
FORMULA_RE = re.compile(r"EMBED Equation\.DSMT4")
PROBLEM_START_RE = re.compile(r"^(计算[：:]|求[：:]|解[：:]|应用题[：:]|如图|已知|设)")
TAG_RE = re.compile(r"【([^】]+)】\s*([^【]*)")
DIFFICULTY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*星")
GRADE_RE = re.compile(r"([1-6一二三四五六])\s*年级")
ANALYSIS_HINT_RE = re.compile(r"(原式|解|步骤|思路|所以|因此|可得|设|则|=|答：)")
STAR_RE = re.compile(r"[★☆⭐]")


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


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def clean_line(line: str) -> str:
    text = SHAPE_RE.sub("", line).replace("\u2028", " ").replace("\ufeff", "")
    text = FORMULA_RE.sub("【公式】", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_inputs(project_root: Path) -> Tuple[List[dict], Dict[str, dict], Dict[str, dict]]:
    baseline_dir = project_root / "artifacts" / "baseline"
    normalized_dir = project_root / "artifacts" / "normalized"
    topics = read_jsonl(baseline_dir / "topics.jsonl")
    assets = {row["asset_id"]: row for row in read_jsonl(baseline_dir / "assets.jsonl")}
    status = {row["asset_id"]: row for row in read_jsonl(normalized_dir / "extract_status.jsonl")}
    return topics, assets, status


def pick_canonical_asset(topic: dict) -> str:
    teacher_assets = topic.get("teacher_asset_ids", [])
    student_assets = topic.get("student_asset_ids", [])
    if teacher_assets:
        return teacher_assets[0]
    if student_assets:
        return student_assets[0]
    return ""


def parse_text(file_path: Path) -> List[str]:
    if not file_path.exists():
        return []
    lines: List[str] = []
    with file_path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = clean_line(raw)
            if line:
                lines.append(line)
    return lines


def extract_topic_summary(lines: List[str]) -> str:
    candidates = [line for line in lines if len(line) >= 16 and "【" not in line]
    if not candidates:
        return ""
    return candidates[0][:240]


def extract_learning_fields(lines: List[str]) -> Tuple[List[str], List[str]]:
    learning_objectives: List[str] = []
    common_mistakes: List[str] = []
    objective_hints = ("本讲", "本节", "本课", "目标", "掌握", "理解", "能够", "学会", "要求")
    mistake_hints = ("注意", "易错", "误区", "错误", "陷阱")
    for line in lines:
        if any(h in line for h in objective_hints) and len(line) > 10:
            learning_objectives.append(line[:120])
        if "培养" in line and len(line) > 10:
            learning_objectives.append(line[:120])
        if any(h in line for h in mistake_hints) and len(line) > 8:
            common_mistakes.append(line[:120])
        if len(learning_objectives) >= 5 and len(common_mistakes) >= 5:
            break
    return sorted(set(learning_objectives))[:5], sorted(set(common_mistakes))[:5]


def split_problem_blocks(lines: List[str]) -> List[List[str]]:
    blocks: List[List[str]] = []
    current: List[str] = []
    for line in lines:
        if PROBLEM_START_RE.match(line):
            if current:
                blocks.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def parse_tags(text: str) -> Dict[str, str]:
    tags: Dict[str, str] = {}
    for key, value in TAG_RE.findall(text):
        tags[key.strip()] = value.strip()
    return tags


def build_fallback_analysis(block: List[str]) -> List[str]:
    rows: List[str] = []
    for line in block[1:]:
        if line.startswith("【"):
            continue
        if "【答案】" in line:
            continue
        if ANALYSIS_HINT_RE.search(line):
            rows.append(line[:240])
        if len(rows) >= 10:
            break
    return rows


def build_answer_backfill(answer: str) -> List[str]:
    text = (answer or "").strip()
    if not text:
        return []
    if text == "【公式】":
        return ["根据题目条件代入并化简，得到结果见答案。"]
    return [f"根据题目条件代入并逐步计算，可得答案：{text}"]


def normalize_grade(grade_token: str) -> str:
    mapping = {
        "一": "1",
        "二": "2",
        "三": "3",
        "四": "4",
        "五": "5",
        "六": "6",
    }
    if grade_token.isdigit():
        return grade_token
    return mapping.get(grade_token, "")


def extract_grade_band(*texts: str) -> str:
    for text in texts:
        if not text:
            continue
        match = GRADE_RE.search(text)
        if match:
            return normalize_grade(match.group(1))
    return ""


def extract_difficulty(*texts: str) -> str:
    for text in texts:
        if not text:
            continue
        m = DIFFICULTY_RE.search(text)
        if m:
            return m.group(1)
        stars = len(STAR_RE.findall(text))
        if stars > 0:
            return str(stars)
    return ""


def enrich_problem_fields(problem_rows: List[dict]) -> List[dict]:
    by_topic: Dict[str, List[dict]] = defaultdict(list)
    for row in problem_rows:
        by_topic[row.get("topic_id", "")].append(row)

    for _, rows in by_topic.items():
        grade_counter = Counter([r.get("grade_band", "") for r in rows if r.get("grade_band", "")])
        difficulty_counter = Counter([r.get("difficulty", "") for r in rows if r.get("difficulty", "")])
        topic_grade = grade_counter.most_common(1)[0][0] if grade_counter else ""
        topic_difficulty = difficulty_counter.most_common(1)[0][0] if difficulty_counter else ""

        for r in rows:
            if not r.get("grade_band") and topic_grade:
                r["grade_band"] = topic_grade
                r["grade_source"] = "topic_mode"
            elif r.get("grade_band"):
                r["grade_source"] = "direct"
            else:
                r["grade_source"] = "none"

            if not r.get("difficulty") and topic_difficulty:
                r["difficulty"] = topic_difficulty
                r["difficulty_source"] = "topic_mode"
            elif r.get("difficulty"):
                r["difficulty_source"] = "direct"
            else:
                r["difficulty_source"] = "none"
    return problem_rows


def infer_method_tags_from_title(title: str) -> List[str]:
    title = (title or "").strip()
    if not title:
        return []
    splitters = r"[、，,与及和]"
    if "之" in title:
        left, right = title.split("之", 1)
        candidates = [left.strip(), right.strip()]
    else:
        candidates = re.split(splitters, title)
    tags = [t.strip() for t in candidates if t.strip()]
    if not tags:
        tags = [title]
    return tags[:3]


def infer_common_mistakes(topic_title: str, method_tags: List[str], template_conf: dict) -> List[str]:
    rows = template_conf.get("keyword_templates", []) if isinstance(template_conf, dict) else []
    search_text = " ".join([topic_title] + method_tags)
    matched: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        keyword = str(row.get("keyword", "")).strip()
        mistakes = row.get("mistakes", [])
        if not keyword or not isinstance(mistakes, list):
            continue
        if keyword in search_text:
            for item in mistakes:
                text = str(item).strip()
                if text and text not in matched:
                    matched.append(text)
    if matched:
        return matched[:5]
    defaults = template_conf.get("default_mistakes", []) if isinstance(template_conf, dict) else []
    out = [str(x).strip() for x in defaults if str(x).strip()]
    return out[:5]


def enrich_topics_common_mistakes(topic_rows: List[dict], problem_rows: List[dict], template_conf: dict) -> List[dict]:
    by_topic: Dict[str, List[dict]] = defaultdict(list)
    for row in problem_rows:
        by_topic[str(row.get("topic_id", "")).strip()].append(row)
    for topic in topic_rows:
        existing = topic.get("common_mistakes", [])
        if isinstance(existing, list) and len(existing) > 0:
            topic["common_mistakes_source"] = "direct"
            continue
        topic_id = str(topic.get("topic_id", "")).strip()
        title = str(topic.get("title", "")).strip()
        method_counter = Counter()
        for p in by_topic.get(topic_id, []):
            for tag in p.get("method_tags", []):
                if isinstance(tag, str) and tag.strip():
                    method_counter[tag.strip()] += 1
        tags = [x for x, _ in method_counter.most_common(8)]
        inferred = infer_common_mistakes(title, tags, template_conf)
        if inferred:
            topic["common_mistakes"] = inferred
            topic["common_mistakes_source"] = "template"
        else:
            topic["common_mistakes_source"] = "none"
    return topic_rows


def build_problem(topic_id: str, topic_title: str, asset_id: str, idx: int, block: List[str], source_ref: dict) -> dict:
    stem = block[0][:500]
    if re.fullmatch(r"(计算[：:]|求[：:]|解[：:]|应用题[：:])", stem):
        for line in block[1:]:
            if not line.startswith("【"):
                stem = f"{stem}{line}"[:500]
                break
    joined = " ".join(block[:5])
    tags = parse_tags(joined)
    answer = ""
    analysis_steps: List[str] = []
    method_tags: List[str] = []
    grade_band = ""
    difficulty = ""

    for i, line in enumerate(block[1:], start=1):
        if "【答案】" in line:
            answer = line.split("【答案】", 1)[-1].strip(" ：:.。")
            if not answer and i + 1 < len(block):
                nxt = block[i + 1].strip()
                if nxt and not nxt.startswith("【"):
                    answer = nxt[:240]
            continue
        if line.startswith(("原式", "解", "步骤", "思路")):
            analysis_steps.append(line[:240])
        elif line.startswith("="):
            analysis_steps.append(line[:240])
        if "【考点】" in line:
            point = line.split("【考点】", 1)[-1].split("【", 1)[0].strip()
            if point:
                method_tags.append(point)
        if "【关键词】" in line:
            k = line.split("【关键词】", 1)[-1].split("【", 1)[0].strip()
            if k:
                method_tags.extend([x.strip() for x in re.split(r"[，,、]", k) if x.strip()])
                grade_band = grade_band or extract_grade_band(k)
        if "【难度】" in line:
            difficulty = difficulty or extract_difficulty(line)

    if "难度" in tags:
        difficulty = difficulty or extract_difficulty(tags["难度"])
    grade_band = grade_band or extract_grade_band(stem, joined)
    if not analysis_steps:
        analysis_steps = build_fallback_analysis(block)
    if not analysis_steps:
        analysis_steps = build_answer_backfill(answer)

    problem_id = f"problem_{hashlib.sha1(f'{topic_id}:{asset_id}:{idx}'.encode('utf-8')).hexdigest()[:16]}"
    method_tags = sorted(set(method_tags))[:20]
    method_tag_source = "direct" if method_tags else "none"
    if not method_tags:
        method_tags = infer_method_tags_from_title(topic_title)
        if method_tags:
            method_tag_source = "topic_title"

    return {
        "problem_id": problem_id,
        "topic_id": topic_id,
        "stem": stem,
        "answer": answer,
        "analysis_steps": analysis_steps[:10],
        "method_tags": method_tags,
        "method_tag_source": method_tag_source,
        "grade_band": grade_band,
        "difficulty": difficulty,
        "grade_source": "direct" if grade_band else "none",
        "difficulty_source": "direct" if difficulty else "none",
        "source_ref": source_ref,
    }


def build_concepts(topic_rows: List[dict], problem_rows: List[dict]) -> List[dict]:
    by_topic: Dict[str, List[dict]] = defaultdict(list)
    for row in problem_rows:
        by_topic[str(row.get("topic_id", "")).strip()].append(row)
    concepts: List[dict] = []
    for topic in topic_rows:
        topic_id = str(topic.get("topic_id", "")).strip()
        title = str(topic.get("title", "")).strip()
        source_ref = topic.get("source_ref", {})
        method_counter = Counter()
        for p in by_topic.get(topic_id, []):
            for tag in p.get("method_tags", []):
                if isinstance(tag, str) and tag.strip():
                    method_counter[tag.strip()] += 1
        key_terms = [x for x, _ in method_counter.most_common(5)]
        if not key_terms and title:
            key_terms = infer_method_tags_from_title(title)
        description = ""
        objectives = topic.get("learning_objectives", [])
        if isinstance(objectives, list) and objectives:
            description = str(objectives[0])[:240]
        elif title:
            description = f"{title}相关核心概念"
        concept_id = f"concept_{hashlib.sha1(f'{topic_id}:{title}'.encode('utf-8')).hexdigest()[:16]}"
        concepts.append(
            {
                "concept_id": concept_id,
                "topic_id": topic_id,
                "name": title or topic_id,
                "description": description,
                "key_terms": key_terms,
                "source_ref": source_ref,
            }
        )
    return concepts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    topics, assets, status = load_inputs(project_root)
    common_mistake_templates = read_json(project_root / "config" / "common_mistake_templates.json")
    curated_dir = project_root / "artifacts" / "curated"
    curated_dir.mkdir(parents=True, exist_ok=True)

    topic_rows: List[dict] = []
    explanation_rows: List[dict] = []
    problem_rows: List[dict] = []
    issue_rows: List[dict] = []

    for topic in topics:
        topic_id = topic.get("topic_id") or topic.get("topic_key", "")
        canonical_asset_id = pick_canonical_asset(topic)
        if not canonical_asset_id:
            issue_rows.append({"issue_type": "missing_canonical_asset", "topic_id": topic_id})
            continue
        ext_status = status.get(canonical_asset_id)
        if not ext_status or ext_status.get("extract_status") != "success":
            issue_rows.append(
                {"issue_type": "canonical_asset_not_extracted", "topic_id": topic_id, "asset_id": canonical_asset_id}
            )
            continue

        output_text_path = project_root / ext_status["output_text_path"]
        lines = parse_text(output_text_path)
        if not lines:
            issue_rows.append({"issue_type": "empty_extracted_text", "topic_id": topic_id, "asset_id": canonical_asset_id})
            continue

        source_ref = {
            "asset_id": canonical_asset_id,
            "file_path": assets[canonical_asset_id]["file_path"],
            "text_path": ext_status["output_text_path"],
        }
        summary = extract_topic_summary(lines)
        learning_objectives, common_mistakes = extract_learning_fields(lines)
        problem_blocks = split_problem_blocks(lines)

        topic_rows.append(
            {
                "topic_id": topic_id,
                "title": topic.get("title", ""),
                "canonical_edition": topic.get("canonical_edition", "teacher"),
                "pair_status": topic.get("pair_status", ""),
                "prerequisites": [],
                "learning_objectives": learning_objectives,
                "common_mistakes": common_mistakes,
                "source_ref": source_ref,
            }
        )

        explanation_rows.append(
            {
                "explanation_id": f"explain_{hashlib.sha1(f'{topic_id}:{canonical_asset_id}'.encode('utf-8')).hexdigest()[:16]}",
                "topic_id": topic_id,
                "audience": "teacher",
                "summary": summary,
                "key_points": [line for line in lines[:20] if line.startswith(("一、", "二、", "三、", "四、", "五、"))][:10],
                "teaching_tips": [],
                "misconception_fix": [],
                "source_ref": source_ref,
            }
        )

        for idx, block in enumerate(problem_blocks, start=1):
            problem_rows.append(build_problem(topic_id, topic.get("title", ""), canonical_asset_id, idx, block, source_ref))

    enriched_problem_rows = enrich_problem_fields(problem_rows)
    enriched_topic_rows = enrich_topics_common_mistakes(topic_rows, enriched_problem_rows, common_mistake_templates)
    write_jsonl(curated_dir / "topics.jsonl", enriched_topic_rows)
    write_jsonl(curated_dir / "explanations.jsonl", explanation_rows)
    write_jsonl(curated_dir / "problems.jsonl", enriched_problem_rows)
    concept_rows = build_concepts(enriched_topic_rows, enriched_problem_rows)
    write_jsonl(curated_dir / "concepts.jsonl", concept_rows)
    write_jsonl(curated_dir / "issues.jsonl", issue_rows)

    summary = {
        "topic_count": len(topic_rows),
        "concept_count": len(concept_rows),
        "explanation_count": len(explanation_rows),
        "problem_count": len(enriched_problem_rows),
        "issue_count": len(issue_rows),
    }
    (curated_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
